from typing import Any

from jerboa.media.core import MediaType, AudioConfig, VideoConfig
from .node import Node
from .context import MediaContext, DecodingContext, SeekTask


class Pipeline:
    def __init__(self, media_type: MediaType, output_node: Node) -> None:
        self._media_type = media_type

        self._output_node = output_node
        self._root_node = self._output_node
        while self._root_node.parent is not None:
            self._root_node = self._root_node.parent

        self._context: DecodingContext | None = None

    @property
    def media_type(self) -> MediaType:
        return self._media_type

    @property
    def presentation_media_config(self) -> AudioConfig | VideoConfig | None:
        if self.initialized:
            return self._context.media.presentation_config
        return None

    @property
    def context(self) -> DecodingContext:
        return self._context

    @property
    def initialized(self) -> bool:
        return self._context is not None

    def deinitialize(self) -> None:
        self._context = None

    def init(self, media: MediaContext, start_timepoint: float | None = None) -> None:
        assert media.av.container == media.av.stream.container
        assert MediaType(media.av.stream.type) == self._media_type

        self._context = DecodingContext(media=media)
        self._root_node.reset(self._context, hard=True, recursive=True)

        self._seek(start_timepoint or media.av.start_timepoint or 0)

    def _seek(self, timepoint: float) -> None:
        assert timepoint >= 0

        self._context.media.av.container.seek(
            round(timepoint / self._context.media.av.stream.time_base),
            stream=self._context.media.av.stream,
        )
        self._context.last_seek_timepoint = timepoint
        self._context.min_timepoint = timepoint
        self._root_node.reset(self._context, hard=False, recursive=True)

    def add_task(self, task: Exception) -> None:
        assert self.initialized, "Cannot add task to uninitialized pipeline"

        self._context.tasks.add_task(task)

    def pull(self) -> Any | None:
        assert self.initialized, "Cannot run uninitialized pipeline"
        while True:
            try:
                self._context.tasks.run_all()

                return self._output_node.pull_as_leaf(self._context)
            except SeekTask as seek_task:
                self._seek(seek_task.timepoint)
