import PySide6.QtWidgets as QtW
import PySide6.QtGui as QtG

ButtonType = QtW.QDialogButtonBox.StandardButton


class RejectAcceptButtonBox(QtW.QDialogButtonBox):
    def __init__(
        self,
        reject_button: ButtonType,
        accept_button: ButtonType,
        icons: bool,
        is_accept_button_disabled_by_default: bool,
    ) -> None:
        super().__init__(reject_button | accept_button)

        self._reject_button = self.button(reject_button)
        self._accept_button = self.button(accept_button)

        if not icons:
            self._reject_button.setIcon(QtG.QIcon())
            self._accept_button.setIcon(QtG.QIcon())

        self._is_accept_button_disabled_by_default = is_accept_button_disabled_by_default

        self.reset()

    def reset(self) -> None:
        self._accept_button.setDisabled(self._is_accept_button_disabled_by_default)

    def enable_accept(self) -> None:
        self._accept_button.setDisabled(False)
        self._accept_button.setDefault(True)

    def loose_accept_focus(self) -> None:
        self._accept_button.setDefault(False)
