from threading import Lock, Condition

from jerboa.core.multithreading import ThreadSpawner
from jerboa.media.core import MediaType, AudioConfig, VideoConfig
from .buffer import AudioBuffer, VideoBuffer, create_buffer
from .task_queue import Task, TaskQueue
from . import pipeline

BUFFER_DURATION = 10  # in seconds


def create_decoding_pipeline(media_type: MediaType):
    if media_type == MediaType.AUDIO:
        return pipeline.Pipeline(
            media_type=MediaType.AUDIO,
            output_node=pipeline.node.AudioPresentationReformattingNode(
                parent=pipeline.node.FrameMappingNode(
                    parent=pipeline.node.FrameMappingPreparationNode(
                        parent=pipeline.node.AudioIntermediateReformattingNode(
                            parent=pipeline.node.AccurateSeekNode(
                                parent=pipeline.node.TimedAudioFrameCreationNode(
                                    parent=pipeline.node.AudioFrameTimingCorrectionNode(
                                        parent=pipeline.node.DecodingNode(
                                            parent=pipeline.node.KeyframeIntervalWatcherNode(
                                                parent=pipeline.node.DemuxingNode(),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    return pipeline.Pipeline(
        media_type=MediaType.VIDEO,
        output_node=pipeline.node.VideoPresentationReformattingNode(
            parent=pipeline.node.FrameMappingNode(
                parent=pipeline.node.FrameMappingPreparationNode(
                    parent=pipeline.node.TimedVideoFrameCreationNode(
                        parent=pipeline.node.DecodingNode(
                            parent=pipeline.node.KeyframeIntervalWatcherNode(
                                parent=pipeline.node.DemuxingNode(),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


class JbDecoder:
    class DiscardFrameTask(Task):
        def run(self) -> None:
            pass

    class StopTask(Task):
        ...

    def __init__(self, decoding_pipeline: pipeline.Pipeline, thread_spawner: ThreadSpawner):
        self._decoding_pipeline = decoding_pipeline
        self._thread_spawner = thread_spawner

        self._buffer: AudioBuffer | VideoBuffer | None = None

        self._mutex = Lock()

        self._is_done = True
        self._is_not_running_condition = Condition(self._mutex)
        self._buffer_not_empty_or_done_decoding = Condition(self._mutex)

        self._tasks = TaskQueue(mutex=self._mutex)
        self._buffer_not_full_or_task_added = Condition(self._mutex)
        self._tasks.add_on_task_added_callback(self._buffer_not_full_or_task_added.notify)

    @property
    def media_type(self) -> MediaType:
        return self._decoding_pipeline.media_type

    @property
    def presentation_media_config(self) -> AudioConfig | VideoConfig:
        return self._decoding_pipeline.presentation_media_config

    @property
    def is_running(self) -> bool:
        return self._decoding_pipeline.initialized

    @property
    def is_done(self) -> bool:
        return self._is_done

    def stop(self) -> None:
        with self._mutex:
            if self._decoding_pipeline.initialized:
                self._tasks.add_task__without_lock(JbDecoder.StopTask())
                self._decoding_pipeline.add_task(JbDecoder.StopTask())
                self._is_not_running_condition.wait_for(lambda: not self.is_running)

    def start(
        self,
        media: pipeline.context.MediaContext,
        start_timepoint: float | None = None,
    ) -> None:
        self.stop()

        with self._mutex:
            assert not self.is_running

            self._buffer = create_buffer(media.presentation_config, BUFFER_DURATION)
            self._decoding_pipeline.init(media=media, start_timepoint=start_timepoint)
            self._is_done = False

            self._thread_spawner.start(self.__decoding)

    def __decoding(
        self,
    ) -> None:
        assert self.is_running
        while True:
            try:
                self._tasks.run_all()  # this must be before the `pull()` call

                frame = self._decoding_pipeline.pull()
                if frame is not None:
                    self.__decoding__put_frame_to_buffer(frame)
                else:
                    with self._mutex:
                        self._is_done = True
                        self._buffer_not_empty_or_done_decoding.notify_all()
                    self._tasks.wait_for_and_run_task()

            except Exception as exc:
                with self._mutex:
                    self._decoding_pipeline.deinitialize()
                    self._buffer = None
                    self._is_done = True

                    self._is_not_running_condition.notify_all()
                    self._buffer_not_empty_or_done_decoding.notify_all()

                if isinstance(exc, JbDecoder.StopTask):
                    break
                else:
                    raise exc

    def __decoding__put_frame_to_buffer(
        self, frame: pipeline.frame.JbAudioFrame | pipeline.frame.JbVideoFrame | None
    ) -> None:
        with self._mutex:
            self._buffer_not_full_or_task_added.wait_for(
                lambda: not self._buffer.is_full() or not self._tasks.is_empty()
            )
            if not self._buffer.is_full():
                self._buffer.put(frame)
                self._buffer_not_empty_or_done_decoding.notify()
            # else a task has been added, which will be handled in the main loop

    def pop(
        self,
        /,
        *args,
        timeout: float | None = None,
    ) -> pipeline.frame.JbAudioFrame | pipeline.frame.JbVideoFrame | None:
        frame = None
        with self._mutex:
            if self._buffer_not_empty_or_done_decoding.wait_for(
                lambda: self._buffer is not None and not self._buffer.is_empty() or self.is_done,
                timeout=timeout,
            ):
                if self._buffer is not None and not self._buffer.is_empty():
                    frame = self._buffer.pop(*args)
                    self._buffer_not_full_or_task_added.notify()
                    return frame
            else:
                raise TimeoutError()
        return frame
