import sys

from PySide6 import QtWidgets

import ui


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(ui.build_qss())

    # Launches UI which coordinates state variables & starting background loops
    window = ui.FishSniperUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
