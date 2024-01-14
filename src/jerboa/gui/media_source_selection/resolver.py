# Jerboa - AI-powered media player
# Copyright (C) 2023 Paweł Głomski

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


import PySide6.QtWidgets as QtW
from PySide6.QtCore import Qt


from jerboa.media.source import MediaSource, MediaStreamSource


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

        self._title = QtW.QLineEdit()
        self._title.setReadOnly(True)

        title_layout = QtW.QHBoxLayout()
        title_layout.addWidget(QtW.QLabel(title_text))
        title_layout.addWidget(self._title)

        streams_selection_layout = QtW.QHBoxLayout()
        streams_selection_layout.addWidget(audio_variant_selector)
        streams_selection_layout.addWidget(video_variant_selector)
        self._audio_variant_selector = audio_variant_selector
        self._video_variant_selector = video_variant_selector

        main_layout = QtW.QVBoxLayout()
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        main_layout.addLayout(title_layout)
        main_layout.addLayout(streams_selection_layout)
        self.setLayout(main_layout)

    def reset(self) -> None:
        self._media_source = None

        self._title.setText("")
        self._audio_variant_selector.reset()
        self._video_variant_selector.reset()

    def set_media_source(self, media_source: MediaSource):
        self._media_source = media_source

        self._title.setText(media_source.title)
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
