import sys
# import PyQt6.QtCore as QtCore
import PyQt6.QtGui as QtGui
import PyQt6.QtWidgets as QtW
import PyQt6.QtMultimedia as QtMedia
from PyQt6.QtCore import Qt

# from jerboa.media.source import JBSource


class PlayerView(QtW.QMainWindow):

  def __init__(self):
    super().__init__()

    self.create_algorithm_starting_bar()
    self.create_algorithm_run_details_bar()
    self.create_display()
    self.create_timeline()

    splitter = QtW.QSplitter()
    # splitter.setStyleSheet('''
    #   QSplitter::handle {
    #     border-right: 1px solid #413F42;
    #     margin: 50px 1px;
    #   }
    #   ''')

    splitter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    splitter.addWidget(self.side_bar)
    splitter.addWidget(self._canvas)
    splitter.addWidget(self.side_bar2)
    splitter.setSizes([self.side_bar.minimumWidth() + 50,
                       self._canvas.minimumWidth() * 2,
                       0])  # Set the initial sizes of the side bar and canvas

    self.setCentralWidget(splitter)

    # self.algorithm_options_side_bar
    # self.algorithm_timeline_options_side_bar
    # self._frame_display
    # self._timeline

  def create_side_bar(self):
    # self.side_bar = QtW.QFrame()
    # self.side_bar.setMinimumWidth(200)
    # self.side_bar.setSizePolicy(QtW.QSizePolicy.Policy.MinimumExpanding,
    #                             QtW.QSizePolicy.Policy.Expanding)

    # side_layout = QtW.QVBoxLayout()
    # side_layout.addWidget(tab_widget)

    # self.side_bar.setLayout(side_layout)

    self.side_bar = QtW.QTabWidget()
    self.side_bar.setMinimumWidth(200)
    tab1 = QtW.QLabel("Tab 1")
    tab2 = QtW.QLabel("Tab 2")
    self.side_bar.addTab(tab1, "Tab 1")
    self.side_bar.addTab(tab2, "Tab 2")

    self.side_bar2 = QtW.QTabWidget()
    self.side_bar2.setMinimumWidth(200)
    tab1 = QtW.QLabel("Tab 1")
    tab2 = QtW.QLabel("Tab 2")
    self.side_bar2.addTab(tab1, "Tab 1")
    self.side_bar2.addTab(tab2, "Tab 2")

  def create_canvas(self):
    self._canvas = QtW.QFrame()
    self._canvas.setMinimumSize(400, 200)
    self._canvas.setSizePolicy(QtW.QSizePolicy.Policy.MinimumExpanding,
                               QtW.QSizePolicy.Policy.MinimumExpanding)
    layout = QtW.QVBoxLayout()
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(QtW.QLabel('test123'))
    layout.addWidget(QtW.QLabel('test123'))
    self._canvas.setLayout(layout)


class MainWindow(QtW.QMainWindow):

  def __init__(self):
    super().__init__()

    self._create_menu_bar()
    self._create_status_bar()

    self._player_view = PlayerView()

    self._views = QtW.QStackedWidget()
    self._views.addWidget(self._player_view)
    self._views.setCurrentIndex(0)
    self.setCentralWidget(self._views)

  def _create_menu_bar(self):
    menu_bar = self.menuBar()

    file_menu = menu_bar.addMenu('File')
    settings_menu = menu_bar.addMenu('Settings')
    plugins_menu = menu_bar.addMenu('Plugins')

  def _create_status_bar(self):
    status_bar = self.statusBar()
    status_bar.showMessage('Ready')
    status_bar.setStyleSheet('''
      QStatusBar {
        border-top: 1px solid #413F42;
      }
      ''')


def main():
  # src = JBSource('tests/test_recordings/test.mp4')
  # src = JBSource('tests/test_recordings/sintel.mp4')
  # src = JBSource('http://clips.vorwaerts-gmbh.de/big_buck_bunny.mp4')
  # src = JBSource('https://rr1---sn-u2oxu-bqok.googlevideo.com/videoplayback?expire=1686940512&ei=AFeMZI64G4fRyAWbubyYDA&ip=37.47.205.215&id=o-AKgua88ILVszzG3n9vdfXmhH9yQjBvJUXFgYMsPgv5TN&itag=22&source=youtube&requiressl=yes&mh=l0&mm=31%2C29&mn=sn-u2oxu-bqok%2Csn-u2oxu-f5fe7&ms=au%2Crdu&mv=m&mvi=1&pcm2cms=yes&pl=21&initcwndbps=601250&spc=qEK7B-90RKtXnokdg99lflBxPSxD-t8&vprv=1&svpuc=1&mime=video%2Fmp4&cnr=14&ratebypass=yes&dur=3884.489&lmt=1668186987208939&mt=1686918562&fvip=3&fexp=24007246&beids=24350017&c=ANDROID&txp=5432434&sparams=expire%2Cei%2Cip%2Cid%2Citag%2Csource%2Crequiressl%2Cspc%2Cvprv%2Csvpuc%2Cmime%2Ccnr%2Cratebypass%2Cdur%2Clmt&sig=AOq0QJ8wRgIhAJm-xYTallggu4bz2c-uCVSWsDBEUbn-LfuvjshMhSfhAiEAx8yJeh13X460YDbkxtoJkxSJTks20U6TrfrviydAApk%3D&lsparams=mh%2Cmm%2Cmn%2Cms%2Cmv%2Cmvi%2Cpcm2cms%2Cpl%2Cinitcwndbps&lsig=AG3C_xAwRAIgdqW8zvbIbdBLex5MR97bSU-FjEmDs3lpejhnbt_DBaECIEmzMq-9VoGRfcfixIszqfsbBGcaJyIMkOxsoJRujeLw')

  app = QtW.QApplication(sys.argv)

  main_win = MainWindow()
  available_geometry = main_win.screen().availableGeometry()
  main_win.resize(available_geometry.width() // 2, available_geometry.height() // 2)
  main_win.show()

  sys.exit(app.exec())


if __name__ == '__main__':
  import multiprocessing as mp
  mp.set_start_method('spawn')

  main()
