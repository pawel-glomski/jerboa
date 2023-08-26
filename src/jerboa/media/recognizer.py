from collections.abc import Callable

from jerboa.signal import Signal
from jerboa.media import MediaSource


class RecognitionError:
  ...


class MediaSorceRecognizer:

  def __init__(self, recognition_finished_signal: Signal
               # thread_pool: ThreadPool,
              ) -> None:
    self._recognition_finished_signal = recognition_finished_signal
    self._thread_pool = ...

  def recognize(
      self,
      media_source_path: str,
      on_success: Callable[[MediaSource], None],
      on_failure: Callable[[RecognitionError], None],
  ):
    error_message = None
    if url.isValid():
      self._media_source_details_panel.display_loading_spinner()

      if url.isLocalFile():
        if Path(url.toLocalFile()).is_file():
          import av

          from threading import Thread

          def open_container_task():
            avcontainer = av.open(url.toLocalFile())

            def update_gui():
              self._media_source_details_panel.display_avcontainer(avcontainer)
              self._button_box.enable_accept()

            # QtCore.QTimer.singleShot(1, update_gui)
            self.update_gui.emit(update_gui)

          # QtCore.QThread().
          Thread(target=open_container_task, daemon=True).start()
        else:
          error_message = 'Local file not found!'
      else:
        # related_content_panel = self._content_panel_streaming_site
        ...
    else:
      error_message = 'Media source path is invalid!'

    if error_message is not None:
      self._error_dialog.showMessage(error_message)

    # def job():
    #   ...
    #   if media_source is not None:
    #     self._recognition_finished_signal.emit(on_success, media_source)
    #   else:
    #     self._recognition_finished_signal.emit(on_failure, media_source_error)

    # self._thread_pool.start(job)
