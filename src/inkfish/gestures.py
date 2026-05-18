"""Gesture handlers — translate QGestureEvent payloads into view transforms.

Plain classes, not QObjects: they are invoked from `InkfishView.event()` and
have no signals of their own.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QPanGesture, QPinchGesture

if TYPE_CHECKING:
    from .canvas import InkfishView


class PinchHandler:
    def handle(self, view: "InkfishView", gesture: QPinchGesture) -> None:
        changes = gesture.changeFlags()
        if changes & QPinchGesture.ChangeFlag.ScaleFactorChanged:
            factor = gesture.scaleFactor()
            if factor > 0:
                center = QPointF(view.mapFromGlobal(gesture.centerPoint().toPoint()))
                view.zoom_to(factor, anchor=center)


class PanHandler:
    def handle(self, view: "InkfishView", gesture: QPanGesture) -> None:
        delta = gesture.delta()
        view.pan_by(delta.x(), delta.y())
