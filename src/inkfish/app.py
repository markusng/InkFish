"""Entry point: build the QApplication and show the main window."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="inkfish", description="Pinch-zoom text editor.")
    parser.add_argument("path", nargs="?", type=Path, help="File to open (.txt, .md, .html).")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    if args.version:
        import importlib.metadata as md
        try:
            print(md.version("inkfish"))
        except md.PackageNotFoundError:
            print("0.0.0+dev")
        return 0

    from PyQt6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    if args.path is not None:
        window.open_path(args.path)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
