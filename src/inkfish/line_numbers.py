"""LineNumberItem — QGraphicsItem that draws line numbers left of DocumentItem."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetricsF, QPainter
from PyQt6.QtWidgets import QGraphicsItem

_PAD = 6.0          # horizontal padding inside the gutter on each side
_GAP = 4.0          # gap between gutter right edge and document left edge
_FG  = QColor("#707070")
_BG  = QColor("#161b22")


class LineNumberItem(QGraphicsItem):
    """Draws line numbers in a gutter to the left of a DocumentItem."""

    def __init__(self, doc_item) -> None:
        super().__init__()
        self._doc_item = doc_item
        self._gutter_w = 40.0
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        doc_item.document().contentsChanged.connect(self._refresh)
        doc_item.document().blockCountChanged.connect(self._refresh)
        self._refresh()

    # ---- QGraphicsItem interface ----------------------------------------------

    def boundingRect(self) -> QRectF:
        h = max(self._doc_item.document().documentLayout().documentSize().height(), 100.0)
        return QRectF(0.0, 0.0, self._gutter_w, h)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        r = self.boundingRect()
        painter.fillRect(r, _BG)

        doc = self._doc_item.document()
        dl = doc.documentLayout()
        painter.setFont(self._doc_item.font())
        painter.setPen(_FG)

        block = doc.begin()
        n = 1
        while block.isValid():
            br = dl.blockBoundingRect(block)
            if br.height() > 0:
                painter.drawText(
                    QRectF(0.0, br.y(), self._gutter_w - _PAD, br.height()),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                    str(n),
                )
            block = block.next()
            n += 1

    # ---- geometry update ------------------------------------------------------

    def _refresh(self) -> None:
        count = max(self._doc_item.document().blockCount(), 1)
        fm = QFontMetricsF(self._doc_item.font())
        self._gutter_w = fm.horizontalAdvance("0" * len(str(count))) + _PAD * 2
        self.prepareGeometryChange()
        doc_pos = self._doc_item.pos()
        self.setPos(doc_pos.x() - self._gutter_w - _GAP, doc_pos.y())
        self.update()
