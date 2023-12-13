from threading import RLock, Lock, Condition

import PySide6.QtWidgets as QtW
import PySide6.QtMultimedia as QtM
import PySide6.QtCore as QtC

from jerboa.utils import ActivationContext
from jerboa.logger import logger
from jerboa.core.signal import Signal
from jerboa.core.multithreading import (
    ThreadSpawner,
    TaskQueue,
    Task,
    FnTask,
)
from jerboa.media.core import MediaType, AudioSampleFormat, AudioChannelLayout, AudioConstraints
from .decoding.decoder import Decoder
from .state import PlayerState
from .timer import PlaybackTimer

AUDIO_THREAD_EVENT_PROCESS_FREQUENCY = 1 / 60

SEEK_PREFILL_TIMEOUT = 2.5  # in seconds
THREAD_RESPONSE_TIMEOUT = 0.1


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
    class KillTask(Task):
        ...

    def __init__(
        self,
        app: QtW.QApplication,
        thread_spawner: ThreadSpawner,
        output_devices_changed_signal: Signal,
        current_output_device_changed_signal: Signal,
    ):
        self._app = app
        self._output_devices_changed_signal = output_devices_changed_signal
        self._current_output_device_changed_signal = current_output_device_changed_signal

        self._mutex = Lock()
        self._media_devices: QtM.QMediaDevices | None = None
        self._current_device: QtM.QAudioDevice | None = None

        self._is_thread_killed = False
        self._is_thread_running = False
        self._is_thread_running_condition = Condition(lock=self._mutex)

        self._tasks = TaskQueue()
        thread_spawner.start(self.__audio_thread)

    @property
    def output_devices_changed_signal(self) -> Signal:
        return self._output_devices_changed_signal

    @property
    def current_output_device_changed_signal(self) -> Signal:
        return self._current_output_device_changed_signal

    def set_current_output_device(self, output_device: QtM.QAudioDevice) -> None:
        with self._mutex:
            self._is_thread_running_condition.wait_for(
                lambda: self._is_thread_running, timeout=THREAD_RESPONSE_TIMEOUT
            )

            self._current_device = output_device
            self._current_output_device_changed_signal.emit()

    def get_output_devices(self) -> list:
        with self._mutex:
            self._is_thread_running_condition.wait_for(
                lambda: self._is_thread_running, timeout=THREAD_RESPONSE_TIMEOUT
            )

            return self._media_devices.audioOutputs()

    def get_current_output_device(self) -> QtM.QAudioDevice:
        with self._mutex:
            self._is_thread_running_condition.wait_for(
                lambda: self._is_thread_running, timeout=THREAD_RESPONSE_TIMEOUT
            )

            return self._current_device

    def get_current_output_device_constraints(self) -> AudioConstraints:
        with self._mutex:
            self._is_thread_running_condition.wait_for(
                lambda: self._is_thread_running, timeout=THREAD_RESPONSE_TIMEOUT
            )

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

    # --------------------------------------- Audio thread --------------------------------------- #

    def __audio_thread(self) -> None:
        with self._mutex:
            self._current_device = QtM.QMediaDevices.defaultAudioOutput()
            self._media_devices = QtM.QMediaDevices()
            self._media_devices.audioOutputsChanged.connect(self.output_devices_changed_signal.emit)
            self._is_thread_running = True
            self._is_thread_running_condition.notify_all()
        while True:
            try:
                QtC.QCoreApplication.processEvents()
                self._tasks.run_all(timeout=AUDIO_THREAD_EVENT_PROCESS_FREQUENCY)

            except AudioManager.KillTask as kill_task:
                if kill_task.execute_and_finish(self.__audio_thread__kill):
                    break
            except Exception as exception:
                logger.error("AudioThread: Task crashed with the following exception:")
                logger.exception(exception)

    def __audio_thread__kill(self) -> None:
        logger.info("AudioThread: Killed by a task")
        with self._mutex:
            self._is_thread_killed = True
            self._tasks.clear(abort_current_task=False)

    def run_on_audio_thread(self, task: Task) -> Task.Future:
        with self._mutex:
            if self._is_thread_killed:
                task.future.abort()
            else:
                self._tasks.add_task(task)
            return task.future


