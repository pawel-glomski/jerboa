from dataclasses import dataclass

from jerboa.logger import logger
from jerboa.core.multithreading import ThreadSpawner, Task, FnTask, PredicateEmitter, Thread
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
        self._root_node.reset(self._context, node.Node.ResetReason.NEW_CONTEXT, recursive=True)

        self._mutex__shared_with_task_queue = self._context.tasks.mutex
        self._buffer = create_buffer(self._context.media.presentation_config, BUFFER_DURATION)
        self._buffer_not_empty_or_done_decoding = PredicateEmitter(
            lambda target_duration: (
                (not self._buffer.is_empty() and self._buffer.duration >= target_duration)
                or self._buffer.is_full()
                or self._is_done
            )
        )
        self._buffer_not_full = PredicateEmitter(predicate=lambda: not self._buffer.is_full())

        self._is_done = False
        self._is_killed = False

        self._logger = logger.bind(context=f"{self.__class__.__name__}({self.media_type})")

        self.seek(self._context.media.avc.start_timepoint)
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
    def is_killed(self) -> bool:
        return self._is_killed

    @property
    def buffered_duration(self) -> float:
        return self._buffer.duration

    @property
    def current_timepoint(self) -> float | None:
        return self._buffer.current_timepoint

    def __thread(self):
        self._logger.debug("Starting decoding")
        while True:
            try:
                self._context.tasks.run_all(timeout=(None if self._is_done else 0))
                if self._is_done:
                    continue

                output = self._output_node.pull_as_leaf(self._context)
                if output is not None:
                    self.__thread__put_output_to_buffer(output)
                else:
                    with self._mutex__shared_with_task_queue:
                        self._logger.debug("Reached EOF")
                        self._is_done = True
                        self._buffer_not_empty_or_done_decoding.evaluate_and_emit__locked()

            except Decoder.SeekTask as seek_task:
                seek_task.execute_and_finish(self.__thread__seek, seek_task.timepoint)
            except Decoder.KillTask as task:
                if task.execute_and_finish(self.__thread__kill, "Killed by a task", crashed=False):
                    break
            except Exception as exception:
                self._logger.exception(exception)
                self.__thread__kill("Killed by an error", crashed=True)
                break

    def __thread__put_output_to_buffer(self, output: JbAudioFrame | JbVideoFrame) -> None:
        with self._mutex__shared_with_task_queue:
            buffer_not_full_event = self._buffer_not_full.create_emit_event__locked()
        self._context.tasks.add_event_to_abort_on_task_added(buffer_not_full_event)
        buffer_not_full_event.wait()
        with self._mutex__shared_with_task_queue:
            if not self._buffer.is_full():
                self._buffer.put(output)
                self._buffer_not_empty_or_done_decoding.evaluate_and_emit__locked()
            # else, a task has been added, handle it in the main loop

    def __thread__seek(self, timepoint: float) -> None:
        self._logger.debug(f"Seeking to {timepoint}")

        with self._mutex__shared_with_task_queue:
            self._context.seek(timepoint)
            self._root_node.reset(
                self._context, node.Node.ResetReason.HARD_DISCONTINUITY, recursive=True
            )

            self._buffer.clear()
            self._buffer_not_full.evaluate_and_emit__locked()

            self._is_done = False

    def __thread__kill(self, message: str, *, crashed: bool) -> None:
        if crashed:
            self._logger.error(message)
        else:
            self._logger.debug(message)

        with self._mutex__shared_with_task_queue:
            assert not self.is_killed

            self._buffer.clear()
            self._context.tasks.clear__locked(abort_current_task=crashed)
            self._is_done = True
            self._is_killed = True

            self._buffer_not_empty_or_done_decoding.evaluate_and_emit__locked()

    def pop(self, *args, timeout: float | None = None) -> JbAudioFrame | JbVideoFrame | None:
        with self._mutex__shared_with_task_queue:
            event = self._buffer_not_empty_or_done_decoding.create_emit_event__locked(
                target_duration=0  # any is good
            )
        if not event.wait(timeout=timeout):
            raise TimeoutError()

        frame = None
        with self._mutex__shared_with_task_queue:
            if not self._buffer.is_empty():
                frame = self._buffer.pop(*args)
                self._buffer_not_full.evaluate_and_emit__locked()
        return frame

    def prefill(self) -> Task.Future:
        def _prefill(executor: FnTask.Executor):
            with self._mutex__shared_with_task_queue:
                event = self._buffer_not_empty_or_done_decoding.create_emit_event__locked(
                    target_duration=PREFILL_DURATION
                )
            executor.abort_aware_wait(event)
            if self._buffer.duration <= 0:
                executor.abort()
            executor.finish()

        prefill_task = FnTask(_prefill)

        Thread(target=prefill_task.run_pending, daemon=True).start()
        return prefill_task.future

    def seek(self, timepoint: float) -> Task.Future:
        assert timepoint >= 0

        task = Decoder.SeekTask(timepoint)
        with self._mutex__shared_with_task_queue:
            if self._is_killed:
                task.future.abort()
            else:
                self._logger.debug("Adding task", details=task)
                self._context.tasks.add_task__locked(task)
        return task.future

    def kill(self) -> Task.Future:
        task = Decoder.KillTask()
        with self._mutex__shared_with_task_queue:
            if self._is_killed:
                task.finish_without_running()
            else:
                self._logger.debug("Adding task", details=task)
                self._context.tasks.add_task__locked(task)
        return task.future

    def apply_new_media_constraints(self, new_constraints: AudioConstraints | None) -> Task.Future:
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
                    parent=node.AccurateSeekNode(
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
        ),
        context=context,
        thread_spawner=thread_spawner,
    )
