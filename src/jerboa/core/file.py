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


import os

from pathlib import Path
from dataclasses import dataclass

from PySide6.QtCore import QUrl

from jerboa.log import logger

_HOME_PATH_VAR_NAME = "JERBOA_HOME"
_HOME_PATH_DEFAULT = Path("~/.jerboa/")
HOME_PATH = Path(os.environ.get(_HOME_PATH_VAR_NAME, _HOME_PATH_DEFAULT)).resolve()

SETTINGS_PATH = HOME_PATH / "settings.json"
CACHE_DIR_PATH_DEFAULT = Path("~/.cache")


class FileManager:
    def __init__(self, cache_dir_path: str):
        self._cache_dir_path = Path(cache_dir_path).resolve()

        if not self._cache_dir_path.is_dir():
            logger.error(
                f"Cache dir path ({self._cache_dir_path}) is not a directory. "
                f"Using the default instead ({CACHE_DIR_PATH_DEFAULT})"
            )
            self._cache_dir_path = CACHE_DIR_PATH_DEFAULT

        for _ in range(2):
            try:
                self._cache_dir_path.mkdir(parents=True, exist_ok=True)
                test_file_path = self._cache_dir_path / "_write_test"
                with open(test_file_path, "wb"):
                    pass
                test_file_path.unlink()
                break
            except PermissionError:
                if self._cache_dir_path is CACHE_DIR_PATH_DEFAULT:
                    raise
                logger.error("No permissions to modify the cache dir, using the default instead")
                self._cache_dir_path = CACHE_DIR_PATH_DEFAULT

    @property
    def settings_path(self) -> Path:
        return SETTINGS_PATH

    @property
    def cache_dir_path(self) -> Path:
        return self._cache_dir_path

    def create_cache_dir(self, dir_path: str) -> Path:
        if not dir_path.startswith("."):  # relative, make it absolute
            dir_path = self.cache_dir_path / dir_path
        return _create_cache_dir__absolute(dir_path)

    def _create_cache_dir__absolute(self, absolute_dir_path: str) -> Path:
        dir_path = Path(absolute_dir_path).resolve()
        assert str(CACHE_DIR_PATH) in str(dir_path)

        if not dir_path.exists():
            os.makedirs(dir_path)
        assert dir_path.exists() and dir_path.is_dir()
        return dir_path


# ------------------------------------------------------------------------------------------------ #
#                                           PathProcessor                                          #
# ------------------------------------------------------------------------------------------------ #


@dataclass
class JbPath:
    path: str
    is_local: bool


class PathProcessor:
    class InvalidPathError(Exception):
        ...

    def __init__(
        self,
        invalid_path_msg: str,
        local_file_not_found_msg: str,
        not_a_file_msg: str,
    ):
        self._invalid_path_msg = invalid_path_msg
        self._local_file_not_found_msg = local_file_not_found_msg
        self._not_a_file_msg = not_a_file_msg

    def process(self, raw_path: str) -> JbPath:
        url = QUrl.fromUserInput(
            raw_path,
            str(Path(".").resolve()),
            QUrl.UserInputResolutionOption.AssumeLocalFile,
        )

        error_message = None
        if not url.isValid():
            error_message = self._invalid_path_msg.format(path=url.toString())
        elif url.isLocalFile():
            local_path = Path(url.toLocalFile())
            if not local_path.exists():
                error_message = self._local_file_not_found_msg.format(path=local_path)
            if not local_path.is_file():
                error_message = self._not_a_file_msg.format(path=local_path)

        if error_message is not None:
            raise PathProcessor.InvalidPathError(error_message)

        if url.isLocalFile():
            return JbPath(url.toLocalFile(), is_local=True)
        return JbPath(url.toString(), is_local=False)
