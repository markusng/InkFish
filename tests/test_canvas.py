"""Canvas mouse fallback + zoom/pan API."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtCore import QEvent

from inkfish.canvas import MAX_SCALE, MIN_SCALE, InkfishView


@pytest.fixture
def view(qtbot):
    v = InkfishView()
    qtbot.addWidget(v)
    v.resize(400, 300)
    v.show()
    qtbot.waitExposed(v)
    return v


def test_zoom_to_changes_scale(view: InkfishView) -> None:
    before = view.current_scale()
    view.zoom_to(1.5)
    assert view.current_scale() == pytest.approx(before * 1.5, rel=1e-3)


def test_zoom_clamped(view: InkfishView) -> None:
    view.zoom_to(1e6)
    assert view.current_scale() == pytest.approx(MAX_SCALE, rel=1e-6)
    view.zoom_to(1e-9)
    assert view.current_scale() == pytest.approx(MIN_SCALE, rel=1e-6)


def test_fit_page_sets_scale_within_bounds(view: InkfishView) -> None:
    view.document_item.setPlainText("hello\nworld\n")
    view.fit_page()
    s = view.current_scale()
    assert MIN_SCALE <= s <= MAX_SCALE


def test_pan_clamp_keeps_doc_in_view(view: InkfishView) -> None:
    view.document_item.setPlainText("a\n" * 20)
    view.set_pan_clamp(True)
    # Try to pan the document far off to the upper-left.
    view.pan_by(-10000, -10000)
    doc_rect = view.document_item.mapRectToScene(view.document_item.boundingRect())
    doc_vp = view.mapFromScene(doc_rect).boundingRect()
    vp = view.viewport().rect()
    # At least 1 px of the document must remain inside the viewport on every side.
    assert doc_vp.right() > 0
    assert doc_vp.bottom() > 0
    assert doc_vp.left() < vp.width()
    assert doc_vp.top() < vp.height()


def test_pan_clamp_off_allows_unbounded_pan(view: InkfishView) -> None:
    view.document_item.setPlainText("a\n" * 20)
    view.set_pan_clamp(False)
    view.pan_by(-5000, -5000)
    doc_rect = view.document_item.mapRectToScene(view.document_item.boundingRect())
    doc_vp = view.mapFromScene(doc_rect).boundingRect()
    # With clamp off, the document is allowed to leave the viewport entirely.
    assert doc_vp.right() < 0 or doc_vp.bottom() < 0


def test_ctrl_wheel_zooms(view: InkfishView, qtbot) -> None:
    before = view.current_scale()
    event = QWheelEvent(
        QPointF(100, 100),
        view.mapToGlobal(QPoint(100, 100)).toPointF(),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    view.wheelEvent(event)
    assert view.current_scale() > before


def test_middle_drag_pans(view: InkfishView) -> None:
    def make(evt_type: QEvent.Type, pos: tuple[float, float], button: Qt.MouseButton) -> QMouseEvent:
        return QMouseEvent(
            evt_type,
            QPointF(*pos),
            QPointF(*pos),
            button,
            button if evt_type != QEvent.Type.MouseMove else Qt.MouseButton.MiddleButton,
            Qt.KeyboardModifier.NoModifier,
        )

    before = view.mapToScene(QPoint(0, 0))
    view.mousePressEvent(make(QEvent.Type.MouseButtonPress, (50, 50), Qt.MouseButton.MiddleButton))
    view.mouseMoveEvent(make(QEvent.Type.MouseMove, (80, 70), Qt.MouseButton.NoButton))
    view.mouseReleaseEvent(make(QEvent.Type.MouseButtonRelease, (80, 70), Qt.MouseButton.MiddleButton))
    after = view.mapToScene(QPoint(0, 0))
    assert (after - before).manhattanLength() > 0
