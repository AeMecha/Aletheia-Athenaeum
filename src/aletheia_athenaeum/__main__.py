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
    # Release acceptance runs the same widgets/backend in a disposable profile.
    parser.add_argument("--verify-installation", type=Path, metavar="REPORT", help=argparse.SUPPRESS)
    parser.add_argument("--verification-embeddings", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Aletheia Athenaeum")
    app.setOrganizationName("Aletheia")
    app.setFont(QFont("Segoe UI", 10))
    if args.verify_installation:
        from .verification import verify
        sys.exit(verify(app, args.verify_installation, args.verification_embeddings))
    window = LibraryWindow(args.home)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
