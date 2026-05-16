"""Canvas mouse fallback + zoom/pan API."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QWheelEvent
from PyQt6.QtCore import QEvent

from inkfish.canvas import InkfishView


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
    view.zoom_to(1000.0)
    assert view.current_scale() <= 20.0 + 1e-6
    view.zoom_to(1e-6)
    assert view.current_scale() >= 0.1 - 1e-6


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
