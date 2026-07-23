from PySide6.QtWidgets import QApplication


def apply_app_style(app: QApplication):
    app.setStyle("Fusion")
    app.setStyleSheet(
        """
        QWidget {
            background: #202124;
            color: #eeeeee;
            font-size: 12px;
        }

        QFrame#panel {
            background: #2a2c30;
            border: 1px solid #3a3d42;
            border-radius: 6px;
        }

        QLabel#sectionLabel {
            color: #aeb4bd;
            font-size: 11px;
            font-weight: 700;
        }

        QLabel#previewBox {
            background: #1f2023;
            border: 1px solid #3a3d42;
            border-radius: 6px;
            color: #aeb4bd;
        }

        QLineEdit, QTextEdit, QComboBox {
            background: #17181b;
            border: 1px solid #464a50;
            border-radius: 5px;
            padding: 6px;
            selection-background-color: #2d6fb7;
        }

        QTextEdit {
            padding: 5px;
        }

        QPushButton {
            background: #316aa6;
            border: 1px solid #3e78b5;
            border-radius: 5px;
            padding: 6px 10px;
            color: #ffffff;
            min-height: 22px;
        }

        QPushButton:hover {
            background: #397bbf;
        }

        QPushButton:disabled {
            background: #34373c;
            border-color: #3e4146;
            color: #777d86;
        }

        QPushButton#secondaryButton {
            background: #44484f;
            border-color: #555b64;
        }

        QPushButton#secondaryButton:hover {
            background: #515761;
        }

        QPushButton#dangerButton {
            background: #8b3a3a;
            border-color: #a24747;
        }

        QPushButton#dangerButton:hover {
            background: #a54545;
        }

        QPushButton#successButton {
            background: #2d8f4e;
            border-color: #36a75d;
        }

        QPushButton#successButton:hover {
            background: #35a85d;
        }

        QPushButton#linkButton {
            background: transparent;
            border: none;
            color: #aeb4bd;
            padding-left: 0;
            padding-right: 0;
        }

        QPushButton#linkButton:hover {
            color: #ffffff;
        }

        QPushButton#imageListButton {
            background: transparent;
            border: none;
            text-align: left;
            color: #d6d8dc;
        }

        QPushButton#imageListButton:hover {
            background: #33363b;
        }

        QPushButton#imageListButton:checked {
            background: #1f538d;
            color: #ffffff;
        }

        QScrollArea {
            border: none;
            background: transparent;
        }

        QCheckBox {
            spacing: 6px;
        }

        QProgressBar {
            background: #17181b;
            border: 1px solid #464a50;
            border-radius: 4px;
            height: 12px;
            text-align: center;
        }

        QProgressBar::chunk {
            background: #2d8f4e;
            border-radius: 3px;
        }
        """
    )
