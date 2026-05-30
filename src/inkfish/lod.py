"""LOD (Level of Detail) state shared by DocumentItem and InkfishView.

Below threshold (rendered pixels per text line), DocumentItem swaps Qt's glyph
pipeline for cheap syntax-coloured density bars, and InkfishView drops the
expensive text/antialiasing render hints. Pinch-zoom remains responsive on
large files because the cost shifts from per-glyph to per-block.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor

DEFAULT_THRESHOLD_PX = 4.0
FALLBACK_BAR_COLOR = QColor("#d4d4d4")

_enabled: bool = True
_threshold_px: float = DEFAULT_THRESHOLD_PX


def lod_enabled() -> bool:
    return _enabled


def set_enabled(value: bool) -> None:
    global _enabled
    _enabled = bool(value)


def threshold_px() -> float:
    return _threshold_px


def set_threshold_px(value: float) -> None:
    global _threshold_px
    try:
        v = float(value)
    except (TypeError, ValueError):
        return
    if v > 0:
        _threshold_px = v


