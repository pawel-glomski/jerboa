from collections.abc import Callable

import yt_dlp

from jerboa.signal import Signal
from jerboa.media import MediaSource
from jerboa.utils.file import JbPath


class MediaSourceRecognizer:
    def __init__(
        self,
        recognition_finished_signal: Signal
        # thread_pool: ThreadPool,
    ) -> None:
        self._recognition_finished_signal = recognition_finished_signal
        self._recognition_finished_signal.connect(lambda fn: fn())

        self._thread_pool = ...

        self._context_id = 0
        self._accepting_jobs = False

    def __enter__(self) -> "MediaSourceRecognizer":
        self.allow_jobs()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop_jobs()

    def allow_jobs(self) -> None:
        self._accepting_jobs = True

    def stop_jobs(self) -> None:
        # this would have to be lock protected if it was to support multi-threaded usage, _context_id
        # would also have to be client-specific, so only jobs of a certain client would be stopped,
        # but currently multi-threaded usage is not needed
        self._accepting_jobs = False
        self._context_id += 1

    def recognize(
        self,
        media_source_path: JbPath,
        on_success: Callable[[MediaSource], None],
        on_failure: Callable[[str], None],
    ):
        if not self._accepting_jobs:
            return

        job_context_id = self._context_id

        import av

        from threading import Thread

        def job():
            media_source = recognition_error_message = None

            try:
                avcontainer = av.open(media_source_path.path)
                media_source = MediaSource.from_av_container(avcontainer)
            except (av.error.OSError, av.error.HTTPError, av.error.ConnectionRefusedError) as err:
                recognition_error_message = str(err)
            except av.error.InvalidDataError:  # unsupported format
                if media_source_path.is_local:
                    recognition_error_message = (
                        'Format of the file "{path}" is not supported'.format(
                            path=media_source_path.path
                        )
                    )
                else:
                    ydl_opts = {
                        "extract_flat": "in_playlist",
                        #   '-S': 'proto:m3u8' # TODO: prefer single stream formats
                    }
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info_dict = ydl.sanitize_info(
                                ydl.extract_info(
                                    media_source_path.path,
                                    download=False,
                                )
                            )
                            media_source = MediaSource.from_yt_dlp_dict(info_dict)
                    except yt_dlp.utils.DownloadError as err:
                        recognition_error_message = str(err)

            def callback_call():
                # do not call the callbacks when if the context is different
                if job_context_id == self._context_id:
                    if media_source is not None:
                        on_success(media_source)
                    else:
                        on_failure(recognition_error_message)

            self._recognition_finished_signal.emit(callback_call)

        Thread(target=job, daemon=True).start()

        # self._thread_pool.start(job)
