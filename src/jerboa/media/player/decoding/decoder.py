from threading import Condition
from dataclasses import dataclass

from jerboa.core.logger import logger
from jerboa.core.multithreading import ThreadSpawner, Task, FnTask, Future
from jerboa.media.core import MediaType, AudioConfig, VideoConfig, AudioConstraints
from .buffer import create_buffer
from .context import DecodingContext
from .frame import JbAudioFrame, JbVideoFrame
from . import node


BUFFER_DURATION = 10  # in seconds
PREFILL_DURATION = 1  # in seconds
assert PREFILL_DURATION < BUFFER_DURATION


class Decoder:
    class KillTask(Task):
        ...

    class DiscardFrameTask(Task):
        def run_impl(self) -> None:
            self.complete__locked()
            # does not rise anything

    @dataclass(frozen=True)
    class SeekTask(Task):
        timepoint: float

    def __init__(
        self,
        output_node: node.Node,
        context: DecodingContext,
        thread_spawner: ThreadSpawner,
    ) -> None:
        super().__init__()

        self._context = context
        self._output_node = output_node
        self._root_node = output_node.find_root_node()
        self._root_node.reset(self._context, hard=True, recursive=True)

        self._mutex__shared_with_task_queue = self._context.tasks.mutex
        self._buffer = create_buffer(self._context.media.presentation_config, BUFFER_DURATION)
        self._buffer_not_empty_or_done_decoding = Condition(self._mutex__shared_with_task_queue)
        self._buffer_not_full = Condition(self._mutex__shared_with_task_queue)

        self._is_done = False
        self._is_killed = False

        self.seek(self._context.media.av.start_timepoint)
        thread_spawner.start(self.__thread)

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

    def __thread(self):
        logger.debug(f"Decoder({self.media_type}): Starting decoding")
        while True:
            try:
                self._context.tasks.run_all(None if self._is_done else 0)
                if self._is_done:
                    continue

                output = self._output_node.pull_as_leaf(self._context)
                if output is not None:
                    self.__thread__put_output_to_buffer(output)
                else:
                    with self._buffer_not_empty_or_done_decoding:
                        logger.debug(f"Decoder({self.media_type}): Reached EOF")
                        self._is_done = True
                        self._buffer_not_empty_or_done_decoding.notify_all()

            except Decoder.SeekTask as seek_task:
                seek_task.execute_and_finish_with(self.__thread__seek, seek_task.timepoint)
            except Decoder.KillTask as task:
                with task.execute() as executor:
                    with executor.finish_context():
                        logger.debug(f"Decoder({self.media_type}): Killed by a task")
                        self.__thread__kill(abort_current_task=False)
                        break
            except Exception as exception:
                logger.error(f"Decoder({self.media_type}): Killed by an error")
                logger.exception(exception)
                self.__thread__kill(abort_current_task=True)
                break

    def __thread__put_output_to_buffer(self, output: JbAudioFrame | JbVideoFrame) -> None:
        task_added = self._context.tasks.task_added
        with task_added.notify_also(self._buffer_not_full, different_locks=False):
            with self._buffer_not_full:
                self._buffer_not_full.wait_for(
                    lambda: not self._buffer.is_full() or not self._context.tasks.is_empty()
                )
                if not self._buffer.is_full():
                    self._buffer.put(output)
                    self._buffer_not_empty_or_done_decoding.notify()

    def __thread__seek(self, timepoint: float) -> None:
        logger.debug(f"Decoder({self.media_type}): Seeking to {timepoint}")

        with self._mutex__shared_with_task_queue:
            self._context.seek(timepoint)
            self._root_node.reset(self._context, hard=False, recursive=True)

            self._buffer.clear()
            self._buffer_not_full.notify_all()

            self._is_done = False

    def __thread__kill(self, abort_current_task: bool) -> None:
        with self._mutex__shared_with_task_queue:
            assert not self.is_killed

            self._buffer.clear()
            self._context.tasks.clear__locked(abort_current_task=abort_current_task)
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
        with self._mutex__shared_with_task_queue:
            if self._buffer_not_empty_or_done_decoding.wait_for(
                lambda: self._is_done or not self._buffer.is_empty(),
                timeout=timeout,
            ):
                if not self._buffer.is_empty():
                    frame = self._buffer.pop(*args)
                    self._buffer_not_full.notify_all()
            else:
                raise TimeoutError()
        return frame

    def prefill(self) -> Future:
        from threading import Thread

        def _prefill(executor: FnTask.Executor):
            executor.abort_aware_wait(
                predicate=lambda: (
                    self._is_done
                    or self._buffer.duration >= PREFILL_DURATION
                    or self._buffer.is_full()
                ),
                different_locks=True,
                condition=self._buffer_not_empty_or_done_decoding,
            )
            if self._buffer.duration <= 0:
                executor.abort()
            else:
                executor.finish()

        prefill_task = FnTask(_prefill)

        Thread(target=prefill_task.run_if_unresolved, daemon=True).start()
        return prefill_task.future

    def seek(self, timepoint: float) -> Future:
        assert timepoint >= 0

        task = Decoder.SeekTask(timepoint)
        with self._mutex__shared_with_task_queue:
            if self._is_killed:
                task.future.abort()
            else:
                logger.debug(f"Decoder({self.media_type}): Adding task {repr(task)}")
                self._context.tasks.add_task__locked(task)
        return task.future

    def kill(self) -> Future:
        task = Decoder.KillTask()
        with self._mutex__shared_with_task_queue:
            if self._is_killed:
                task.finish_without_running()
            else:
                self._context.tasks.add_task__locked(task)
        return task.future

    def apply_new_media_constraints(self, new_constraints: AudioConstraints | None) -> Future:
        # TODO: if it changes the presentation format, just clear the buffer and continue decoding
        task = FnTask(lambda: None, already_finished=True)
        return task.future


def create_audio_decoder(
    context: DecodingContext,
    thread_spawner: ThreadSpawner,
) -> Decoder:
    return Decoder(
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


def create_video_decoder(
    context: DecodingContext,
    thread_spawner: ThreadSpawner,
) -> Decoder:
    return Decoder(
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
