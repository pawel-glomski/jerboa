from pathlib import Path
from jerboa.media import MediaType

TEST_REC_PATH = str(Path("tests/test_recordings/sintel.mp4").resolve())
TEST_REC_CHANNELS = {MediaType.Video: 0, MediaType.Audio: 1}
