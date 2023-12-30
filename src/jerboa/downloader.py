import youtube_dl

from multiprocessing import Pool
from logging import Logger
from pathlib import Path
from typing import List
from argparse import ArgumentParser

from .utils.cli import cli_subcommand
from .utils.logger import NULL_LOGGER

SUBTITLES_FORMAT = 'vtt'
QUERY_JOBS_MULTI = 4
DOWNLOAD_RETRIES = 6
SLOW_DOWNLOAD_TIMEOUT = 6
NO_SUBS_LANGUAGE = 'none'
OUT_VIDEO = 'video'
OUT_AUDIO = 'audio'
OUT_RECORDING = 'recording'
OUT_SUBTITLES = 'subs'


class Downloader:

  def __init__(self,
               dst: str,
               lang: str,
               jobs: int,
               min_speed: float,
               buffer_size: float,
               with_video: bool,
               logger: Logger = NULL_LOGGER):
    """Downloader of recordings with lyrics of a specified language

    Args:
        dst (str): Path to a directory for downloaded recordings
        lang (str): Language of lyrics (language code, for example 'en')
        jobs (int): Number of threads to use for downloading
        min_speed (float): Minimum download speed to reset the connection [MiB]
        buffer_size (float): Downloading buffer size [MiB]
        with_video (bool): Download also video stream
        logger (Logger, optional): Logger for messages. Defaults to NULL_LOGGER.
    """
    self.dst = Path(dst).resolve()
    self.lang = lang.lower()
    self.jobs = jobs
    self.min_speed = min_speed * 1024 * 1024
    self.buffer_size = int(buffer_size * 1024 * 1024)
    self.with_video = with_video
    self.logger = logger

  def download(self, src: str) -> None:
    """Download the specified dataset

    Args:
        src (str): Path to the file containing links of videos to download
    """
    src = Path(src).resolve()

    if not src.is_file():
      raise FileNotFoundError(f'Bad src file path: {src}')

    self.logger.info(f'Checking the links provided in: {src}')
    urls = self._get_urls(src, self.jobs * QUERY_JOBS_MULTI)
    self.logger.info('Finished checking links')

    self.logger.info('Downloading:')
    with Pool(self.jobs) as pool:
      if self.lang != NO_SUBS_LANGUAGE:
        urls = pool.starmap(self._download_stream, [(url, OUT_SUBTITLES) for url in urls])
        urls = set(urls) - {''}
      urls = pool.starmap(self._download_stream, [(url, OUT_RECORDING) for url in urls])
      urls = set(urls) - {''}
    self.logger.info('Finished downloading')

    if self.dst.exists():
      with open(self.dst / 'downloaded.txt', 'w', encoding='UTF-8') as file:
        file.writelines([url + '\n' for url in urls])

  def _get_urls(self, src_path: Path, jobs: int) -> List[str]:
    """Get a list of urls from the provided file, which have subtitles in the specified language

    Args:
        src_path (Path): Path to a file with links of videos to download
        jobs (int): Number of simultaneous queries for videos

    Returns:
        List[str]: List of unique urls to download
    """
    with open(src_path, 'r', encoding='UTF-8') as src_file:
      valid_urls = []
      with Pool(jobs) as pool:
        urls = [l.strip() for l in src_file.readlines() if l.strip() != '']
        urls_list = pool.map(self._inspect_url, [url for url in urls])
        valid_urls += [url for insp_urls in urls_list for url in insp_urls]
      return list(set(valid_urls))

  def _inspect_url(self, url: str) -> List[str]:
    """Inspect the provided URL, expand if it is a playlist, and return the urls which have
    subtitles in the specified language

    Args:
        url (str): URL to inspect

    Returns:
        List[str]: List of valid urls
    """
    try:
      with youtube_dl.YoutubeDL({'logger': NULL_LOGGER}) as ydl:
        info = ydl.extract_info(url, download=False)
        if 'entries' in info:
          playlist = []
          for vid_info in info['entries']:
            playlist += self._get_valid_url(vid_info)
          return playlist
        else:
          return self._get_valid_url(info)
    except Exception as e:
      self.logger.warning(f'[ERROR] {url} - {str(e)}')
    return []

  def _get_valid_url(self, vid_info: dict) -> List[str]:
    """Check whether the provided video match the requirements

    Args:
        vid_info (dict): Information about the video

    Returns:
        List[str]: List with the URL of the video or empty if it was discarded
    """
    url = vid_info['webpage_url']
    if self.lang == NO_SUBS_LANGUAGE:
      return [url]
    subs = {sub['ext'] for sub in vid_info.get('subtitles', {}).get(self.lang, [])}
    if SUBTITLES_FORMAT in subs:
      self.logger.info(f'[VALID] {url}')
      return [url]
    self.logger.warning(f'[ BAD ] {url} - No subtitles for language: "{self.lang}" '
                        f'in format: "{SUBTITLES_FORMAT}"')
    return []

  def _download_stream(self, url: str, stype: str) -> str:
    """Download a stream of the specified type from the provided URL

    Args:
        url (str): URL of stream to download
        stype (str): Type of stream to download

    Raises:
        ConnectionError: When download is going too slow, restart the connection
        ValueError:

    Returns:
        str: The provided URL if successfully downloaded, empty string otherwise
    """
    last_good_speed_time = 0

    def _progress_callback(progress):
      nonlocal last_good_speed_time
      if progress['status'] == 'downloading':
        speed = progress.get('speed', 0)
        speed = 0 if speed is None else speed
        if speed > self.min_speed:
          last_good_speed_time = progress['elapsed']
        if (progress['elapsed'] - last_good_speed_time > SLOW_DOWNLOAD_TIMEOUT and
            progress['eta'] > 15):
          raise ConnectionError('Too slow ({:.2f} KiB/s), '.format(speed / 1024) +
                                'restarting the connection')

    dst_path = '{}/%(title)s-%(id)s/{}.%(ext)s'
    common_options = {
        'logger': NULL_LOGGER,
        'restrictfilenames': 'True',
        'progress_hooks': [_progress_callback],
        'buffersize': self.buffer_size
    }

    if stype == OUT_SUBTITLES:
      assert self.lang != NO_SUBS_LANGUAGE
      if self._download(
          url, {
              **common_options, 'outtmpl': dst_path.format(self.dst, OUT_SUBTITLES),
              'skip_download': 'True',
              'writesubtitles': 'True',
              'subtitleslangs': [self.lang],
              'subtitlesformat': SUBTITLES_FORMAT
          }, f'[ SUB ] {url} - '):
        self.logger.info(f'[ SUB ] {url}')
        return url
    elif stype == OUT_RECORDING:
      out_format = 'best' if self.with_video else 'bestaudio'
      out_name = OUT_VIDEO if self.with_video else OUT_AUDIO
      if self._download(url, {
          **common_options, 'outtmpl': dst_path.format(self.dst, out_name),
          'format': out_format
      }, f'[ VID ] {url} - '):
        self.logger.info(f'[ VID ] {url}')
        return url
    else:
      raise ValueError(f'Bad stream type value: {stype}')
    return ''

  def _download(self, url: str, options: dict, err_prefix: str = '') -> bool:
    """Download a stream/video specified in options with other download settings

    Args:
        url (str): URL to the video containing the resource specified in options
        options (dict): Download options for youtube-dl downloader
        err_prefix (str, optional): . Defaults to ''.

    Returns:
        bool: Whether successfully downloaded specified resource
    """
    retries = DOWNLOAD_RETRIES
    while retries > 0:
      with youtube_dl.YoutubeDL(options) as ydl:
        try:
          ydl.download([url])
          return True
        except youtube_dl.DownloadError as e:
          self.logger.warning(err_prefix + str(e))
          if e.exc_info[0] is not ConnectionError:
            retries -= 1
    if retries == 0:
      self.logger.error(err_prefix + f'Skipping after {DOWNLOAD_RETRIES} retries')
    else:
      self.logger.error(err_prefix + 'Skipping')
    return False


