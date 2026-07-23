from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QVBoxLayout

from .. import updater
from .qt_utils import UiDispatcher


class UpdateProgressDialog(QDialog):
    def __init__(self, parent, download_url, sha256):
        super().__init__(parent)
        self.setWindowTitle("Dang cap nhat")
        self.setFixedSize(420, 160)
        self.setModal(True)
        self._can_close = False
        self.dispatcher = UiDispatcher(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        self.status_label = QLabel("Dang tai ban cap nhat moi...")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.close_btn = QPushButton("Dang xu ly...")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        button_row.addWidget(self.close_btn)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        updater.download_and_install_update(
            download_url,
            sha256,
            self._thread_progress,
            self._thread_success,
            self._thread_error,
        )

    def closeEvent(self, event):
        if self._can_close:
            event.accept()
        else:
            event.ignore()

    def _thread_progress(self, percent):
        self.dispatcher.call(self._on_progress, percent)

    def _thread_success(self, script_path):
        self.dispatcher.call(self._on_success, script_path)

    def _thread_error(self, message):
        self.dispatcher.call(self._on_error, message)

    def _on_progress(self, percent):
        if percent == -1:
            self.progress.setValue(100)
            self.status_label.setText("Dang kiem tra checksum...")
            return

        self.progress.setValue(max(0, min(100, int(percent))))
        self.status_label.setText(f"Dang tai: {percent}%")

    def _on_success(self, script_path):
        self.progress.setValue(100)
        self.status_label.setText("Cap nhat san sang. Ung dung se khoi dong lai...")
        QTimer.singleShot(700, lambda: updater.execute_updater_and_exit(script_path))

    def _on_error(self, message):
        self._can_close = True
        self.progress.setValue(0)
        self.status_label.setText("Cap nhat that bai.")
        self.close_btn.setText("Dong")
        self.close_btn.setEnabled(True)
        QMessageBox.critical(self, "Cap nhat that bai", message)
