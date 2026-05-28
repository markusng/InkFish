"""InkfishView — QGraphicsView holding a single DocumentItem.

Centralises the view transform: every input mode (mouse wheel, middle-drag,
trackpad pinch, touchscreen pinch) routes through `zoom_to` and `pan_by`.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QEvent, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPainter, QTransform, QWheelEvent
from PyQt6.QtWidgets import QGestureEvent, QGraphicsScene, QGraphicsView, QWidget

from . import lod
from .document_item import DocumentItem
from .gestures import PanHandler, PinchHandler
from .line_numbers import LineNumberItem

MIN_SCALE = 0.1
MAX_SCALE = 20.0
WHEEL_ZOOM_BASE = 1.0015
ALT_ZOOM_SENSITIVITY = 0.005
PAN_CLAMP_MARGIN = 50  # viewport pixels of doc edge that must remain visible when clamp is on


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

        self._pan_clamp_enabled: bool = False
        self._in_clamp: bool = False  # re-entry guard for scroll-bar valueChanged
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll_value_changed)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll_value_changed)

        # Render hints follow zoom: skip text/edge antialiasing at sub-pixel scales.
        self.zoom_changed.connect(lambda _s: self._apply_render_hints_for_scale())

        # Drop antialiasing during active pan/zoom; restore 120 ms after motion stops.
        self._is_navigating: bool = False
        self._nav_restore_timer = QTimer(self)
        self._nav_restore_timer.setSingleShot(True)
        self._nav_restore_timer.setInterval(120)
        self._nav_restore_timer.timeout.connect(self._on_nav_idle)

        # Reduce per-frame overhead: skip 1-px antialiasing overdraw padding;
        # items are responsible for their own painter state (save/restore).
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing
            | QGraphicsView.OptimizationFlag.DontSavePainterState
        )

    # ---- transform mutation ---------------------------------------------------

    def current_scale(self) -> float:
        return self.transform().m11()

    def _apply_render_hints_for_scale(self) -> None:
        line_h = getattr(self.document_item, "_font_line_height_px", 14.7)
        if self._is_navigating or line_h * self.transform().m22() < lod.threshold_px():
            self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform)
        else:
            self.setRenderHints(
                QPainter.RenderHint.Antialiasing
                | QPainter.RenderHint.TextAntialiasing
                | QPainter.RenderHint.SmoothPixmapTransform
            )

    def _set_navigating(self, active: bool) -> None:
        if active:
            if not self._is_navigating:
                self._is_navigating = True
                self._apply_render_hints_for_scale()
            self._nav_restore_timer.start()
        else:
            self._is_navigating = False
            self._apply_render_hints_for_scale()

    def _on_nav_idle(self) -> None:
        self._set_navigating(False)

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
        self._clamp_scroll_to_doc()
        self._set_navigating(True)
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
        self._clamp_scroll_to_doc()
        self.zoom_changed.emit(self.current_scale())

    def fit_page(self) -> None:
        """Zoom so the whole document fits in the viewport, centred. Respects MIN/MAX_SCALE."""
        doc_rect = self.document_item.boundingRect()
        if doc_rect.isEmpty():
            return
        vp = self.viewport().rect()
        if vp.width() <= 0 or vp.height() <= 0:
            return
        sx = vp.width() / doc_rect.width()
        sy = vp.height() / doc_rect.height()
        target = min(sx, sy)
        target = max(MIN_SCALE, min(MAX_SCALE, target))
        self.setTransform(QTransform.fromScale(target, target))
        self.centerOn(self.document_item)
        self._clamp_scroll_to_doc()
        self.zoom_changed.emit(self.current_scale())

    def set_pan_clamp(self, enabled: bool) -> None:
        self._pan_clamp_enabled = enabled
        if enabled:
            self._clamp_scroll_to_doc()

    def pan_clamp_enabled(self) -> bool:
        return self._pan_clamp_enabled

    def _on_scroll_value_changed(self, _value: int) -> None:
        if self._in_clamp or not self._pan_clamp_enabled:
            return
        self._clamp_scroll_to_doc()

    def _clamp_scroll_to_doc(self) -> None:
        """If pan clamp is enabled, nudge scroll bars so the document keeps a margin in view."""
        if not self._pan_clamp_enabled or self._in_clamp:
            return
        try:
            doc_rect_scene = self.document_item.mapRectToScene(self.document_item.boundingRect())
        except RuntimeError:
            # DocumentItem may already be deleted during view teardown; scroll bars can
            # still fire valueChanged briefly after. Nothing meaningful to clamp.
            return
        if doc_rect_scene.isEmpty():
            return
        doc_rect_vp = self.mapFromScene(doc_rect_scene).boundingRect()
        vp = self.viewport().rect()
        if vp.width() <= 0 or vp.height() <= 0:
            return
        margin = PAN_CLAMP_MARGIN
        dx = 0
        dy = 0
        # Horizontal: clamp so at least `margin` px of doc overlaps the viewport on each side.
        if doc_rect_vp.width() <= vp.width():
            # Doc fits horizontally: keep entire doc inside viewport.
            if doc_rect_vp.left() < 0:
                dx = doc_rect_vp.left()
            elif doc_rect_vp.right() > vp.width():
                dx = doc_rect_vp.right() - vp.width()
        else:
            # Doc wider than viewport: at least `margin` of doc must be on the right and left edges.
            if doc_rect_vp.right() < margin:
                dx = doc_rect_vp.right() - margin
            elif doc_rect_vp.left() > vp.width() - margin:
                dx = doc_rect_vp.left() - (vp.width() - margin)
        # Vertical: symmetric.
        if doc_rect_vp.height() <= vp.height():
            if doc_rect_vp.top() < 0:
                dy = doc_rect_vp.top()
            elif doc_rect_vp.bottom() > vp.height():
                dy = doc_rect_vp.bottom() - vp.height()
        else:
            if doc_rect_vp.bottom() < margin:
                dy = doc_rect_vp.bottom() - margin
            elif doc_rect_vp.top() > vp.height() - margin:
                dy = doc_rect_vp.top() - (vp.height() - margin)
        if dx == 0 and dy == 0:
            return
        self._in_clamp = True
        try:
            h = self.horizontalScrollBar()
            v = self.verticalScrollBar()
            h.setValue(h.value() + int(round(dx)))
            v.setValue(v.value() + int(round(dy)))
        finally:
            self._in_clamp = False

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
        self._set_navigating(True)
        h = self.horizontalScrollBar()
        v = self.verticalScrollBar()
        h.setValue(h.value() - int(round(dx)))
        v.setValue(v.value() - int(round(dy)))
        self._clamp_scroll_to_doc()

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
        if e.type() == QEvent.Type.ShortcutOverride:
            # When vim is in a navigation mode, claim Ctrl+F (page down) and Ctrl+B
            # (page up) so they reach DocumentItem.keyPressEvent instead of firing
            # the global Find QAction.
            if self.document_item.is_vim_navigation_mode():
                ke = e  # QKeyEvent
                if ke.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    if ke.key() in (Qt.Key.Key_F, Qt.Key.Key_B):
                        e.accept()
                        return True
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
