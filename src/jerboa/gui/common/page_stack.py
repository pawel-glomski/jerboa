import PySide6.QtWidgets as QtW
import PySide6.QtGui as QtG
from PySide6.QtCore import Qt


class PageStack(QtW.QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QtW.QFrame.Shape.Box)
        self.setSizePolicy(QtW.QSizePolicy.Policy.Expanding, QtW.QSizePolicy.Policy.Expanding)

    def set_pages(self, pages: list[QtW.QWidget]) -> None:
        while self.count() > 0:
            self.removeWidget(self.widget(0))
        for page in pages:
            self.addWidget(page)


class MessagePage(QtW.QLabel):
    def __init__(self, text: str):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class LoadingSpinnerPage(QtW.QLabel):
    def __init__(self, loading_spinner_movie: QtG.QMovie):
        super().__init__()
        self.setMovie(loading_spinner_movie)
        self.movie().start()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
