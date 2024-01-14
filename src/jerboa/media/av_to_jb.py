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
