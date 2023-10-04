from PySide6 import QtGui, QtCore


class LoadingSpinner(QtGui.QMovie):
    def __init__(self, path: str, size: tuple[int, int]) -> None:
        super().__init__(path)
        self.setScaledSize(QtCore.QSize(*size))
