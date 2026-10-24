"""Launch the native Qt widget application, with no browser/server dependency."""
import argparse
import sys
from pathlib import Path
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from .window import LibraryWindow


def main():
    parser = argparse.ArgumentParser(description="Aletheia Athenaeum native personal library")
    parser.add_argument("--home", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Aletheia Athenaeum")
    app.setOrganizationName("Aletheia")
    app.setFont(QFont("Segoe UI", 10))
    window = LibraryWindow(args.home)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
