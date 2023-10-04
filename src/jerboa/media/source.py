from typing import Optional

from bisect import bisect_right
from dataclasses import dataclass

from jerboa.media.core import MediaType

DEFAULT_SAMPLE_RATE = 44100
DEFAULT_RESOLUTION = 720


@dataclass(order=True, frozen=True)
class AudioFeatures:
    sample_rate: int | None
    channels: int | None

    def __str__(self) -> str:
        return f"{self.channels}x {self.sample_rate}"

    @staticmethod
    def find_default(features_alternatives: list["AudioFeatures"]) -> int | None:
        if features_alternatives:
            idx = bisect_right(
                features_alternatives,
                DEFAULT_SAMPLE_RATE,
                key=lambda audio_variant: audio_variant.sample_rate,
            )
            return max(0, idx - 1)
        return None


@dataclass(order=True, frozen=True)
class VideoFeatures:
    width: int | None
    height: int | None
    fps: float | None

    def __str__(self) -> str:
        return f"{self.width}x{self.height}, {self.fps:.1f}fps"

    @staticmethod
    def find_default(features_alternatives: list["VideoFeatures"]) -> int | None:
        if features_alternatives:
            idx = bisect_right(
                features_alternatives,
                DEFAULT_RESOLUTION,
                key=lambda video_variant: min(video_variant.width, video_variant.height),
            )
            return max(0, idx - 1)
        return None


@dataclass(frozen=True)
class MediaStreamVariant:
    path: str
    single_stream: bool
    protocol_or_container: str
    # codec_name: str
    bit_rate: float
    grouping_features: AudioFeatures | VideoFeatures


@dataclass(frozen=True)
class AudioSourceVariant(MediaStreamVariant):
    sample_rate: int
    channels: int

    @property
    def media_type(self) -> MediaType:
        return MediaType.AUDIO

    @staticmethod
    def from_yt_dlp_dict(info: dict) -> Optional["AudioSourceVariant"]:
        if "url" in info:
            return AudioSourceVariant(
                path=info.get("url"),
                single_stream=not VideoSourceVariant.is_video(info),
                protocol_or_container=f"{info.get('protocol')}|{info.get('container')}",
                bit_rate=info.get("tbr"),
                sample_rate=info.get("asr"),
                channels=info.get("audio_channels"),
                grouping_features=AudioFeatures(
                    sample_rate=info.get("asr"),
                    channels=info.get("audio_channels"),
                ),
            )
        return None

    @staticmethod
    def from_av_container(av_container) -> Optional["AudioSourceVariant"]:
        if av_container.streams.audio:
            stream = av_container.streams.audio[0]
            return AudioSourceVariant(
                path=av_container.name,
                single_stream=len(av_container.streams) > 1,
                protocol_or_container="",
                bit_rate=stream.bit_rate,
                sample_rate=stream.sample_rate,
                channels=stream.channels,
                grouping_features=AudioFeatures(
                    sample_rate=stream.sample_rate,
                    channels=stream.channels,
                ),
            )
        return None

    @staticmethod
    def is_audio(fmt: dict) -> bool:
        return (
            fmt.get("resolution") == "audio only"
            or fmt.get("acodec") not in [None, "none"]
            or fmt.get("audio_ext") not in [None, "none"]
            or fmt.get("abr") not in [None, "none", 0]
            or fmt.get("asr") not in [None, "none", 0]
        )

    @staticmethod
    def is_audio_strict(fmt: dict) -> bool:
        try:
            int(fmt.get("asr"))
        except (ValueError, TypeError):
            return False
        return True


@dataclass(frozen=True)
class VideoSourceVariant(MediaStreamVariant):
    fps: int
    width: int
    height: int

    @property
    def media_type(self) -> MediaType:
        return MediaType.VIDEO

    @staticmethod
    def from_yt_dlp_dict(info: dict) -> Optional["VideoSourceVariant"]:
        if "url" in info:
            return VideoSourceVariant(
                path=info.get("url"),
                single_stream=not AudioSourceVariant.is_audio(info),
                protocol_or_container=f"{info.get('protocol')}|{info.get('container')}",
                bit_rate=info.get("tbr"),
                fps=info.get("fps"),
                width=info.get("width"),
                height=info.get("height"),
                grouping_features=VideoFeatures(
                    width=info.get("width"),
                    height=info.get("height"),
                    fps=info.get("fps"),
                ),
            )
        return None

    @staticmethod
    def from_av_container(av_container) -> Optional["VideoSourceVariant"]:
        if av_container.streams.video:
            stream = av_container.streams.video[0]
            return VideoSourceVariant(
                path=av_container.name,
                single_stream=len(av_container.streams) > 1,
                protocol_or_container="",
                bit_rate=stream.bit_rate,
                fps=stream.guessed_rate,
                width=stream.width,
                height=stream.height,
                grouping_features=VideoFeatures(
                    width=stream.width,
                    height=stream.height,
                    fps=stream.guessed_rate,
                ),
            )
        return None

    @staticmethod
    def is_video(fmt: dict) -> bool:
        return (
            fmt.get("vcodec", "none") != "none"
            or fmt.get("resolution", "audio only") != "audio only"
            or fmt.get("video_ext", "none") != "none"
            or (fmt.get("vbr") is not None and fmt.get("vbr", 0) != 0)
        )

    @staticmethod
    def is_video_strict(fmt: dict) -> bool:
        try:
            int(fmt.get("width"))
            int(fmt.get("height"))
        except (ValueError, TypeError):
            return False
        return True

    @staticmethod
    def is_storyboard(fmt: dict) -> bool:
        return (
            "storyboard" in fmt.get("format_note", "")
            or fmt.get("columns") is not None
            or fmt.get("rows") is not None
            or fmt.get("protocol") == "mhtml"
            or fmt.get("ext") == "mhtml"
        )


