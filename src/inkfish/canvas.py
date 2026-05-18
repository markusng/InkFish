"""InkfishView — QGraphicsView holding a single DocumentItem.

Centralises the view transform: every input mode (mouse wheel, middle-drag,
trackpad pinch, touchscreen pinch) routes through `zoom_to` and `pan_by`.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QTransform, QWheelEvent
from PyQt6.QtWidgets import QGestureEvent, QGraphicsScene, QGraphicsView, QWidget

from .document_item import DocumentItem
from .gestures import PanHandler, PinchHandler
from .line_numbers import LineNumberItem

MIN_SCALE = 0.01
MAX_SCALE = 1000.0
WHEEL_ZOOM_BASE = 1.0015
ALT_ZOOM_SENSITIVITY = 0.005


class InkfishView(QGraphicsView):
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        scene = QGraphicsScene(parent)
        super().__init__(scene, parent)

        self.document_item = DocumentItem()
        scene.addItem(self.document_item)
        self._line_number_item = LineNumberItem(self.document_item)
        scene.addItem(self._line_number_item)
        self._line_number_item.setVisible(False)
        # Generous scene rect so pan has room to work; the document item lives near origin.
        scene.setSceneRect(-20000, -20000, 40000, 40000)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setFrameShape(self.Shape.NoFrame)
        self.setBackgroundBrush(self.palette().base())

        self._pan_active = False
        self._pan_last: QPointF | None = None
        self._alt_zoom_active = False
        self._alt_zoom_anchor: QPointF | None = None   # viewport pos at press
        self._alt_zoom_start_scale: float = 1.0        # scale at press time

        self._pinch = PinchHandler()
        self._pan_gesture = PanHandler()
        self.grabGesture(Qt.GestureType.PinchGesture)
        self.grabGesture(Qt.GestureType.PanGesture)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

    # ---- transform mutation ---------------------------------------------------

    def current_scale(self) -> float:
        return self.transform().m11()

    def zoom_to(self, factor: float, anchor: QPointF | None = None) -> None:
        if factor <= 0:
            return
        current = self.current_scale()
        target = current * factor
        target = max(MIN_SCALE, min(MAX_SCALE, target))
        applied = target / current
        if applied == 1.0:
            return
        if anchor is not None:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
            before = self.mapToScene(anchor.toPoint())
            self.scale(applied, applied)
            after = self.mapToScene(anchor.toPoint())
            delta = after - before
            self.translate(delta.x(), delta.y())
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        else:
            self.scale(applied, applied)
        self.zoom_changed.emit(self.current_scale())

    def set_line_numbers_visible(self, visible: bool) -> None:
        self._line_number_item.setVisible(visible)

    def line_numbers_visible(self) -> bool:
        return self._line_number_item.isVisible()

    def scroll_to_document_origin(self) -> None:
        """Scroll so the document's top-left corner sits at the viewport's (0, 0)."""
        doc_tl = self.document_item.mapToScene(QPointF(0, 0))
        vp = self.mapFromScene(doc_tl)
        self.pan_by(-vp.x(), -vp.y())

    def reset_view(self) -> None:
        self.setTransform(QTransform())
        self.centerOn(self.document_item)
        self.zoom_changed.emit(self.current_scale())

    def scroll_half_page(self, down: bool) -> None:
        delta = self.viewport().height() // 2
        self.pan_by(0, delta if down else -delta)

    def scroll_page(self, down: bool) -> None:
        delta = self.viewport().height()
        self.pan_by(0, delta if down else -delta)

    def pan_by(self, dx: float, dy: float) -> None:
        """Pan by (dx, dy) in viewport pixels — moves the scene under the viewport."""
        if dx == 0 and dy == 0:
            return
        h = self.horizontalScrollBar()
        v = self.verticalScrollBar()
        h.setValue(h.value() - int(round(dx)))
        v.setValue(v.value() - int(round(dy)))

    # ---- mouse fallback -------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            factor = WHEEL_ZOOM_BASE ** delta
            self.zoom_to(factor, anchor=QPointF(event.position()))
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if event.button() == Qt.MouseButton.RightButton and alt:
            self._alt_zoom_active = True
            self._alt_zoom_anchor = QPointF(event.position())
            self._alt_zoom_start_scale = self.current_scale()
            self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = True
            self._pan_last = QPointF(event.position())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pan_active and self._pan_last is not None:
            pos = QPointF(event.position())
            delta = pos - self._pan_last
            self._pan_last = pos
            self.pan_by(delta.x(), delta.y())
            event.accept()
            return
        if self._alt_zoom_active and self._alt_zoom_anchor is not None:
            pos = event.position()
            dx = pos.x() - self._alt_zoom_anchor.x()   # right → zoom in
            dy = self._alt_zoom_anchor.y() - pos.y()   # up    → zoom in
            total_delta = dx + dy
            target_scale = self._alt_zoom_start_scale * math.exp(
                total_delta * ALT_ZOOM_SENSITIVITY
            )
            factor = target_scale / self.current_scale()
            self.zoom_to(factor, anchor=self._alt_zoom_anchor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Alt:
            self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Alt:
            self.viewport().unsetCursor()
            self._alt_zoom_active = False
            self._alt_zoom_anchor = None
        super().keyReleaseEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton and self._alt_zoom_active:
            self._alt_zoom_active = False
            self._alt_zoom_anchor = None
            self.viewport().unsetCursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_active:
            self._pan_active = False
            self._pan_last = None
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---- gesture dispatch -----------------------------------------------------

    def event(self, e: QEvent) -> bool:
        if e.type() == QEvent.Type.Gesture:
            assert isinstance(e, QGestureEvent)
            handled = False
            pinch = e.gesture(Qt.GestureType.PinchGesture)
            if pinch is not None:
                self._pinch.handle(self, pinch)
                handled = True
            pan = e.gesture(Qt.GestureType.PanGesture)
            if pan is not None:
                self._pan_gesture.handle(self, pan)
                handled = True
            if handled:
                e.accept()
                return True
        return super().event(e)
