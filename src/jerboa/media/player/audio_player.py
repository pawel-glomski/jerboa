from threading import Lock

import PySide6.QtWidgets as QtW
import PySide6.QtMultimedia as QtM
import PySide6.QtCore as QtC

from jerboa.core.signal import Signal
from jerboa.media.source import AudioSourceVariant
from jerboa.media.core import MediaType, AudioSampleFormat, AudioChannelLayout, AudioConstraints
from .decoding.decoder import JbDecoder, pipeline
from .state import PlayerState
from .timer import PlaybackTimer

TIMEOUT_TIME = 0.1


def jb_to_qt_audio_sample_format(
    sample_format_jb: AudioSampleFormat,
) -> QtM.QAudioFormat.SampleFormat:
    match sample_format_jb.data_type:
        case AudioSampleFormat.DataType.U8:
            return QtM.QAudioFormat.SampleFormat.UInt8
        case AudioSampleFormat.DataType.S16:
            return QtM.QAudioFormat.SampleFormat.Int16
        case AudioSampleFormat.DataType.S32:
            return QtM.QAudioFormat.SampleFormat.Int16
        case AudioSampleFormat.DataType.F32:
            return QtM.QAudioFormat.SampleFormat.Float
        case _:
            raise ValueError(f"Unrecognized sample data type: {sample_format_jb.data_type}")


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
            channel_layouts=self._get_supported_channel_layout(),
            channels_num_min=self._current_device.minimumChannelCount(),
            channels_num_max=self._current_device.maximumChannelCount(),
            sample_rate_min=self._current_device.minimumSampleRate(),
            sample_rate_max=self._current_device.maximumSampleRate(),
        )

    def _get_supported_sample_formats(self) -> list[AudioSampleFormat]:
        sample_formats_jb = list[AudioSampleFormat]()

        sample_formats_qt = self._current_device.supportedSampleFormats()
        for sample_format_qt in sample_formats_qt:
            match sample_format_qt:
                case QtM.QAudioFormat.SampleFormat.UInt8:
                    sample_formats_jb.append(
                        AudioSampleFormat(data_type=AudioSampleFormat.DataType.U8, is_planar=False)
                    )
                case QtM.QAudioFormat.SampleFormat.Int16:
                    sample_formats_jb.append(
                        AudioSampleFormat(data_type=AudioSampleFormat.DataType.S16, is_planar=False)
                    )
                case QtM.QAudioFormat.SampleFormat.Int32:
                    sample_formats_jb.append(
                        AudioSampleFormat(data_type=AudioSampleFormat.DataType.S32, is_planar=False)
                    )
                case QtM.QAudioFormat.SampleFormat.Float:
                    sample_formats_jb.append(
                        AudioSampleFormat(data_type=AudioSampleFormat.DataType.F32, is_planar=False)
                    )
                case _:
                    raise ValueError(f"Unrecognized sample format: {sample_format_qt}")

        assert len(set(sample_formats_jb)) == len(sample_formats_jb)

        if len(sample_formats_jb) == 0:
            raise EnvironmentError(
                f"The current audio device ({self._current_device.description()}) "
                "does not support any sample format"
            )

        return sample_formats_jb

    def _get_supported_channel_layout(self) -> AudioChannelLayout:
        result = AudioChannelLayout.LAYOUT_MONO  # enable mono by default
        match self._current_device.channelConfiguration():
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigSurround7Dot1:
                result |= AudioChannelLayout.LAYOUT_SURROUND_7_1
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigSurround7Dot0:
                result |= AudioChannelLayout.LAYOUT_SURROUND_7_0
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigSurround5Dot1:
                result |= AudioChannelLayout.LAYOUT_SURROUND_5_1
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigSurround5Dot0:
                result |= AudioChannelLayout.LAYOUT_SURROUND_5_0
            case QtM.QAudioFormat.ChannelConfig.ChannelConfig3Dot1:
                result |= AudioChannelLayout.LAYOUT_3_1
            case QtM.QAudioFormat.ChannelConfig.ChannelConfig3Dot0:
                result |= AudioChannelLayout.LAYOUT_3_0
            case QtM.QAudioFormat.ChannelConfig.ChannelConfig2Dot1:
                result |= AudioChannelLayout.LAYOUT_2_1
            case QtM.QAudioFormat.ChannelConfig.ChannelConfigStereo:
                result |= AudioChannelLayout.LAYOUT_STEREO
            case _:
                pass
        return result


