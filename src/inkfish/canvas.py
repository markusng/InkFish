"""InkfishView — QGraphicsView holding a single DocumentItem.

Centralises the view transform: every input mode (mouse wheel, middle-drag,
trackpad pinch, touchscreen pinch) routes through `zoom_to` and `pan_by`.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QWheelEvent
from PyQt6.QtWidgets import QGestureEvent, QGraphicsScene, QGraphicsView, QWidget

from .document_item import DocumentItem
from .gestures import PanHandler, PinchHandler

MIN_SCALE = 0.1
MAX_SCALE = 20.0
WHEEL_ZOOM_BASE = 1.0015


class InkfishView(QGraphicsView):
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        scene = QGraphicsScene(parent)
        super().__init__(scene, parent)

        self.document_item = DocumentItem()
        scene.addItem(self.document_item)
        # Generous scene rect so pan has room to work; the document item lives near origin.
        scene.setSceneRect(-20000, -20000, 40000, 40000)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
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
