from collections.abc import Callable

from jerboa.signal import Signal
from jerboa.media import MediaSource


class RecognitionError:
  message: str


class MediaSorceRecognizer:

  def __init__(self, recognition_finished_signal: Signal
               # thread_pool: ThreadPool,
              ) -> None:
    self._recognition_finished_signal = recognition_finished_signal
    self._recognition_finished_signal.connect(lambda fn: fn())

    self._thread_pool = ...

  def recognize(
      self,
      media_source_path: str,
      on_success: Callable[[MediaSource], None],
      on_failure: Callable[[RecognitionError], None],
  ):
    import av

    from threading import Thread

    def job():
      avcontainer = av.open(media_source_path)

      def callback_call():
        # if media_source is not None:
        on_success(MediaSource(avcontainer))
        # else:
        #   on_failure(media_source_error)

      self._recognition_finished_signal.emit(callback_call)

    Thread(target=job, daemon=True).start()

    # self._thread_pool.start(job)
