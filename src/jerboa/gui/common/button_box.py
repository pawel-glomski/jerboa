import PySide6.QtWidgets as QtW
import PySide6.QtGui as QtG


class RejectAcceptButtonBox(QtW.QDialogButtonBox):
    def __init__(
        self,
        reject_button_text: str | None = None,
        accept_button_text: str | None = None,
        *,
        icons: bool = False,
        is_accept_button_disabled_by_default: bool = True,
    ) -> None:
        super().__init__(
            QtW.QDialogButtonBox.StandardButton.Cancel | QtW.QDialogButtonBox.StandardButton.Ok
        )

        self._reject_button = self.button(QtW.QDialogButtonBox.StandardButton.Cancel)
        self._accept_button = self.button(QtW.QDialogButtonBox.StandardButton.Ok)

        self._reject_button.setDefault(False)
        self._reject_button.setAutoDefault(False)

        if reject_button_text:
            self._reject_button.setText(reject_button_text)
        if accept_button_text:
            self._accept_button.setText(accept_button_text)

        if not icons:
            self._reject_button.setIcon(QtG.QIcon())
            self._accept_button.setIcon(QtG.QIcon())

        self._is_accept_button_disabled_by_default = is_accept_button_disabled_by_default

        self.reset()

    def reset(self) -> None:
        self._accept_button.setDisabled(self._is_accept_button_disabled_by_default)
        self._reject_button.setDisabled(False)

    def enable_accept(self) -> None:
        self._accept_button.setDisabled(False)
        self._accept_button.setDefault(True)

    def disable_reject(self) -> None:
        self._reject_button.setDisabled(True)

    def loose_accept_focus(self) -> None:
        self._accept_button.setDefault(False)
