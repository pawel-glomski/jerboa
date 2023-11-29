from PySide6 import QtWidgets as QtW


class MainWindow(QtW.QMainWindow):
    def __init__(
        self,
        min_size: tuple[int, int],
        relative_size: [float, float],
        menu_bar: QtW.QMenuBar,
        main_widget: QtW.QWidget,
        status_bar: QtW.QStatusBar,
    ):
        super().__init__()
        self.setMinimumSize(*min_size)

        available_geometry = self.screen().availableGeometry()
        self.resize(
            int(available_geometry.width() * relative_size[0]),
            int(available_geometry.height() * relative_size[1]),
        )

        self.setMenuBar(menu_bar)
        self.setCentralWidget(main_widget)
        # self.setStatusBar(status_bar)