class MediaStreamSource:
    def __init__(
        self,
        variants: list[AudioSourceVariant | VideoSourceVariant],
    ):
        self._media_type = variants[0].media_type if variants else None
        assert all(variant.media_type == self._media_type for variant in variants)

        self._variants_by_features = dict[
            AudioFeatures | VideoFeatures, list[AudioSourceVariant | VideoSourceVariant]
        ]()

        for variant in variants:
            self._variants_by_features.setdefault(variant.grouping_features, []).append(variant)

        # sort by features in an ascending order
        self._features_list = sorted(list(self._variants_by_features.keys()))

        if variants:
            Features = type(variants[0].grouping_features)
            self._default_features_index = Features.find_default(self._features_list)
        else:
            self._default_features_index = None

        # there is nothing to choose from if there is only 1 variant, so the source is resolved
        self.selected_features_index = 0 if len(self._features_list) == 1 else None

    @property
    def media_type(self) -> MediaType:
        return self._media_type

    @property
    def is_available(self) -> bool:
        return self.selected_features_index is not None or len(self._features_list) > 0

    @property
    def is_resolved(self) -> bool:
        return self.selected_features_index is not None or len(self._features_list) == 0

    @property
    def features_list(self) -> list[AudioFeatures] | list[VideoFeatures]:
        return self._features_list

    @property
    def default_features_index(self) -> int | None:
        return self._default_features_index

    @property
    def selected_variant_group(self) -> list[AudioSourceVariant] | list[VideoSourceVariant] | None:
        if self.selected_features_index is not None:
            return self._variants_by_features[self._features_list[self.selected_features_index]]
        return None

    @staticmethod
    def from_yt_dlp_dict(info: dict, media_type: MediaType) -> "MediaStreamSource":
        formats = []
        Variant = None
        if media_type == MediaType.AUDIO:
            formats = MediaStreamSource._get_audio_formats(info["formats"])
            Variant = AudioSourceVariant
        elif media_type == MediaType.VIDEO:
            formats = MediaStreamSource._get_video_formats(info["formats"])
            Variant = VideoSourceVariant

        variants = [Variant.from_yt_dlp_dict(fmt_info) for fmt_info in formats]
        variants = [fmt for fmt in variants if fmt is not None]

        return MediaStreamSource(variants)

    @staticmethod
    def _get_audio_formats(formats: list[dict]) -> list[dict]:
        audio_all = [fmt for fmt in formats if AudioSourceVariant.is_audio(fmt)]
        audio_strict = [fmt for fmt in audio_all if AudioSourceVariant.is_audio_strict(fmt)]

        return audio_strict or audio_all

    @staticmethod
    def _get_video_formats(formats: list[dict]) -> list[dict]:
        video_all = [fmt for fmt in formats if VideoSourceVariant.is_video(fmt)]
        video_strict = [fmt for fmt in video_all if VideoSourceVariant.is_video_strict(fmt)]
        video_stricter = [fmt for fmt in video_strict if not VideoSourceVariant.is_storyboard(fmt)]

        return video_stricter or video_strict or video_all

    @staticmethod
    def from_av_container(av_container, media_type: MediaType) -> "MediaStreamSource":
        variant = None
        if media_type == MediaType.AUDIO:
            variant = AudioSourceVariant.from_av_container(av_container)
        elif media_type == MediaType.VIDEO:
            variant = VideoSourceVariant.from_av_container(av_container)

        return MediaStreamSource([variant] if variant is not None else [])


@dataclass
class MediaSource:
    title: str
    audio: MediaStreamSource
    video: MediaStreamSource

    @property
    def is_resolved(self) -> bool:
        return self.audio.is_resolved and self.video.is_resolved

    @staticmethod
    def from_yt_dlp_dict(info: dict) -> "MediaSource":
        if "entries" in info:
            raise ValueError("Cannot play a playlist")

        return MediaSource(
            title=info["title"],
            audio=MediaStreamSource.from_yt_dlp_dict(info, MediaType.AUDIO),
            video=MediaStreamSource.from_yt_dlp_dict(info, MediaType.VIDEO),
        )

    @staticmethod
    def from_av_container(av_container) -> "MediaSource":
        audio_source = MediaStreamSource.from_av_container(av_container, MediaType.AUDIO)
        video_source = MediaStreamSource.from_av_container(av_container, MediaType.VIDEO)

        return MediaSource(title=av_container.name, audio=audio_source, video=video_source)
