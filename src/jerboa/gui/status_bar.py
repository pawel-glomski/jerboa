import PySide6.QtWidgets as QtW


class StatusBar(QtW.QStatusBar):
    def __init__(self):
        super().__init__()

        self.showMessage("Ready")
        self.setStyleSheet(
            """
          QStatusBar {
            border-top: 1px solid #413F42;
          }
          """
        )
