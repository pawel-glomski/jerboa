import PySide6.QtWidgets as QtW
from PySide6 import QtGui

QButtonEnum = QtW.QDialogButtonBox.StandardButton


class RejectAcceptDialogButtonBox(QtW.QDialogButtonBox):
    def __init__(
        self,
        reject_button: str,
        accept_button: str,
        icons: bool,
        accept_disabled_by_default: bool,
    ) -> None:
        match reject_button.lower():
            case "cancel":
                reject_button_bitmask = QButtonEnum.Cancel
            case _:
                raise ValueError(f"Missing reject button ({reject_button=})")
        match accept_button.lower():
            case "ok":
                accept_button_bitmask = QButtonEnum.Ok
            case _:
                raise ValueError(f"Missing accept button ({accept_button=})")

        super().__init__(reject_button_bitmask | accept_button_bitmask)

        self._reject_button = self.button(reject_button_bitmask)
        self._ok_button = self.button(accept_button_bitmask)

        if not icons:
            self._reject_button.setIcon(QtGui.QIcon())
            self._ok_button.setIcon(QtGui.QIcon())

        self._accept_disabled_by_default = accept_disabled_by_default

        self.reset()

    def reset(self) -> None:
        self._ok_button.setDisabled(self._accept_disabled_by_default)

    def enable_accept(self) -> None:
        self._ok_button.setDisabled(False)
        self._ok_button.setDefault(True)

    def loose_accept_focus(self) -> None:
        self._ok_button.setDefault(False)