class QtAudioSourceDevice(QtC.QIODevice):
    def __init__(self, decoder: JbDecoder):
        assert decoder.media_type == MediaType.AUDIO

        QtC.QIODevice.__init__(self)

        self._decoder = decoder
        self._bytes_per_sample = self._decoder.presentation_media_config.bytes_per_sample

        self.open(QtC.QIODevice.ReadOnly)

    def readData(self, maxSize: int) -> bytes:
        wanted_samples_num = int(maxSize / self._bytes_per_sample)
        try:
            audio = self._decoder.pop(wanted_samples_num, timeout=TIMEOUT_TIME)
        except TimeoutError:
            audio = None

        if audio is not None:
            return bytes(audio.audio_signal)
        return -1

    def writeData(self, _) -> int:
        return 0  # Not implemented as we're only reading audio data

    def bytesAvailable(self) -> int:
        return 0


class AudioPlayer(PlaybackTimer):
    def __init__(
        self,
        audio_manager: AudioManager,
        decoder: JbDecoder,
        shutdown_signal: Signal,
        suspend_signal: Signal,
        resume_signal: Signal,
        seek_signal: Signal,
    ):
        self._decoder = decoder

        self._mutex = Lock()

        self._audio_sink: QtM.QAudioSink | None = None

        self._audio_manager = audio_manager
        self._audio_manager.current_output_device_changed_signal.connect(
            self._on_output_device_changed
        )

        self._shutdown_signal = shutdown_signal
        self._suspend_signal = suspend_signal
        self._resume_signal = resume_signal
        self._seek_signal = seek_signal

        self._shutdown_signal.connect(self._shutdown)
        self._suspend_signal.connect(self._suspend)
        self._resume_signal.connect(self._resume)
        self._seek_signal.connect(self._seek)

    def __del__(self):
        self.shutdown()

    def _on_output_device_changed(self) -> None:
        with self._mutex:
            if self._audio_sink:
                self._audio_sink.reset()
                self._decoder.apply_new_media_constraints(
                    self._audio_manager.get_current_output_device_constraints(),
                    start_timepoint=0,
                )

    def startup(self, source: AudioSourceVariant) -> None:
        assert source.media_type == MediaType.AUDIO

        av_context = pipeline.context.AVContext.open(
            source.path,
            MediaType.AUDIO,
            stream_idx=0,
        )

        def _startup() -> None:
            assert self._mutex.locked()

            media = pipeline.context.MediaContext(
                av=av_context,
                media_constraints=self._audio_manager.get_current_output_device_constraints(),
            )

            # if the decoder is already is running, `start()` will wait for it to stop,
            # but since this function is called post-shutdown, this shouldn't be the case
            assert not self._decoder.is_running
            self._decoder.start(media)

            jb_audio_cofnig = media.presentation_config
            audio_format = QtM.QAudioFormat()
            audio_format.setSampleRate(jb_audio_cofnig.sample_rate)
            audio_format.setChannelCount(jb_audio_cofnig.channels_num)
            audio_format.setSampleFormat(
                jb_to_qt_audio_sample_format(jb_audio_cofnig.sample_format)
            )

            self._audio_sink = QtM.QAudioSink(
                self._audio_manager.get_current_output_device(),
                audio_format,
            )
            self._audio_sink.start(QtAudioSourceDevice(self._decoder))

        self._shutdown_signal.emit(self._mutex, _startup, lock=False)

    def shutdown(self) -> None:
        self._shutdown_signal.emit()

    def _shutdown(self, lock: bool = True) -> None:
        if lock:
            with self._mutex:
                self._shutdown__without_lock()
        else:
            self._shutdown__without_lock()

    def _shutdown__without_lock(self) -> None:
        assert self._mutex.locked()
        if self._audio_sink is not None:
            self._decoder.stop()
            self._audio_sink.stop()
        self._audio_sink = None

    def suspend(self) -> None:
        self._suspend_signal.emit()

    def _suspend(self) -> None:
        with self._mutex:
            if self._audio_sink is not None:
                self._audio_sink.suspend()

    def resume(self) -> None:
        self._resume_signal.emit()

    def _resume(self) -> None:
        with self._mutex:
            if self._audio_sink is not None:
                self._audio_sink.resume()

    def seek(self, timepoint: float) -> None:
        self._seek_signal.emit(timepoint=timepoint)

    def _seek(self, timepoint: float) -> None:
        with self._mutex:
            ...

    def playback_timepoint(self) -> float:
        if self._audio_sink is not None:
            return self._audio_sink.processedUSecs() / 1e6
        return 0
