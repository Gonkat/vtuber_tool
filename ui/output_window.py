from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QPalette, QColor, QKeySequence
from PyQt5.QtWidgets import QWidget, QLabel, QShortcut

from ui.character_overlay import CharacterOverlay


class OutputWindow(QWidget):
    """
    The output window intended to be captured by OBS / Discord screen share.
    Shows either the raw camera feed or a custom background + character overlay.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VTuber Output  ·  Capture this window in OBS")
        self.resize(1280, 720)
        self.setMinimumSize(320, 180)

        # Pure black background
        pal = self.palette()
        pal.setColor(QPalette.Window, QColor(0, 0, 0))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # Background / feed display label
        self._bg = QLabel(self)
        self._bg.setAlignment(Qt.AlignCenter)
        self._bg.setStyleSheet("background-color: black;")
        self._bg.resize(self.size())

        # Character overlay (child of output window so it floats above bg)
        self._character = CharacterOverlay(self)
        self._character.move(40, 40)
        self._character.resize(240, 240)
        self._character.hide()   # hidden until VTuber mode active

        self._vtuber_mode = False
        self._background_pixmap: QPixmap | None = None

        # ESC to close
        QShortcut(QKeySequence("Escape"), self, self.hide)
        # F key to toggle fullscreen
        QShortcut(QKeySequence("F"), self, self._toggle_fullscreen)

    # ─── Public API ────────────────────────────────────────────────────────

    def set_camera_frame(self, pixmap: QPixmap):
        """Called by camera thread with new frame."""
        if not self._vtuber_mode:
            self._display(pixmap)

    def set_background_image(self, pixmap: QPixmap):
        self._background_pixmap = pixmap
        if self._vtuber_mode:
            self._display(pixmap)

    def set_vtuber_mode(self, enabled: bool):
        self._vtuber_mode = enabled
        self._character.setVisible(enabled)
        if enabled and self._background_pixmap:
            self._display(self._background_pixmap)
        elif not enabled:
            # Will be updated by next camera frame
            self._bg.clear()
            self._bg.setStyleSheet("background-color: black;")

    def update_volume(self, volume: float):
        self._character.update_volume(volume)

    @property
    def character(self) -> CharacterOverlay:
        return self._character

    # ─── Internal ──────────────────────────────────────────────────────────

    def _display(self, pixmap: QPixmap):
        """Scale and crop pixmap to fill the display area."""
        if pixmap.isNull():
            return
        target = self._bg.size()
        scaled = pixmap.scaled(target, Qt.KeepAspectRatioByExpanding,
                               Qt.SmoothTransformation)
        # Center-crop
        x = (scaled.width() - target.width()) // 2
        y = (scaled.height() - target.height()) // 2
        cropped = scaled.copy(x, y, target.width(), target.height())
        self._bg.setPixmap(cropped)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bg.resize(self.size())
        # Re-render background at new size
        if self._vtuber_mode and self._background_pixmap:
            self._display(self._background_pixmap)

    def closeEvent(self, event):
        # Hide instead of destroy so it can be re-opened
        event.ignore()
        self.hide()
