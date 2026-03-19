"""
ArtistCircleWidget
──────────────────
Circular avatar with an optional animated glow ring and name label.
Used in the "Daily Artists" horizontal row on the main dashboard.
"""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import (
    Qt, QSize, QTimer, QPropertyAnimation, QEasingCurve,
    pyqtSignal, pyqtProperty, QPointF
)
from PyQt5.QtGui import (
    QPainter, QPainterPath, QPen, QColor, QPixmap, QRadialGradient,
    QLinearGradient, QBrush, QFont, QFontMetrics
)
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy


# ─────────────────────────────────────────────────────────────────
#  Internal avatar-only painting widget
# ─────────────────────────────────────────────────────────────────
class _CircleAvatar(QWidget):
    """Paints a circular avatar (image or gradient placeholder) with a
    coloured ring that can pulse via a QPropertyAnimation on `glow_opacity`."""

    clicked = pyqtSignal()

    DIAMETER = 90          # px – size of the full widget incl. ring
    RING_WIDTH = 2.5       # px – ring stroke
    INNER_PAD = 5          # px – gap between ring and photo

    def __init__(
        self,
        diameter: int = 90,
        ring_color: str = "#4d59fb",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._ring_color = QColor(ring_color)
        self._pixmap: Optional[QPixmap] = None
        self._placeholder_letter: str = "?"
        self._glow_opacity: float = 0.55
        self._hovered = False

        self.setFixedSize(diameter, diameter)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)

    # ── public API ─────────────────────────────────────────────

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap.scaled(
            self._diameter, self._diameter,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        self.update()

    def set_placeholder_letter(self, letter: str) -> None:
        self._placeholder_letter = letter[:1].upper()
        self.update()

    # ── glow_opacity property for QPropertyAnimation ───────────

    def _get_glow_opacity(self) -> float:
        return self._glow_opacity

    def _set_glow_opacity(self, val: float) -> None:
        self._glow_opacity = val
        self.update()

    glow_opacity = pyqtProperty(float, _get_glow_opacity, _set_glow_opacity)

    # ── events ─────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovered = True
        self._animate_glow(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._animate_glow(0.55)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _animate_glow(self, target: float) -> None:
        anim = QPropertyAnimation(self, b"glow_opacity", self)
        anim.setDuration(200)
        anim.setStartValue(self._glow_opacity)
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        # keep reference so GC doesn't kill it
        self._last_anim = anim

    # ── painting ───────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )

        d = self._diameter
        center = d / 2
        photo_r = (d / 2) - self.INNER_PAD  # radius of photo circle

        # ── outer glow ring ──────────────────────────────────
        ring_color = QColor(self._ring_color)
        ring_color.setAlphaF(self._glow_opacity)

        pen = QPen(ring_color, self.RING_WIDTH)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        half_ring = self.RING_WIDTH / 2
        p.drawEllipse(
            QPointF(center, center),
            center - half_ring,
            center - half_ring,
        )

        # ── clip to inner circle ─────────────────────────────
        clip = QPainterPath()
        clip.addEllipse(
            QPointF(center, center), photo_r, photo_r
        )
        p.setClipPath(clip)

        if self._pixmap and not self._pixmap.isNull():
            # draw centered / cropped image
            src = self._pixmap
            x_off = (src.width() - d) / 2
            y_off = (src.height() - d) / 2
            p.drawPixmap(
                0, 0,
                src,
                int(x_off), int(y_off), d, d,
            )
        else:
            # gradient placeholder
            grad = QLinearGradient(0, 0, d, d)
            grad.setColorAt(0, QColor("#1a1a3a"))
            grad.setColorAt(1, QColor("#0d0d20"))
            p.fillRect(0, 0, d, d, grad)

            # centre letter
            p.setPen(QPen(QColor("#4d59fb")))
            font = QFont("DM Sans", int(d * 0.32), QFont.Bold)
            p.setFont(font)
            p.drawText(
                0, 0, d, d,
                Qt.AlignCenter,
                self._placeholder_letter,
            )

        p.end()


# ─────────────────────────────────────────────────────────────────
#  Public widget
# ─────────────────────────────────────────────────────────────────
class ArtistCircleWidget(QWidget):
    """
    Vertical widget: circular avatar (with glow ring) + artist name.

    Usage::

        widget = ArtistCircleWidget(name="Max Himum", diameter=90)
        widget.set_pixmap(some_pixmap)
        widget.clicked.connect(lambda: ...)
    """

    clicked = pyqtSignal(str)   # emits artist name

    def __init__(
        self,
        name: str = "",
        diameter: int = 90,
        ring_color: str = "#4d59fb",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._name = name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignHCenter)

        # avatar
        self._avatar = _CircleAvatar(diameter=diameter, ring_color=ring_color)
        self._avatar.clicked.connect(lambda: self.clicked.emit(self._name))
        # default placeholder letter = first char of name
        if name:
            self._avatar.set_placeholder_letter(name[0])
        layout.addWidget(self._avatar, 0, Qt.AlignHCenter)

        # name label
        self._name_label = QLabel(name)
        self._name_label.setObjectName("artist_circle_name")
        self._name_label.setAlignment(Qt.AlignHCenter)
        self._name_label.setWordWrap(False)
        fm = QFontMetrics(self._name_label.font())
        self._name_label.setMaximumWidth(diameter + 20)
        layout.addWidget(self._name_label, 0, Qt.AlignHCenter)

        self.setFixedWidth(diameter + 20)
        self.setCursor(Qt.PointingHandCursor)

    # ── public API ─────────────────────────────────────────────

    def set_pixmap(self, pixmap: QPixmap) -> None:
        """Set the artist photo."""
        self._avatar.set_pixmap(pixmap)

    def set_name(self, name: str) -> None:
        """Update the displayed name."""
        self._name = name
        self._name_label.setText(name)
        if name:
            self._avatar.set_placeholder_letter(name[0])

    def set_ring_color(self, color: str) -> None:
        self._avatar._ring_color = QColor(color)
        self._avatar.update()

    # ── mouse passthrough ──────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._name)
        super().mousePressEvent(event)