############################################### CLI ################################################


@cli_subcommand
class CLI:

  COMMAND = 'download'
  DESCRIPTION = 'Downloads specified recordings'
  ARG_SRC = 'src'
  ARG_DST = 'dst'
  ARG_LANG = 'lang'
  ARG_JOBS = 'jobs'
  ARG_MIN_SPEED = 'min_speed'
  ARG_BUFFER_SIZE = 'buffer_size'
  ARG_WITH_VIDEO = 'with_video'
  DEFAULT_ARGS = {
      ARG_LANG: NO_SUBS_LANGUAGE,
      ARG_JOBS: 4,
      ARG_MIN_SPEED: 0.1,
      ARG_BUFFER_SIZE: 0.5,
      ARG_WITH_VIDEO: False
  }

  @staticmethod
  def setup_arg_parser(parser: ArgumentParser) -> ArgumentParser:
    """Sets up a CLI argument parser for this submodule

    Returns:
        ArgumentParser: Configured parser
    """
    parser.description = CLI.DESCRIPTION
    parser.add_argument(CLI.ARG_SRC,
                        help='Path of the file with links to videos',
                        type=str,
                        action='store')
    parser.add_argument(CLI.ARG_DST,
                        help='Path of the destination directory for downloaded videos',
                        type=str,
                        action='store')
    parser.add_argument('-l',
                        f'--{CLI.ARG_LANG}',
                        help='Language used in the videos',
                        type=str,
                        action='store',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_LANG])
    parser.add_argument('-j',
                        f'--{CLI.ARG_JOBS}',
                        help='Number of threads to use for downloading',
                        type=int,
                        action='store',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_JOBS])
    parser.add_argument('-m',
                        f'--{CLI.ARG_MIN_SPEED}',
                        help='Minimum download speed to reset the connection [MiB]',
                        type=float,
                        action='store',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_MIN_SPEED])
    parser.add_argument('-b',
                        f'--{CLI.ARG_BUFFER_SIZE}',
                        help='Downloading buffer size [MiB]',
                        type=float,
                        action='store',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_BUFFER_SIZE])
    parser.add_argument('-v',
                        f'--{CLI.ARG_WITH_VIDEO}',
                        help='Download also video stream',
                        action='store_true',
                        default=CLI.DEFAULT_ARGS[CLI.ARG_WITH_VIDEO])
    parser.set_defaults(run=CLI.run_submodule)
    return parser

  @staticmethod
  def run_submodule(args: object, logger: Logger) -> None:
    """Runs this submodule

    Args:
        args (object): Arguments of this submodule (defined in setup_arg_parser)
        logger (Logger): Logger for messages
    """
    args = args.__dict__
    dl = Downloader(dst=args[CLI.ARG_DST],
                    lang=args[CLI.ARG_LANG],
                    jobs=args[CLI.ARG_JOBS],
                    min_speed=args[CLI.ARG_MIN_SPEED],
                    buffer_size=args[CLI.ARG_BUFFER_SIZE],
                    with_video=args[CLI.ARG_WITH_VIDEO],
                    logger=logger)
    dl.download(args[CLI.ARG_SRC])
