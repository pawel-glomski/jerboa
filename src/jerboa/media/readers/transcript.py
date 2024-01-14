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


import webvtt

from typing import Callable, List
from pathlib import Path

from jerboa.analysis.utils.tokenization import EditToken

REGISTERED_READERS: List[Callable[[str], List[EditToken]]] = []


def read_transcript(sub_path: str) -> List[EditToken]:
    """Reads transcript of a recording

    Args:
        sub_path (str): Path to the transcript

    Returns:
        List[EditToken]: Tokenized transcript
    """
    path = Path(sub_path).resolve()
    for reader, extensions in REGISTERED_READERS:
        if path.suffix[1:].lower() in extensions:
            transcript = reader(sub_path)
            if transcript is not None:
                return transcript
    return None


def transcript_reader(extensions: List[str]) -> Callable:
    """Registers a new reader function. New readers should reside in this file

    Args:
        extensions (List[str]): A list of extensions supported by this reader
    """

    def register(reader_func: Callable[[str], List[EditToken]]):
        assert isinstance(extensions, list)
        REGISTERED_READERS.append((reader_func, [e.lower() for e in extensions]))
        return reader_func

    return register


@transcript_reader(extensions=["vtt"])
def vtt_reader(sub_path: str) -> List[EditToken]:
    vtt = webvtt.read(sub_path)
    transcript = [EditToken(c.text, c.start_in_seconds, c.end_in_seconds) for c in vtt.captions]
    transcript = [t for t in transcript if len(t.text) > 0]
    return transcript
