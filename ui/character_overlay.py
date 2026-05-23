import os
from dataclasses import dataclass, field
from typing import Optional

from PyQt5.QtCore import Qt, QPoint, QSize, QRect, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QCursor
from PyQt5.QtWidgets import QWidget, QLabel


def load_image_as_pixmap(path: str, fallback_size: QSize = None) -> QPixmap:
    """Load PNG/JPG/BMP/SVG as QPixmap."""
    if fallback_size is None:
        fallback_size = QSize(200, 200)
    path_lower = path.lower()
    if path_lower.endswith('.svg'):
        try:
            from PyQt5.QtSvg import QSvgRenderer
            renderer = QSvgRenderer(path)
            size = renderer.defaultSize()
            if not size.isValid() or size.isEmpty():
                size = fallback_size
            pixmap = QPixmap(size)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return pixmap
        except Exception:
            pass
    pixmap = QPixmap(path)
    if pixmap.isNull():
        pixmap = QPixmap(fallback_size)
        pixmap.fill(QColor(200, 100, 200, 120))
    return pixmap


@dataclass
class LayerConfig:
    path: str
    min_vol: float = 0.0
    max_vol: float = 1.0
    name: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = os.path.basename(self.path)

    def should_show(self, volume: float) -> bool:
        return self.min_vol <= volume <= self.max_vol


