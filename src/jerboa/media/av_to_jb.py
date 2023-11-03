import av

from .core import AudioConstraints


def audio_channel_layout(av_layout: av.AudioLayout):
    result = AudioConstraints.ChannelLayout.NONE

    for channel in av_layout.channels:
        match channel.name.upper():
            case "LFE":
                result |= AudioConstraints.ChannelLayout.CHANNEL_LFE
            case "FL":
                result |= AudioConstraints.ChannelLayout.CHANNEL_FRONT_LEFT
            case "FR":
                result |= AudioConstraints.ChannelLayout.CHANNEL_FRONT_RIGHT
            case "FC":
                result |= AudioConstraints.ChannelLayout.CHANNEL_FRONT_CENTER
            case "BL":
                result |= AudioConstraints.ChannelLayout.CHANNEL_BACK_LEFT
            case "BR":
                result |= AudioConstraints.ChannelLayout.CHANNEL_BACK_RIGHT
            case "SL":
                result |= AudioConstraints.ChannelLayout.CHANNEL_SIDE_LEFT
            case "SR":
                result |= AudioConstraints.ChannelLayout.CHANNEL_SIDE_RIGHT
            case _:
                pass

    if result == AudioConstraints.ChannelLayout.NONE:
        # at least let's try mono
        return AudioConstraints.ChannelLayout.LAYOUT_MONO
    return result
