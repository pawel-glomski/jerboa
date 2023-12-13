from collections.abc import Callable

import yt_dlp

from jerboa.core.signal import Signal
from jerboa.core.multithreading import ThreadPool, FnTask
from jerboa.core.file import JbPath
from .source import MediaSource


class MediaSourceRecognizer:
    def __init__(self, thread_pool: ThreadPool) -> None:
        self._thread_pool = thread_pool

    def recognize(
        self,
        media_source_path: JbPath,
        success_signal: Signal,
        failure_signal: Signal,
    ) -> FnTask.Future:
        return self._thread_pool.start(
            FnTask(
                lambda executor: self._recognize(
                    executor,
                    media_source_path,
                    success_signal,
                    failure_signal,
                )
            )
        )

    def _recognize(
        self,
        executor: FnTask.Executor,
        media_source_path: JbPath,
        success_signal: Signal,
        failure_signal: Signal,
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
                recognition_error_message = (
                    f"Format of the file '{media_source_path.path}' is not supported"
                )
            else:
                ydl_opts = {
                    "extract_flat": "in_playlist",
                    #   '-S': 'proto:m3u8' # TODO: prefer single stream formats
                }
                try:
                    executor.exit_if_aborted()

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

        with executor.finish_context:
            if media_source is not None:
                success_signal.emit(media_source=media_source)
            else:
                failure_signal.emit(error_message=recognition_error_message)
