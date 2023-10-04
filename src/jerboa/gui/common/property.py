import PySide6.QtWidgets as QtW
from jerboa.core import logger


class LabelValuePair(QtW.QWidget):
    def __init__(self, label: str, read_only=True):
        super().__init__()
        self._label = QtW.QLabel(f"{label}")
        self._value = QtW.QLineEdit()
        self._value.setReadOnly(read_only)

        layout = QtW.QHBoxLayout()
        layout.addWidget(self._label)
        layout.addWidget(self._value)
        self.setLayout(layout)

    def set_value(self, value):
        self._value.setText(str(value))


class PropertiesCollection(QtW.QWidget):
    def __init__(self):
        super().__init__()
        self._values = dict[str, QtW.QLineEdit]()
        self._labels_layout = QtW.QVBoxLayout()
        self._values_layout = QtW.QVBoxLayout()

        main_layout = QtW.QHBoxLayout()
        main_layout.addLayout(self._labels_layout)
        main_layout.addLayout(self._values_layout)
        self.setLayout(main_layout)

    def add_property(self, key: str, read_only: bool = True):
        label = QtW.QLabel(f"{key}:")
        value = QtW.QLineEdit()
        value.setReadOnly(read_only)
        value.setDisabled(read_only)

        self._values[key] = value
        self._labels_layout.addWidget(label)
        self._values_layout.addWidget(value)

    def set_value(self, key: str, value):
        value_widget = self._values.get(key, None)
        if value_widget is not None:
            value_widget.setText(str(value))
        else:
            logger.error(f'Tried to set the value of a missing property: "{key}"')

    def clear_values(self):
        for value in self._values.values():
            value.setText("")
