from typing import Optional

from dataclasses import dataclass, field

from jerboa.media import MediaType


@dataclass
class MediaStreamVariant:
    path: str
    single_stream: bool
    protocol_or_container: str
    # codec_name: str
    bit_rate: float


@dataclass
class AudioSourceVariant(MediaStreamVariant):
    sample_rate: int
    channels: int

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


@dataclass
class VideoSourceVariant(MediaStreamVariant):
    fps: int
    width: int
    height: int

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


@dataclass
class MediaStreamSource:
    media_type: MediaType
    selected_variants: list[int] = field(default_factory=list)
    variants: list[AudioSourceVariant | VideoSourceVariant] = field(default_factory=list)

    @property
    def is_available(self) -> bool:
        return len(self.selected_variants) > 0 or len(self.variants) > 0

    @property
    def is_resolved(self) -> bool:
        return len(self.selected_variants) > 0 or len(self.variants) == 0

    @staticmethod
    def from_yt_dlp_dict(info: dict, media_type: MediaType) -> "MediaStreamSource":
        mss = MediaStreamSource(media_type=media_type)

        formats = []
        variant = None
        if media_type == MediaType.AUDIO:
            formats = MediaStreamSource._get_audio_formats(info["formats"])
            variant = AudioSourceVariant
        elif media_type == MediaType.VIDEO:
            formats = MediaStreamSource._get_video_formats(info["formats"])
            variant = VideoSourceVariant

        mss.variants = [variant.from_yt_dlp_dict(fmt_info) for fmt_info in formats]
        mss.variants = [fmt for fmt in mss.variants if fmt is not None]
        if len(mss.variants) == 1:
            mss.selected_variants = [0]

        return mss

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
        mss = MediaStreamSource(media_type=media_type)

        variant = None
        if media_type == MediaType.AUDIO:
            variant = AudioSourceVariant.from_av_container(av_container)
        elif media_type == MediaType.VIDEO:
            variant = VideoSourceVariant.from_av_container(av_container)

        if variant is not None:
            mss.variants = [variant]
            mss.selected_variants = [0]

        return mss


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