class CharacterOverlay(QWidget):
    """
    A draggable, resizable overlay of multiple image layers.
    Layers are shown/hidden based on current microphone volume.
    Screaming triggers a red glow overlay.
    """

    RESIZE_ZONE = 22     # px from bottom-right corner that triggers resize
    MIN_SIZE = 40
    MAX_SIZE = 2000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.SizeAllCursor)
        self.resize(220, 220)

        self.layers: list[LayerConfig] = []
        self._pixmaps_orig: list[QPixmap] = []   # original full-res pixmaps
        self._labels: list[QLabel] = []

        self._volume: float = 0.0
        self._scream_threshold: float = 0.85

        # Drag state
        self._drag_offset: Optional[QPoint] = None

        # Resize state
        self._resizing: bool = False
        self._resize_start_global: Optional[QPoint] = None
        self._resize_start_size: Optional[QSize] = None

        # Red overlay with smoothing
        self._red_label = QLabel(self)
        self._red_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._red_label.setStyleSheet("background: transparent;")
        self._red_label.hide()
        self._red_pixmap_cache: Optional[QPixmap] = None
        self._red_cache_size: Optional[QSize] = None
        
        self._target_red_alpha: int = 0
        self._current_red_alpha: int = 0
        self._red_smoothness_ms: int = 100  # milliseconds for smooth transition
        
        # Timer for smooth red alpha transition
        self._red_smooth_timer = QTimer()
        self._red_smooth_timer.setInterval(16)  # ~60 fps
        self._red_smooth_timer.timeout.connect(self._update_red_alpha_smooth)

        # Corner resize grip indicator
        self._grip_visible = False

    # ─── Layer management ──────────────────────────────────────────────────

    def add_layer(self, config: LayerConfig) -> int:
        """Add a layer and return its index."""
        pixmap = load_image_as_pixmap(config.path)
        self._pixmaps_orig.append(pixmap)
        self.layers.append(config)

        lbl = QLabel(self)
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        lbl.setStyleSheet("background: transparent;")
        lbl.show()
        self._labels.append(lbl)

        self._red_label.raise_()
        self._relayout()
        self.update_volume(self._volume)
        return len(self.layers) - 1

    def remove_layer(self, index: int):
        if 0 <= index < len(self.layers):
            self.layers.pop(index)
            self._pixmaps_orig.pop(index)
            lbl = self._labels.pop(index)
            lbl.deleteLater()
            self.update_volume(self._volume)

    def update_layer_config(self, index: int, config: LayerConfig):
        if 0 <= index < len(self.layers):
            self.layers[index] = config
            self._pixmaps_orig[index] = load_image_as_pixmap(config.path)
            self._relayout()
            self.update_volume(self._volume)

    def move_layer_up(self, index: int):
        if 0 < index < len(self.layers):
            self.layers[index], self.layers[index - 1] = self.layers[index - 1], self.layers[index]
            self._pixmaps_orig[index], self._pixmaps_orig[index - 1] = \
                self._pixmaps_orig[index - 1], self._pixmaps_orig[index]
            self._labels[index], self._labels[index - 1] = \
                self._labels[index - 1], self._labels[index]
            self._relayout()
            self.update_volume(self._volume)

    def clear_layers(self):
        for lbl in self._labels:
            lbl.deleteLater()
        self._labels.clear()
        self._pixmaps_orig.clear()
        self.layers.clear()

    # ─── Volume ────────────────────────────────────────────────────────────

    def update_volume(self, volume: float):
        self._volume = volume
        for layer, lbl in zip(self.layers, self._labels):
            lbl.setVisible(layer.should_show(volume))

        # Red scream overlay - set target alpha (smooth transition will happen in timer)
        if volume > self._scream_threshold:
            progress = (volume - self._scream_threshold) / (1.0 - self._scream_threshold)
            self._target_red_alpha = int(progress * 200)
            self._red_smooth_timer.start()
        else:
            self._target_red_alpha = 0
            # Stop timer if target is 0 and current is close to 0
            if self._current_red_alpha < 5:
                self._red_smooth_timer.stop()
                self._current_red_alpha = 0
                self._red_label.hide()

    def _update_red_alpha_smooth(self):
        """Smoothly transition red alpha to target value."""
        if self._current_red_alpha == self._target_red_alpha:
            if self._target_red_alpha == 0:
                self._red_smooth_timer.stop()
                self._red_label.hide()
            return
        
        # Calculate step based on smoothness setting
        steps = max(1, self._red_smoothness_ms // 16)  # 16ms per frame
        step_size = max(1, abs(self._target_red_alpha - self._current_red_alpha) / steps)
        
        if self._current_red_alpha < self._target_red_alpha:
            self._current_red_alpha = min(self._target_red_alpha, int(self._current_red_alpha + step_size))
        else:
            self._current_red_alpha = max(self._target_red_alpha, int(self._current_red_alpha - step_size))
        
        # Update display
        if self._current_red_alpha > 0:
            self._red_pixmap = self._create_red_overlay_pixmap(self.width(), self.height(), self._current_red_alpha)
            self._red_label.setPixmap(self._red_pixmap)
            self._red_label.resize(self.size())
            self._red_label.show()
            self._red_label.raise_()
        else:
            self._red_label.hide()

    def set_red_smoothness(self, milliseconds: int):
        """Set the smoothness (speed) of red glow transition in milliseconds."""
        self._red_smoothness_ms = max(10, min(1000, milliseconds))

    def set_scream_threshold(self, value: float):
        self._scream_threshold = max(0.5, min(0.99, value))

    def _create_red_overlay_pixmap(self, width: int, height: int, alpha: int) -> QPixmap:
        """Create a pixmap with red overlay on non-transparent areas. Uses caching for speed."""
        size = QSize(width, height)
        
        # Create base overlay only if size changed
        if self._red_pixmap_cache is None or self._red_cache_size != size:
            self._red_pixmap_cache = self._build_red_base(width, height)
            self._red_cache_size = size
        
        # Apply alpha to cached pixmap
        result = QPixmap(self._red_pixmap_cache.size())
        result.fill(Qt.transparent)
        
        painter = QPainter(result)
        painter.setOpacity(alpha / 255.0)
        painter.drawPixmap(0, 0, self._red_pixmap_cache)
        painter.end()
        
        return result

    def _build_red_base(self, width: int, height: int) -> QPixmap:
        """Build the red tinted base pixmap (expensive operation, done once per size)."""
        overlay = QPixmap(width, height)
        overlay.fill(Qt.transparent)
        
        # Paint all visible layers with red tint
        for layer, pixmap_orig in zip(self.layers, self._pixmaps_orig):
            if layer.should_show(self._volume):
                # Scale pixmap to current size
                scaled = pixmap_orig.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (width - scaled.width()) // 2
                y = (height - scaled.height()) // 2
                
                # Create red-tinted version
                red_tinted = self._tint_red(scaled)
                
                painter = QPainter(overlay)
                painter.drawPixmap(x, y, red_tinted)
                painter.end()
        
        return overlay

    def _tint_red(self, pixmap: QPixmap) -> QPixmap:
        """Apply red tint to pixmap, keeping alpha channel."""
        img = pixmap.toImage()
        img = img.convertToFormat(img.Format_ARGB32)
        
        # Use faster approach: convert to raw data
        for y in range(img.height()):
            for x in range(img.width()):
                color = img.pixelColor(x, y)
                if color.alpha() > 0:  # Only tint non-transparent pixels
                    color.setRed(255)
                    color.setGreen(20)
                    color.setBlue(20)
                    img.setPixelColor(x, y, color)
        
        return QPixmap.fromImage(img)

    # ─── Layout ────────────────────────────────────────────────────────────

    def _relayout(self):
        """Scale and center all layer images to current widget size."""
        w, h = self.width(), self.height()
        for pixmap, lbl in zip(self._pixmaps_orig, self._labels):
            scaled = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            lbl.setPixmap(scaled)
            lbl.resize(scaled.size())
            lbl.move((w - scaled.width()) // 2, (h - scaled.height()) // 2)
        self._red_label.resize(self.size())
        
        # Invalidate red pixmap cache when size changes
        self._red_pixmap_cache = None
        self._red_cache_size = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    # ─── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        # Draw a subtle border + resize grip when hovered
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Hover outline
        if self._grip_visible:
            pen = QPen(QColor(120, 120, 255, 160), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(1, 1, self.width() - 2, self.height() - 2)

            # Bottom-right resize grip
            gx, gy = self.width() - self.RESIZE_ZONE, self.height() - self.RESIZE_ZONE
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(100, 100, 255, 200)))
            painter.drawRoundedRect(
                self.width() - 14, self.height() - 14, 12, 12, 4, 4
            )
            # Resize icon (lines)
            pen2 = QPen(QColor(255, 255, 255, 220), 1.5)
            painter.setPen(pen2)
            for offset in [4, 8]:
                painter.drawLine(
                    self.width() - offset, self.height() - 2,
                    self.width() - 2, self.height() - offset
                )
        painter.end()

    # ─── Mouse events ──────────────────────────────────────────────────────

    def _in_resize_zone(self, pos: QPoint) -> bool:
        return (pos.x() >= self.width() - self.RESIZE_ZONE and
                pos.y() >= self.height() - self.RESIZE_ZONE)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._in_resize_zone(event.pos()):
                self._resizing = True
                self._resize_start_global = event.globalPos()
                self._resize_start_size = QSize(self.width(), self.height())
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self._drag_offset = event.pos()
                self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        # Update cursor / grip based on hover zone
        if not (event.buttons() & Qt.LeftButton):
            if self._in_resize_zone(event.pos()):
                self.setCursor(Qt.SizeFDiagCursor)
            else:
                self.setCursor(Qt.SizeAllCursor)
            self._grip_visible = True
            self.update()

        if self._resizing and self._resize_start_global:
            delta = event.globalPos() - self._resize_start_global
            new_w = max(self.MIN_SIZE, min(self.MAX_SIZE,
                        self._resize_start_size.width() + delta.x()))
            new_h = max(self.MIN_SIZE, min(self.MAX_SIZE,
                        self._resize_start_size.height() + delta.y()))
            self.resize(new_w, new_h)

        elif self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            new_pos = self.pos() + event.pos() - self._drag_offset
            if self.parent():
                p = self.parent()
                new_pos.setX(max(-self.width() // 2,
                                 min(new_pos.x(), p.width() - self.width() // 2)))
                new_pos.setY(max(-self.height() // 2,
                                 min(new_pos.y(), p.height() - self.height() // 2)))
            self.move(new_pos)
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self._resizing = False
        self._resize_start_global = None
        if self._in_resize_zone(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        event.accept()

    def leaveEvent(self, event):
        self._grip_visible = False
        self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        """Scale character with scroll wheel (Ctrl+Wheel for fine control)."""
        modifiers = event.modifiers()
        delta = event.angleDelta().y()
        if modifiers & Qt.ControlModifier:
            factor = 1.03 if delta > 0 else 0.97
        else:
            factor = 1.12 if delta > 0 else 0.88

        new_w = int(max(self.MIN_SIZE, min(self.MAX_SIZE, self.width() * factor)))
        new_h = int(max(self.MIN_SIZE, min(self.MAX_SIZE, self.height() * factor)))

        # Scale from center
        center = self.pos() + QPoint(self.width() // 2, self.height() // 2)
        self.resize(new_w, new_h)
        new_pos = center - QPoint(new_w // 2, new_h // 2)
        if self.parent():
            p = self.parent()
            new_pos.setX(max(-new_w // 2, min(new_pos.x(), p.width() - new_w // 2)))
            new_pos.setY(max(-new_h // 2, min(new_pos.y(), p.height() - new_h // 2)))
        self.move(new_pos)
        event.accept()
