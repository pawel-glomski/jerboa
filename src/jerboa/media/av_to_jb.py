import av

from .core import AudioChannelLayout


def audio_channel_layout(av_layout: av.AudioLayout):
    result = AudioChannelLayout.NONE

    for channel in av_layout.channels:
        match channel.name.upper():
            case "LFE":
                result |= AudioChannelLayout.CHANNEL_LFE
            case "FL":
                result |= AudioChannelLayout.CHANNEL_FRONT_LEFT
            case "FR":
                result |= AudioChannelLayout.CHANNEL_FRONT_RIGHT
            case "FC":
                result |= AudioChannelLayout.CHANNEL_FRONT_CENTER
            case "BL":
                result |= AudioChannelLayout.CHANNEL_BACK_LEFT
            case "BR":
                result |= AudioChannelLayout.CHANNEL_BACK_RIGHT
            case "SL":
                result |= AudioChannelLayout.CHANNEL_SIDE_LEFT
            case "SR":
                result |= AudioChannelLayout.CHANNEL_SIDE_RIGHT
            case _:
                pass

    if result == AudioChannelLayout.NONE:
        # at least let's try mono
        return AudioChannelLayout.LAYOUT_MONO
    return result
