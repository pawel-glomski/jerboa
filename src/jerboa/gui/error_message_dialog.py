import PySide6.QtWidgets as QtW


class ErrorMessageDialogFactory:
    def __init__(self, title: str, default_parent: QtW.QWidget) -> None:
        self._title = title
        self._default_parent = default_parent

    def open(self, message: str, parent: QtW.QWidget | None = None) -> None:
        dialog = QtW.QMessageBox(
            QtW.QMessageBox.Icon.NoIcon,
            self._title,
            message,
            parent=(parent or self._default_parent),
        )
        dialog.setModal(True)
        dialog.exec()