class QtAudioSourceDevice(QtC.QIODevice):
    def __init__(self, decoder: Decoder):
        QtC.QIODevice.__init__(self)

        self._decoder = decoder
        self._bytes_per_sample = self._decoder.presentation_media_config.bytes_per_sample

        self.open(QtC.QIODevice.OpenModeFlag.ReadWrite)

    def readData(self, maxSize: int) -> bytes:
        wanted_samples_num = int(maxSize / self._bytes_per_sample)
        try:
            audio = self._decoder.pop(wanted_samples_num, timeout=0)
        except TimeoutError:
            audio = None
            logger.debug("QtAudioSourceDevice: Buffer underrun")

        if audio is not None:
            return audio.audio_signal.tobytes()
        return bytes()

    def writeData(self, _) -> int:
        return 0  # Not implemented as we're only reading audio data

    def bytesAvailable(self) -> int:
        return 0


class AudioPlayer(PlaybackTimer):
    def __init__(
        self,
        audio_manager: AudioManager,
        fatal_error_signal: Signal,
        buffer_underrun_signal: Signal,
        eof_signal: Signal,
    ):
        self._state = PlayerState.UNINITIALIZED
        self._decoder: Decoder | None = None
        self._audio_sink: QtM.QAudioSink | None = None
        self._time_offset: float | None = None

        self._ignore_state_changes = ActivationContext()

        self._audio_manager = audio_manager
        self._audio_manager.current_output_device_changed_signal.connect(
            self.__audio_thread__on_output_device_changed
        )

        self._fatal_error_signal = fatal_error_signal
        self._buffer_underrun_signal = buffer_underrun_signal
        self._eof_signal = eof_signal

        # Operations on `audio_sink` change its state, thus
        # `__audio_thread__on_audio_sink_state_change` will be called.
        # `__audio_thread__on_audio_sink_state_change` needs the mutex locked, so RLock is required
        self._rlock = RLock()

    def __del__(self):
        self.uninitialize()

    @property
    def fatal_error_signal(self) -> Signal:
        return self._fatal_error_signal

    @property
    def buffer_underrun_signal(self) -> Signal:
        return self._buffer_underrun_signal

    @property
    def eof_signal(self) -> Signal:
        return self._eof_signal

    @property
    def state(self) -> PlayerState:
        return self._state

    @property
    def is_initialized(self) -> bool:
        return self._state != PlayerState.UNINITIALIZED

    @property
    def reached_eof(self) -> bool:
        return (
            self._state != PlayerState.UNINITIALIZED
            and self._audio_sink.state() == QtM.QAudio.State.IdleState
            and self._decoder.is_done
            and self._decoder.buffered_duration <= 0
        )

    @QtC.Slot()
    def __audio_thread__on_output_device_changed(self) -> None:
        with self._rlock:
            if self._audio_sink is not None:
                self._audio_sink.reset()
                self._decoder.apply_new_media_constraints(self.get_constraints())

    @QtC.Slot(QtM.QAudio.State)
    def __audio_thread__on_audio_sink_state_change(self, qt_state: QtM.QAudio.State) -> None:
        with self._rlock:
            if self._ignore_state_changes:
                return

            match qt_state:
                case QtM.QAudio.State.ActiveState:
                    self._set_state_with_log(PlayerState.PLAYING)
                case QtM.QAudio.State.SuspendedState:
                    self._set_state_with_log(PlayerState.SUSPENDED)
                case QtM.QAudio.State.IdleState:
                    assert self._decoder is not None

                    self._set_state_with_log(PlayerState.SUSPENDED)
                    if self._decoder.is_done and self._decoder.buffered_duration <= 0:
                        logger.warning("Suspended by EOF")
                        self.eof_signal.emit()
                    else:
                        logger.warning("Suspended by buffer underrun")
                        self.buffer_underrun_signal.emit()
                case QtM.QAudio.State.StoppedState:
                    self._set_state_with_log(PlayerState.UNINITIALIZED)
                    if self._decoder is not None:
                        self.fatal_error_signal.emit()
                case _:
                    raise ValueError(f"Unrecognized state: {qt_state}")

    def _set_state_with_log(self, state: PlayerState) -> None:
        if self._state != state:
            logger.debug(f"Changing the state ({self._state} -> {state})")
            self._state = state

    def initialize(self, decoder: Decoder) -> Task.Future:
        assert decoder.media_type == MediaType.AUDIO
        return self._audio_manager.run_on_audio_thread(
            FnTask(lambda executor: self.__audio_thread__initialize(executor, decoder))
        )

    def __audio_thread__initialize(self, executor: Task.Executor, decoder: Decoder) -> None:
        with self._rlock:
            logger.debug("Initializing...")

            assert self.state == PlayerState.UNINITIALIZED and self._decoder is None

            decoder_future = decoder.apply_new_media_constraints(self.get_constraints())
            executor.abort_aware_wait_for_future(decoder_future)
            if decoder_future.stage != Task.Stage.FINISHED_CLEAN:
                logger.error("Initializing... Failed (Decoder constraints update error)")
                executor.abort()

            jb_audio_cofnig = decoder.presentation_media_config
            audio_format = QtM.QAudioFormat()
            audio_format.setSampleRate(jb_audio_cofnig.sample_rate)
            audio_format.setChannelCount(jb_audio_cofnig.channels_num)
            audio_format.setSampleFormat(
                jb_to_qt_audio_sample_format(jb_audio_cofnig.sample_format)
            )

            with executor.finish_context:
                if self.__audio_thread__reset__locked(audio_format, decoder):
                    logger.debug("Initializing... Successful")
                else:
                    logger.error("Initializing... Failed")
                    executor.abort()

    def __audio_thread__reset__locked(
        self, audio_format: QtM.QAudioFormat, decoder: Decoder
    ) -> bool:
        logger.debug("Resetting audio sink...")

        self.__audio_thread__reset__clear_audio_sink__locked()
        if decoder is not self._decoder:
            self.__audio_thread__reset__clear_decoder__locked()
        self.__audio_thread__reset__init__locked(audio_format, decoder)

        if self.state == PlayerState.UNINITIALIZED:
            logger.error("Resetting audio sink... Failed (QAudioSink malfunction)")
            self.__audio_thread__reset__clear_decoder__locked()
            self.__audio_thread__reset__clear_audio_sink__locked()
            self._set_state_with_log(PlayerState.UNINITIALIZED)
            self.fatal_error_signal.emit()
            return False

        logger.debug("Resetting audio sink... Successful)")
        return True

    def __audio_thread__reset__clear_decoder__locked(self) -> None:
        if self._decoder is not None:
            self._decoder.kill()  # we do not need to wait for it to finish
            self._decoder = None
            self._time_offset = None

    def __audio_thread__reset__clear_audio_sink__locked(self) -> None:
        if self._audio_sink is not None:
            with self._ignore_state_changes:
                self._audio_sink.stop()
                self._audio_sink.stateChanged.disconnect()
                self._audio_sink.deleteLater()
                self._audio_sink = None

    def __audio_thread__reset__init__locked(
        self, audio_format: QtM.QAudioFormat, decoder: Decoder
    ) -> None:
        assert self._audio_sink is None

        if decoder.current_timepoint is None:
            logger.error("Decoder not prefilled")
            return

        self._decoder = decoder
        self._time_offset = decoder.current_timepoint

        self._audio_sink = QtM.QAudioSink(
            self._audio_manager.get_current_output_device(), audio_format
        )
        self._audio_sink.stateChanged.connect(self.__audio_thread__on_audio_sink_state_change)
        self._audio_sink.start(QtAudioSourceDevice(decoder))
        self._audio_sink.suspend()

    def uninitialize(self) -> Task.Future:
        return self._audio_manager.run_on_audio_thread(
            FnTask(lambda executor: executor.finish_with(self.__audio_thread__uninitialize))
        )

    def __audio_thread__uninitialize(self) -> None:
        with self._rlock:
            if self.state == PlayerState.UNINITIALIZED:
                logger.debug("Player is already uninitialized")
                return

            logger.debug("Uninitializing...")

            self.__audio_thread__reset__clear_audio_sink__locked()
            self.__audio_thread__reset__clear_decoder__locked()

            self._set_state_with_log(PlayerState.UNINITIALIZED)

            logger.debug("Uninitializing... Successful")

    def suspend(self) -> Task.Future:
        return self._audio_manager.run_on_audio_thread(FnTask(self.__audio_thread__suspend))

    def __audio_thread__suspend(self, executor: Task.Executor) -> None:
        with self._rlock:
            if self._audio_sink is None:
                logger.error("Suspending... Failed (Player not initialized)")
                executor.abort()

            if self.state == PlayerState.SUSPENDED:
                executor.finish()
                logger.debug("Player is already suspended")
            else:
                with executor.finish_context:
                    logger.debug("Suspending...")
                    self._audio_sink.suspend()
                    if self.state != PlayerState.SUSPENDED:
                        logger.error("Suspending... Failed")
                        executor.abort()
                    logger.debug("Suspending... Successful")

    def resume(self) -> Task.Future:
        return self._audio_manager.run_on_audio_thread(FnTask(self.__audio_thread__resume))

    def __audio_thread__resume(self, executor: Task.Executor) -> None:
        with self._rlock:
            if self._audio_sink is None:
                logger.debug("Not resuming (player not initialized)")
                executor.abort()

            with executor.finish_context:
                if self.state == PlayerState.PLAYING:
                    logger.debug("Player is already playing")
                else:
                    logger.debug("Resuming...")

                    self._audio_sink.resume()
                    if self.state != PlayerState.PLAYING:
                        logger.error("Resuming... Failed (EOF or decoder error)")
                        executor.abort()
                    logger.debug("Resuming... Successful")

    def seek(self, source_timepoint: float) -> Task.Future:
        assert self.state != PlayerState.PLAYING

        return self._audio_manager.run_on_audio_thread(
            FnTask(lambda executor: self.__audio_thread__seek(executor, source_timepoint))
        )

    def __audio_thread__seek(self, executor: Task.Executor, source_timepoint: float) -> None:
        assert source_timepoint >= 0

        logger.debug("Seeking...")
        with self._rlock:
            if self._audio_sink is None:
                executor.abort()

            seek_future = self._decoder.seek(source_timepoint)
            executor.abort_aware_wait_for_future(seek_future)
            if seek_future.stage != Task.Stage.FINISHED_CLEAN:
                logger.error("Seeking... Failed (Decoder seek failed)")
                executor.abort()

            prefill_future = self._decoder.prefill()
            executor.abort_aware_wait_for_future(prefill_future)
            if prefill_future.stage != Task.Stage.FINISHED_CLEAN:
                if self._decoder.is_done and self._decoder.buffered_duration <= 0:
                    logger.info("Seeking... Failed (EOF)")
                    self._state = PlayerState.SUSPENDED
                    self.eof_signal.emit()
                else:
                    logger.error("Seeking... Failed (Decoder prefill failed)")
                executor.abort()

            with executor.finish_context:
                # for some reason QAudioSink stops working after a few restarts, so instead we just
                # create a new sink each time...
                if self.__audio_thread__reset__locked(self._audio_sink.format(), self._decoder):
                    logger.debug("Seeking... Successful")
                else:
                    logger.error("Seeking... Failed")
                    executor.abort()

    def current_timepoint(self) -> float | None:
        with self._rlock:
            if self._audio_sink is not None and self._time_offset is not None:
                return self._time_offset + self._audio_sink.processedUSecs() / 1e6
        return None

    def get_constraints(self) -> AudioConstraints:
        return self._audio_manager.get_current_output_device_constraints()
