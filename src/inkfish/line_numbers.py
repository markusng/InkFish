"""LineNumberItem — QGraphicsItem that draws line numbers left of DocumentItem."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
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
        # contentsChanged fires on every keystroke — only a visual refresh is needed.
        # blockCountChanged drives geometry (gutter width may change at decade boundaries).
        doc_item.document().contentsChanged.connect(self.update)
        doc_item.document().blockCountChanged.connect(self._refresh)
        self._refresh()

    # ---- QGraphicsItem interface ----------------------------------------------

    def boundingRect(self) -> QRectF:
        h = max(self._doc_item.document().documentLayout().documentSize().height(), 100.0)
        return QRectF(0.0, 0.0, self._gutter_w, h)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.save()
        exposed = option.exposedRect
        painter.fillRect(exposed, _BG)

        doc = self._doc_item.document()
        dl = doc.documentLayout()
        painter.setFont(self._doc_item.font())
        painter.setPen(_FG)

        # LineNumberItem is positioned to align vertically with DocumentItem,
        # so local-y maps directly to document-y for hit testing.
        top_y = exposed.top()
        bottom_y = exposed.bottom()
        pos = dl.hitTest(QPointF(0.0, top_y), Qt.HitTestAccuracy.FuzzyHit)
        if pos < 0:
            pos = 0
        block = doc.findBlock(pos)
        while block.isValid():
            br = dl.blockBoundingRect(block)
            if br.top() > bottom_y:
                break
            if br.height() > 0:
                painter.drawText(
                    QRectF(0.0, br.y(), self._gutter_w - _PAD, br.height()),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                    str(block.blockNumber() + 1),
                )
            block = block.next()
        painter.restore()

    # ---- geometry update ------------------------------------------------------

    def _refresh(self) -> None:
        count = max(self._doc_item.document().blockCount(), 1)
        fm = QFontMetricsF(self._doc_item.font())
        new_w = fm.horizontalAdvance("0" * len(str(count))) + _PAD * 2
        if new_w != self._gutter_w:
            self._gutter_w = new_w
            self.prepareGeometryChange()
            doc_pos = self._doc_item.pos()
            self.setPos(doc_pos.x() - self._gutter_w - _GAP, doc_pos.y())
        self.update()
