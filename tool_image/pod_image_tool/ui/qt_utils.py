import traceback

from PIL import Image
from PySide6.QtCore import QObject, QSize, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QComboBox, QPushButton


class UiDispatcher(QObject):
    invoke = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.invoke.connect(self._run)

    def call(self, fn, *args):
        self.invoke.emit(fn, args)

    @Slot(object, object)
    def _run(self, fn, args):
        try:
            fn(*args)
        except Exception:
            traceback.print_exc()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
            return

        event.ignore()


class ElidedButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__("", parent)
        self._full_text = ""
        self.set_full_text(text)

    def set_full_text(self, text):
        self._full_text = text or ""
        self.setToolTip(self._full_text)
        self._apply_elided_text()

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(min(hint.width(), 160))
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(24, hint.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_elided_text()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_elided_text()

    def _apply_elided_text(self):
        available_width = max(12, self.width() - 18)
        display_text = self._elide_right(self._full_text, available_width)
        if self.text() != display_text:
            super().setText(display_text)

    def _elide_right(self, text, available_width):
        metrics = self.fontMetrics()
        if metrics.horizontalAdvance(text) <= available_width:
            return text

        marker = "..."
        marker_width = metrics.horizontalAdvance(marker)
        if marker_width >= available_width:
            return marker

        low = 0
        high = len(text)
        target_width = available_width - marker_width
        while low < high:
            midpoint = (low + high + 1) // 2
            if metrics.horizontalAdvance(text[:midpoint]) <= target_width:
                low = midpoint
            else:
                high = midpoint - 1

        return f"{text[:low]}{marker}"


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    if image.mode != "RGBA":
        image = image.convert("RGBA")

    data = image.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        image.width,
        image.height,
        image.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return QPixmap.fromImage(qimage.copy())
