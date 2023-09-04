from bisect import bisect_right
from dataclasses import dataclass

import PyQt5.QtWidgets as QtW
from PyQt5.QtCore import Qt


from jerboa.media.source import (
    MediaType,
    MediaSource,
    MediaStreamSource,
    AudioSourceVariant,
    VideoSourceVariant,
)
from jerboa.gui.common import LabelValuePair

DEFAULT_SAMPLE_RATE = 44100
DEFAULT_RESOLUTION = 720


@dataclass(order=True, frozen=True)
class AudioFeatures:
    sample_rate: int | None
    channels: int | None

    def __str__(self) -> str:
        return f"{self.channels}x {self.sample_rate}"

    @staticmethod
    def from_variant(variant: AudioSourceVariant) -> "AudioFeatures":
        return AudioFeatures(sample_rate=variant.sample_rate, channels=variant.channels)

    @staticmethod
    def find_default(features_alternatives: list["AudioFeatures"]) -> int:
        return bisect_right(
            features_alternatives,
            DEFAULT_SAMPLE_RATE,
            key=lambda audio_variant: audio_variant.sample_rate,
        )


@dataclass(order=True, frozen=True)
class VideoFeatures:
    width: int | None
    height: int | None
    fps: float | None

    def __str__(self) -> str:
        return f"{self.width}x{self.height} at {self.fps:.1f}fps"

    @staticmethod
    def from_variant(variant: VideoSourceVariant) -> "VideoFeatures":
        return VideoFeatures(width=variant.width, height=variant.height, fps=variant.fps)

    @staticmethod
    def find_default(features_alternatives: list["VideoFeatures"]) -> int:
        return bisect_right(
            features_alternatives,
            DEFAULT_RESOLUTION,
            key=lambda video_variant: min(video_variant.width, video_variant.height),
        )


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
        self._variant_groups: list[int] = []

        self._variants_combobox.clear()

    def set_stream_source(self, stream_source: MediaStreamSource) -> None:
        self.reset()

        Features = None
        if stream_source.media_type == MediaType.AUDIO:
            Features = AudioFeatures
        elif stream_source.media_type == MediaType.VIDEO:
            Features = VideoFeatures

        if len(stream_source.variants) > 0 and Features is not None:
            variants_by_features: dict[AudioFeatures | VideoFeatures, list[int]] = {}
            for idx, variant in enumerate(stream_source.variants):
                variants_by_features.setdefault(Features.from_variant(variant), []).append(idx)

            # sort by featuers in an ascending order
            features_alternatives = sorted(list(variants_by_features.keys()))
            self._variant_groups = [
                variants_by_features[features] for features in features_alternatives
            ]

            default_idx = Features.find_default(features_alternatives)
            default_idx = max(0, default_idx - 1)

            self._variants_combobox.addItems([str(features) for features in features_alternatives])
            self._variants_combobox.setCurrentIndex(default_idx)

    def get_current_variant_group(self) -> list[int]:
        idx = self._variants_combobox.currentIndex()
        return self._variant_groups[idx] if idx >= 0 else []


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
            self._media_source.audio.selected_variants = (
                self._audio_variant_selector.get_current_variant_group()
            )
            self._media_source.video.selected_variants = (
                self._video_variant_selector.get_current_variant_group()
            )
        return self._media_source
