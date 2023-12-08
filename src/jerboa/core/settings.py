import pydantic_settings
from pathlib import Path

HOME_PATH_DEFAULT = Path("~/.jerboa/")

CACHE_DIR_PATH_DEFAULT = Path("~/.cache")


class Settings(pydantic_settings.BaseSettings):
    _config = pydantic_settings.SettingsConfigDict(env_prefix="JERBOA")
    home_dir_path: Path = HOME_PATH_DEFAULT
    cache_dir_path: str = CACHE_DIR_PATH_DEFAULT

    @staticmethod
    def load() -> "Settings":
        with open(file.SETTINGS_PATH, "rb", encoding="utf-8") as settings_file:
            return Settings.model_validate_json(settings_file.read())
