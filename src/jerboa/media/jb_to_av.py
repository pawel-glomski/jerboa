import av
import numpy as np

from .core import AudioConstraints, VideoConfig


def audio_sample_format(sample_format_jb: AudioConstraints.SampleFormat) -> av.AudioFormat:
    match sample_format_jb:
        case AudioConstraints.SampleFormat.U8:
            av_name = "u8"
        case AudioConstraints.SampleFormat.S16:
            av_name = "s16"
        case AudioConstraints.SampleFormat.S32:
            av_name = "s32"
        case AudioConstraints.SampleFormat.F32:
            av_name = "flt"
        case _:
            raise ValueError(f"Unrecognized sample format: {sample_format_jb}")

    av_name += "p" if sample_format_jb.is_planar else ""

    return av.AudioFormat(av_name)


def audio_channel_layout(channel_layout_jb: AudioConstraints.ChannelLayout) -> av.AudioLayout:
    match channel_layout_jb:
        case AudioConstraints.ChannelLayout.LAYOUT_MONO:
            av_name = "mono"
        case AudioConstraints.ChannelLayout.LAYOUT_STEREO:
            av_name = "stereo"
        case AudioConstraints.ChannelLayout.LAYOUT_2_1:
            av_name = "2.1"
        case AudioConstraints.ChannelLayout.LAYOUT_3_0:
            av_name = "3.0"
        case AudioConstraints.ChannelLayout.LAYOUT_3_1:
            av_name = "3.1"
        case AudioConstraints.ChannelLayout.LAYOUT_SURROUND_5_0:
            av_name = "5.0"
        case AudioConstraints.ChannelLayout.LAYOUT_SURROUND_5_1:
            av_name = "5.1"
        case AudioConstraints.ChannelLayout.LAYOUT_SURROUND_7_0:
            av_name = "7.0"
        case AudioConstraints.ChannelLayout.LAYOUT_SURROUND_7_1:
            av_name = "7.1"
        case _:
            raise ValueError(f"Unrecognized channel layout: {channel_layout_jb}")

    return av.AudioLayout(av_name)


def video_pixel_format(pixel_format_jb: VideoConfig.PixelFormat) -> av.VideoFormat:
    match pixel_format_jb:
        case VideoConfig.PixelFormat.RGBA8888:
            av_name = "rgba"
        case _:
            raise ValueError(f"Unrecognized pixel format: {pixel_format_jb}")

    return av.VideoFormat(av_name)
