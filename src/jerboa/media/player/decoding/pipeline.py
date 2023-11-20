from threading import Condition

from jerboa.core.logger import logger
from jerboa.core.multithreading import ThreadSpawner, Task, FnTask
from jerboa.media.core import MediaType, AudioConfig, VideoConfig, AudioConstraints
from .buffer import create_buffer
from .context import DecodingContext, SeekTask
from .frame import JbAudioFrame, JbVideoFrame
from .decoder import Decoder
from . import node


BUFFER_DURATION = 10  # in seconds
PREFILL_DURATION = 1  # in seconds
assert PREFILL_DURATION < BUFFER_DURATION


class Pipeline(Decoder):
    class KillTask(Task):
        ...

    class DiscardFrameTask(Task):
        def run_impl(self) -> None:
            self.complete__locked()
            # does not rise anything

    def __init__(
        self,
        output_node: node.Node,
        context: DecodingContext,
        thread_spawner: ThreadSpawner,
    ) -> None:
        super().__init__()

        self._output_node = output_node
        self._context = context
        self._mutex = self._context.mutex

        self._root_node = self._output_node
        while self._root_node.parent is not None:
            self._root_node = self._root_node.parent
        self._root_node.reset(self._context, hard=True, recursive=True)

        self._buffer = create_buffer(self._context.media.presentation_config, BUFFER_DURATION)
        self._buffer_not_empty_or_done_decoding = Condition(self._mutex)
        self._buffer_not_full_or_task_added = Condition(self._mutex)
        self._context.tasks.add_on_task_added_callback(self._buffer_not_full_or_task_added.notify)

        self._is_done = False
        self._is_killed = False

        self.seek(self._context.media.av.start_timepoint)
        thread_spawner.start(self.__decoding__thread)

    @property
    def media_type(self) -> MediaType:
        return self.presentation_media_config.media_type

    @property
    def presentation_media_config(self) -> AudioConfig | VideoConfig:
        return self._context.media.presentation_config

    @property
    def is_done(self) -> bool:
        assert not self.is_killed or self._is_done

        return self._is_done

    @property
    def buffered_duration(self) -> float:
        return self._buffer.duration

    @property
    def is_killed(self) -> bool:
        return self._is_killed

    def __decoding__thread(self):
        logger.debug(f"Decoder({self.media_type}): Starting decoding")
        while True:
            try:
                if self._context.tasks.run_all(wait_when_empty=self._is_done) > 0:
                    continue

                output = self._output_node.pull_as_leaf(self._context)
                if output is not None:
                    self.__decoding__put_output_to_buffer(output)
                else:
                    with self._mutex:
                        self._is_done = True
                        self._buffer_not_empty_or_done_decoding.notify_all()

            except SeekTask as seek_task:
                seek_task.complete_after(self.__decoding__seek, seek_task.timepoint)
            except Pipeline.KillTask as task:
                logger.debug(f"Decoder({self.media_type}): Killed by a task")
                task.complete_after(self.__decoding__kill)
                break  # ends the thread
            except:
                logger.debug(f"Decoder({self.media_type}): Killed by an error")
                self.__decoding__kill()
                raise  # ends the thread

    def __decoding__put_output_to_buffer(self, output: JbAudioFrame | JbVideoFrame) -> None:
        with self._mutex:
            self._buffer_not_full_or_task_added.wait_for(
                lambda: not self._buffer.is_full() or not self._context.tasks.is_empty()
            )
            if not self._buffer.is_full():
                self._buffer.put(output)
                self._buffer_not_empty_or_done_decoding.notify()
            # else a task has been added, which will be handled in the main loop

    def __decoding__seek(self, timepoint: float) -> None:
        logger.debug(f"Decoder({self.media_type}): Seeking to {timepoint}")

        with self._mutex:
            self._context.seek__locked(timepoint)
            self._root_node.reset(self._context, hard=False, recursive=True)

            self._buffer.clear()
            self._buffer_not_full_or_task_added.notify_all()

            self._is_done = False

    def __decoding__kill(self) -> None:
        with self._mutex:
            assert not self.is_killed

            self._buffer.clear()
            self._context.tasks.clear__locked()
            self._is_done = True
            self._is_killed = True

            self._buffer_not_empty_or_done_decoding.notify_all()

    def pop(
        self,
        /,
        *args,
        timeout: float | None = None,
    ) -> JbAudioFrame | JbVideoFrame | None:
        frame = None
        with self._mutex:
            if self._buffer_not_empty_or_done_decoding.wait_for(
                lambda: self._is_done or not self._buffer.is_empty(),
                timeout=timeout,
            ):
                if not self._buffer.is_empty():
                    frame = self._buffer.pop(*args)
                    self._buffer_not_full_or_task_added.notify()
            else:
                raise TimeoutError()
        return frame

    def prefill(self, timeout: float | None = None) -> Task.Future:
        from threading import Thread

        prefill_task = FnTask(
            self._buffer_not_empty_or_done_decoding.wait_for,
            predicate=lambda: self._is_done
            or self._buffer.duration >= PREFILL_DURATION
            or self._buffer.is_full(),
            timeout=timeout,
        )

        def _prefill_thread():
            with self._mutex:
                prefill_task.run()

        Thread(target=_prefill_thread, daemon=True).start()
        return prefill_task.future

    def seek(self, timepoint: float) -> Task.Future:
        assert timepoint >= 0

        return self._add_task(SeekTask(timepoint))

    def _add_task(self, task: Task) -> Task.Future:
        with self._mutex:
            if self._is_killed:
                task.cancel()
            else:
                logger.debug(f"Decoder({self.media_type}): Adding task {repr(task)}")
                self._context.tasks.add_task__locked(task)
        return task.future

    def kill(self) -> Task.Future:
        task = Pipeline.KillTask()
        with self._mutex:
            if self._is_killed:
                task.complete()
            else:
                self._context.tasks.add_task__locked(task)
        return task.future

    def apply_new_media_constraints(self, new_constraints: AudioConstraints | None) -> Task.Future:
        # TODO: if it changes the presentation format, just clear the buffer and continue decoding
        task = FnTask(lambda: None)
        task.cancel()
        return task.future


def create_audio_decoding_pipeline(
    context: DecodingContext,
    thread_spawner: ThreadSpawner,
) -> Pipeline:
    return Pipeline(
        output_node=node.AudioPresentationReformattingNode(
            parent=node.FrameMappingNode(
                parent=node.FrameMappingPreparationNode(
                    parent=node.AudioIntermediateReformattingNode(
                        parent=node.AccurateSeekNode(
                            parent=node.TimedAudioFrameCreationNode(
                                parent=node.AudioFrameTimingCorrectionNode(
                                    parent=node.DecodingNode(
                                        parent=node.KeyframeIntervalWatcherNode(
                                            parent=node.DemuxingNode(),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        context=context,
        thread_spawner=thread_spawner,
    )


def create_video_decoding_pipeline(
    context: DecodingContext,
    thread_spawner: ThreadSpawner,
) -> Pipeline:
    return Pipeline(
        output_node=node.VideoPresentationReformattingNode(
            parent=node.FrameMappingNode(
                parent=node.FrameMappingPreparationNode(
                    parent=node.TimedVideoFrameCreationNode(
                        parent=node.DecodingNode(
                            parent=node.KeyframeIntervalWatcherNode(
                                parent=node.DemuxingNode(),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        context=context,
        thread_spawner=thread_spawner,
    )
