from threading import Lock

import PySide6.QtWidgets as QtW
import PySide6.QtMultimedia as QtM
import PySide6.QtCore as QtC

from jerboa.core.signal import Signal
from jerboa.media.source import AudioSourceVariant
from jerboa.media.core import MediaType, AudioConfig, AudioConstraints
from .decoding.decoder import JbDecoder, pipeline
from .state import PlayerState

# from jerboa.core.timeline import FragmentedTimeline


class AudioManager:
    def __init__(
        self,
        app: QtW.QApplication,
        output_devices_changed_signal: Signal,
        current_output_device_changed_signal: Signal,
    ):
        self._app = app
        self._output_devices = QtM.QMediaDevices()
        self._current_device = self._output_devices.defaultAudioOutput()

        self._output_devices.audioOutputsChanged.connect(output_devices_changed_signal.emit)
        self._output_devices_changed_signal = output_devices_changed_signal
        self._current_output_device_changed_signal = current_output_device_changed_signal

    @property
    def output_devices_changed_signal(self) -> Signal:
        return self._output_devices_changed_signal

    @property
    def current_output_device_changed_signal(self) -> Signal:
        return self._current_output_device_changed_signal

    def set_current_output_device(self, output_device: QtM.QAudioDevice) -> None:
        self._current_device = output_device
        self._current_output_device_changed_signal.emit()

    def get_output_devices(self) -> list:
        return self._output_devices.audioOutputs()

    def get_current_output_device(self) -> QtM.QAudioDevice:
        return self._current_device

    def get_current_output_device_constraints(self) -> AudioConstraints:
        return AudioConstraints(
            sample_formats=self._get_supported_sample_formats(),
            channel_layouts=self._get_supported_channel_layouts(),
            channels_num_min=self._current_device.minimumChannelCount(),
            channels_num_max=self._current_device.maximumChannelCount(),
            sample_rate_min=self._current_device.minimumSampleRate(),
            sample_rate_max=self._current_device.maximumSampleRate(),
        )

    def _get_supported_sample_formats(self) -> AudioConstraints.SampleFormat:
        jb_sample_formats = AudioConstraints.SampleFormat.NONE

        sample_formats = self._current_device.supportedSampleFormats()
        for sample_format in sample_formats:
            match sample_format:
                case QtM.QAudioFormat.SampleFormat.UInt8:
                    jb_sample_formats |= AudioConstraints.SampleFormat.U8
                case QtM.QAudioFormat.SampleFormat.Int16:
                    jb_sample_formats |= AudioConstraints.SampleFormat.S16
                case QtM.QAudioFormat.SampleFormat.Int32:
                    jb_sample_formats |= AudioConstraints.SampleFormat.S32
                case QtM.QAudioFormat.SampleFormat.Float:
                    jb_sample_formats |= AudioConstraints.SampleFormat.F32
                case _:
                    pass
        return jb_sample_formats

    def _get_supported_channel_layouts(self) -> AudioConstraints.ChannelLayout:
        match self._current_device.channelConfiguration():
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigSurround7Dot1:
                return AudioConstraints.ChannelLayout.LAYOUT_SURROUND_7_1
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigSurround7Dot0:
                return AudioConstraints.ChannelLayout.LAYOUT_SURROUND_7_0
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigSurround5Dot1:
                return AudioConstraints.ChannelLayout.LAYOUT_SURROUND_5_1
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigSurround5Dot0:
                return AudioConstraints.ChannelLayout.LAYOUT_SURROUND_5_0
            case QtM.QAudioFormat.ChannelConfig.ChannelConfig3Dot1:
                return AudioConstraints.ChannelLayout.LAYOUT_3_1
            case QtM.QAudioFormat.ChannelConfig.ChannelConfig3Dot0:
                return AudioConstraints.ChannelLayout.LAYOUT_3_0
            case QtM.QAudioFormat.ChannelConfig.ChannelConfig2Dot1:
                return AudioConstraints.ChannelLayout.LAYOUT_2_1
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigStereo:
                return AudioConstraints.ChannelLayout.LAYOUT_STEREO
            case _:
                return AudioConstraints.ChannelLayout.LAYOUT_MONO


class QtAudioSourceDevice(QtC.QIODevice):
    def __init__(self, decoder: JbDecoder):
        assert decoder.stream_info.media_type == MediaType.AUDIO

        QtC.QIODevice.__init__(self)

        self._decoder = decoder
        self.open(QtC.QIODevice.ReadOnly)

    def readData(self, maxSize: int) -> bytes:
        audio_config: AudioConfig = self._decoder.dst_media_config

        sample_size_in_bytes = audio_config.channels_num * audio_config.format.bytes
        wanted_samples_num = int(maxSize / sample_size_in_bytes)
        audio = self._decoder.pop(wanted_samples_num)
        if audio is not None:
            return audio.signal.tobytes()
        return -1

    def writeData(self, _) -> int:
        return 0  # Not implemented as we're only reading audio data

    def bytesAvailable(self) -> int:
        return 0


class AudioPlayer:
    def __init__(self, audio_manager: AudioManager, decoder: JbDecoder):
        self._mutex = Lock()

        self._audio_sink: QtM.QAudioSink | None = None
        self._decoder: JbDecoder | None = None

        self._audio_manager = audio_manager
        self._audio_manager.current_output_device_changed_signal.connect(
            self._on_output_device_changed
        )

    def __del__(self):
        self.stop()

    def _on_output_device_changed(self) -> None:
        with self._mutex:
            if self._audio_sink:
                self._audio_sink.reset()
                self._decoder.apply_new_media_constraints(
                    self._audio_manager.get_current_output_device_constraints(),
                    start_timepoint=0,
                )

    def wait_for_state(self, state: PlayerState, timeout: float) -> None:
        pass
        # with self._mutex:
        #     if not self._state_changed.wait_for(lambda: self._state == state, timeout=timeout):
        #         raise TimeoutError(f"Waiting for state ({state=}) timed out ({timeout=})")

    def stop(self) -> None:
        with self._mutex:
            self._stop_unsafe()

    def _stop_unsafe(self) -> None:
        assert self._mutex.locked()

        if self._audio_sink:
            self._audio_sink.stop()
        self._audio_sink = None

    def suspend(self) -> None:
        with self._mutex:
            if self._audio_sink:
                self._audio_sink.suspend()

    def resume(self) -> None:
        with self._mutex:
            if self._audio_sink:
                self._audio_sink.resume()

    def start(self, source: AudioSourceVariant):
        assert source.media_type == MediaType.AUDIO

        with self._mutex:
            self._stop_unsafe()

            media_context = pipeline.MediaContext.open(
                source.path,
                MediaType.AUDIO,
                stream_idx=0,
                media_constraints=self._audio_manager.get_current_output_device_constraints(),
            )

            jb_audio_cofnig = decoder.dst_media_config
            audio_format = QtM.QAudioFormat()
            audio_format.setSampleRate(jb_audio_cofnig.sample_rate)
            audio_format.setChannelCount(jb_audio_cofnig.channels_num)
            audio_format.setSampleFormat(QtM.QAudioFormat.SampleFormat.Float)

            self._audio_sink = QtM.QAudioSink(
                self._audio_manager.get_current_output_device(),
                audio_format,
            )
            self._audio_sink.start(QtAudioSourceDevice(decoder))
