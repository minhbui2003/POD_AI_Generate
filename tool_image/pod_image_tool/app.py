import os
import sys

if __package__ in (None, ""):
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication

from pod_image_tool import updater
from pod_image_tool.constants import APP_TITLE
from pod_image_tool.ui.main_window import ClipartAIToolWindow
from pod_image_tool.ui.style import apply_app_style


def main():
    updater.cleanup_update_artifacts()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    apply_app_style(app)

    window = ClipartAIToolWindow()
    window.show()

    return app.exec()
