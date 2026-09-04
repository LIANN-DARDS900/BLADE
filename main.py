from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.constants import APP_NAME, DATA_DIR, ICON_PATH, load_config
from app.main_window import MainWindow


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Request UAC elevation and relaunch the current executable/script."""
    if os.name != "nt":
        return False
    try:
        if getattr(sys, "frozen", False):
            executable = sys.executable
            parameters = " ".join(f'"{arg}"' for arg in sys.argv[1:])
        else:
            executable = sys.executable
            script = str(Path(sys.argv[0]).resolve())
            parameters = " ".join([f'"{script}"', *[f'"{arg}"' for arg in sys.argv[1:]]])
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            parameters,
            str(Path.cwd()),
            1,
        )
        return result > 32
    except Exception:
        return False


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("BLADE Endpoint Engineering")
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    if os.name != "nt":
        QMessageBox.critical(None, APP_NAME, "This application is designed for Windows 10/11 only.")
        return 10

    elevated = is_admin()
    if not elevated and "--no-elevate" not in sys.argv:
        if relaunch_as_admin():
            return 0
        QMessageBox.warning(
            None,
            "Administrator rights required",
            "The application could not obtain Administrator rights. Detection can open, but deployment actions will remain disabled.",
        )

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    window = MainWindow(load_config(), is_admin())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
