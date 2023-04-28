import os

from pathlib import Path

CACHE_DIR_ENV_VAR_NAME = 'SPLE_HOME'
DEFAULT_CACHE_DIR_PATH = Path.home() / '.jerboa/'
CACHE_DIR_PATH = Path(os.environ.get(CACHE_DIR_ENV_VAR_NAME, DEFAULT_CACHE_DIR_PATH)).resolve()


def create_cache_dir_rel(relative_dir_path: str) -> Path:
  return create_cache_dir_abs(CACHE_DIR_PATH / relative_dir_path)


def create_cache_dir_abs(absolute_dir_path: str) -> Path:
  dir_path = Path(absolute_dir_path).resolve()
  assert str(CACHE_DIR_PATH) in str(dir_path)

  if not dir_path.exists():
    os.makedirs(dir_path)
  assert dir_path.exists() and dir_path.is_dir()
  return dir_path


create_cache_dir_abs(CACHE_DIR_PATH / 'temp')
