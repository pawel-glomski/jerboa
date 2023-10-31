from threading import Lock, Condition

from jerboa.core.multithreading import ThreadSpawner
from jerboa.media.core import MediaType
from .buffer import AudioBuffer, VideoBuffer, create_buffer
from .task_queue import Task, TaskQueue
from . import pipeline

BUFFER_DURATION = 10.5  # in seconds


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
        ...

    class StopTask(Task):
        ...

    def __init__(self, decoding_pipeline: pipeline.Pipeline, thread_spawner: ThreadSpawner):
        self._decoding_pipeline = decoding_pipeline
        self._thread_spawner = thread_spawner

        self._buffer: AudioBuffer | VideoBuffer | None = None

        self._mutex = Lock()

        self._is_done = False
        self._is_done_condition = Condition(self._mutex)
        self._buffer_not_empty_or_done_decoding = Condition(self._mutex)

        self._tasks = TaskQueue(mutex=self._mutex)

        self._buffer_not_full_or_task_added = Condition(self._mutex)
        self._tasks.add_on_task_added_callback(self._buffer_not_full_or_task_added.notify)

    @property
    def is_done(self) -> bool:
        return self._is_done

    def stop(self, wait: bool = False) -> None:
        with self._mutex:
            if self._decoding_pipeline.initialized:
                self._tasks.add_task__already_locked(JbDecoder.StopTask())
                self._buffer_not_empty_or_done_decoding.notify()
                self._decoding_pipeline.add_task(JbDecoder.StopTask())
                if wait:
                    self._is_done_condition.wait_for(lambda: self.is_done)

    def start(self, media: pipeline.MediaContext, start_timepoint: float | None = None):
        self.stop(wait=True)

        with self._mutex:
            self._is_done = False
            self._thread_spawner.start(
                self.__decoding,
                media,
                start_timepoint,
            )

    def __decoding(self, media: pipeline.MediaContext, start_timepoint: float | None = None):
        self._buffer = create_buffer(
            media.presentation_config,
            BUFFER_DURATION,
        )
        self._decoding_pipeline.init(media=media, start_timepoint=start_timepoint)

        while True:
            try:
                self._tasks.run_all()

                frame = self._decoding_pipeline.pull()
                if frame is None:
                    with self._mutex:
                        self._is_done = True
                        self._is_done_condition.notify_all()
                        self._buffer_not_empty_or_done_decoding.notify_all()
                        break
                self.__decoding__put_frame_to_buffer(frame)
            except JbDecoder.StopTask:
                with self._mutex:
                    self._is_done = True
                    self._decoding_pipeline.deinitialize()
                    self._is_done_condition.notify_all()
                    self._buffer_not_empty_or_done_decoding.notify_all()
                break

    def __decoding__put_frame_to_buffer(
        self, frame: pipeline.frame.JbAudioFrame | pipeline.frame.JbVideoFrame | None
    ):
        with self._mutex:
            self._buffer_not_full_or_task_added.wait_for(
                lambda: not self._buffer.is_full() or not self._tasks.is_empty()
            )
            self._tasks.run_all__already_locked()

            self._buffer.put(frame)
            self._buffer_not_empty_or_done_decoding.notify()

    def pop(
        self, *args, timeout: float | None = None
    ) -> pipeline.frame.JbAudioFrame | pipeline.frame.JbVideoFrame | None:
        frame = None
        with self._mutex:
            if self._buffer_not_empty_or_done_decoding.wait_for(
                lambda: self._buffer is not None and not self._buffer.is_empty() or self.is_done,
                timeout=timeout,
            ):
                if not self._buffer.is_empty():
                    frame = self._buffer.pop(*args)
                    self._buffer_not_empty_or_done_decoding.notify()
                    return frame
            else:
                raise TimeoutError()
        return frame
