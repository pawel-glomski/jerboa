import PySide6.QtWidgets as QtW
from PySide6 import QtGui
from PySide6.QtCore import Qt


class Palette(QtGui.QPalette):
    def __init__(
        self,
        app: QtW.QApplication,  # not used, but it is a dependency
        # palette_changed_signal: Signal TODO: enable palette change
    ) -> None:
        super().__init__()

        self.setColor(QtGui.QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        self.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(53, 53, 53))
        self.setColor(QtGui.QPalette.ColorRole.Text, Qt.GlobalColor.white)
        self.setColor(QtGui.QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        self.setColor(QtGui.QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        self.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(25, 25, 25))
        self.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(53, 53, 53))
        self.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(42, 130, 218))
        self.setColor(QtGui.QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        self.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(42, 130, 218))
        self.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(53, 53, 53))
        self.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(53, 53, 53))
        self.setColor(QtGui.QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
