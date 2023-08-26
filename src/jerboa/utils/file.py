import os

from pathlib import Path

from PyQt5.QtCore import QUrl

CACHE_DIR_ENV_VAR_NAME = 'SPLE_HOME'
DEFAULT_CACHE_DIR_PATH = Path.home() / '.jerboa/'
CACHE_DIR_PATH = Path(os.environ.get(CACHE_DIR_ENV_VAR_NAME, DEFAULT_CACHE_DIR_PATH)).resolve()


class PathProcessor:

  def __init__(
      self,
      invalid_path_msg: str,
      local_file_not_found_msg: str,
      not_a_file_msg: str,
  ):
    self._invalid_path_msg = invalid_path_msg
    self._local_file_not_found_msg = local_file_not_found_msg
    self._not_a_file_msg = not_a_file_msg

  def process(self, raw_path: str) -> tuple[str, bool]:
    url = QUrl.fromUserInput(
        raw_path,
        str(Path('.').resolve()),
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

    if error_message is None:
      if url.isLocalFile():
        path = url.toLocalFile()
      else:
        path = url.toString()
      return path, True
    else:
      return error_message, False


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
