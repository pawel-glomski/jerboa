import PySide6.QtWidgets as QtW
from PySide6.QtCore import Qt


from jerboa.media.source import MediaSource, MediaStreamSource
from jerboa.gui.common.property import LabelValuePair


class StreamVariantSelector(QtW.QWidget):
    def __init__(self, label_text: str):
        super().__init__()
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

        self._variants_combobox_label = QtW.QLabel(label_text)
        self._variants_combobox = QtW.QComboBox()

        layout = QtW.QHBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._variants_combobox_label)
        layout.addWidget(self._variants_combobox)
        self.setLayout(layout)

        self.reset()

    def reset(self) -> None:
        self._variants_combobox.clear()

    def set_stream_source(self, stream_source: MediaStreamSource) -> None:
        self.reset()
        if stream_source.is_available:
            self._variants_combobox.addItems(
                [str(features) for features in stream_source.features_list]
            )
            self._variants_combobox.setCurrentIndex(stream_source.default_features_index)

    def get_current_variant_index(self) -> int | None:
        idx = self._variants_combobox.currentIndex()
        return idx if idx >= 0 else None


class MediaSourceResolver(QtW.QWidget):
    def __init__(
        self,
        title_text: str,
        audio_variant_selector: StreamVariantSelector,
        video_variant_selector: StreamVariantSelector,
    ):
        super().__init__()

        self._title = LabelValuePair(title_text)
        self._audio_variant_selector = audio_variant_selector
        self._video_variant_selector = video_variant_selector

        streams_selection_layout = QtW.QHBoxLayout()
        streams_selection_layout.addWidget(self._audio_variant_selector)
        streams_selection_layout.addWidget(self._video_variant_selector)

        main_layout = QtW.QVBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        main_layout.addWidget(self._title)
        main_layout.addLayout(streams_selection_layout)
        self.setLayout(main_layout)

    def reset(self) -> None:
        self._media_source = None

        self._title.set_value("")
        self._audio_variant_selector.reset()
        self._video_variant_selector.reset()

    def set_media_source(self, media_source: MediaSource):
        self._media_source = media_source

        self._title.set_value(media_source.title)
        self._audio_variant_selector.set_stream_source(media_source.audio)
        self._video_variant_selector.set_stream_source(media_source.video)

    def get_resolved_media_source(self) -> MediaSource | None:
        if self._media_source is not None:
            self._media_source.audio.selected_features_index = (
                self._audio_variant_selector.get_current_variant_index()
            )
            self._media_source.video.selected_features_index = (
                self._video_variant_selector.get_current_variant_index()
            )
        return self._media_source
