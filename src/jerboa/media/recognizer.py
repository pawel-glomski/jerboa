from collections.abc import Callable

import yt_dlp

from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool, FnTask, Future
from jerboa.core.file import JbPath
from .source import MediaSource


class MediaSourceRecognizer:
    def __init__(
        self,
        recognition_finished_signal: Signal,
        thread_pool: ThreadPool,
    ) -> None:
        self._recognition_finished_signal = recognition_finished_signal
        self._recognition_finished_signal.connect(lambda callback: callback())

        self._thread_pool = thread_pool

    def recognize(
        self,
        media_source_path: JbPath,
        on_success: Callable[[MediaSource], None],
        on_failure: Callable[[str], None],
    ) -> Future[None]:
        return self._thread_pool.start(
            FnTask(
                lambda executor: self._recognize(
                    executor,
                    media_source_path,
                    on_success,
                    on_failure,
                )
            )
        )

    def _recognize(
        self,
        executor: FnTask.Executor,
        media_source_path: JbPath,
        on_success: Callable[[MediaSource], None],
        on_failure: Callable[[str], None],
    ):
        import av

        media_source = recognition_error_message = None

        try:
            avcontainer = av.open(media_source_path.path)
            media_source = MediaSource.from_av_container(avcontainer)
        except (
            av.error.FileNotFoundError,
            av.error.OSError,
            av.error.HTTPError,
            av.error.ConnectionRefusedError,
        ) as err:
            recognition_error_message = str(err)
        except (av.error.InvalidDataError, av.error.EOFError):  # not a media file
            if media_source_path.is_local:
                recognition_error_message = 'Format of the file "{path}" is not supported'.format(
                    path=media_source_path.path
                )
            else:
                ydl_opts = {
                    "extract_flat": "in_playlist",
                    #   '-S': 'proto:m3u8' # TODO: prefer single stream formats
                }
                try:
                    if executor.is_aborted:
                        executor.abort()

                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info_dict = ydl.sanitize_info(
                            ydl.extract_info(
                                media_source_path.path,
                                download=False,
                            )
                        )
                        media_source = MediaSource.from_yt_dlp_dict(info_dict)
                except Exception as err:
                    recognition_error_message = str(err)

        def callback_impl():
            if media_source is not None:
                on_success(media_source)
            else:
                on_failure(recognition_error_message)

        executor.finish_with(self._recognition_finished_signal.emit, callback=callback_impl)
