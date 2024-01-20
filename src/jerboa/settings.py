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


import pydantic
import pydantic_settings
from typing_extensions import Annotated
from pathlib import Path

from jerboa import __version__
from .log import logger


# ------------------------------------------- Constants ------------------------------------------ #

PROJECT_NAME = "jerboa"
PROJECT_VERSION = __version__

_HOME_PATH_DEFAULT = Path(f"~/.{PROJECT_NAME}/")
_CACHE_DIR_PATH_DEFAULT = Path(f"~/.cache/{PROJECT_NAME}/")

# --------------------------------------------- Utils -------------------------------------------- #


def check_directory_write_permissions(dir_path: Path) -> bool:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        assert dir_path.is_dir(), "Not a directory"

        test_file_path = dir_path / "_write_test"
        with open(test_file_path, "wb"):
            pass
        test_file_path.unlink()
        return True
    except PermissionError:
        return False


# ------------------------------------------ Validators ------------------------------------------ #


def validate_directory_write_permissions(dir_path: Path) -> Path:
    if not check_directory_write_permissions(dir_path):
        raise AssertionError("No write permissions")
    return dir_path


def validate_directory_write_permissions_with_fallback(dir_path: Path, fallback_path: Path) -> Path:
    try:
        return validate_directory_write_permissions(dir_path)
    except AssertionError:
        logger.warning(
            f"No write permissions for '{dir_path}'. Trying the fallback instead '{fallback_path}'"
        )
        return validate_directory_write_permissions(fallback_path)


DirectoryPath = Annotated[
    pydantic.DirectoryPath,
    pydantic.Field(validate_default=True),
    pydantic.AfterValidator(validate_directory_write_permissions),
]

# ------------------------------------------ Environment ----------------------------------------- #


class Environment(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        frozen=True, validate_default=True, env_prefix=f"{PROJECT_NAME.upper()}_"
    )

    home_path: DirectoryPath = _HOME_PATH_DEFAULT

    def __post_init__(self):
        self.home_path.mkdir(parents=True, exist_ok=True)

    @property
    def settings_path(self) -> Path:
        return self.home_path / "settings.json"


ENVIRONMENT = Environment()

# ------------------------------------------- Settings ------------------------------------------- #


class Settings(pydantic.BaseModel):
    model_config = pydantic_settings.SettingsConfigDict(frozen=True, validate_default=True)

    version: str = PROJECT_VERSION
    cache_path: Path = _CACHE_DIR_PATH_DEFAULT

    def save(self) -> None:
        with open(ENVIRONMENT.settings_path, "w", encoding="utf-8") as settings_file:
            settings_file.write(self.model_dump_json())

    @staticmethod
    def load() -> "Settings":
        if ENVIRONMENT.settings_path.exists():
            with open(ENVIRONMENT.settings_path, "r", encoding="utf-8") as settings_file:
                return Settings.model_validate_json(settings_file.read())
        return Settings()

    @pydantic.field_validator("cache_path", mode="after")
    @classmethod
    def validate_cache_path(cls, cache_path: Path) -> Path:
        return validate_directory_write_permissions_with_fallback(
            cache_path, fallback_path=_CACHE_DIR_PATH_DEFAULT
        )
