"""DocumentItem — QGraphicsTextItem wrapping a QTextDocument with fold support."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QTextCursor, QTextDocument
from PyQt6.QtWidgets import QGraphicsTextItem

from .folding import FoldRegion, find_fold_regions


@dataclass
class _FoldedSection:
    region: FoldRegion
    hidden_lines: list[str]
    placeholder_line_index: int


class DocumentItem(QGraphicsTextItem):
    def __init__(self) -> None:
        super().__init__()
        font = QFont("Courier New")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(11)
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setTextWidth(900)
        self._folds: dict[int, _FoldedSection] = {}

    # ---- text accessors -------------------------------------------------------

    def text(self) -> str:
        return self.document().toPlainText()

    def set_text(self, text: str) -> None:
        self._folds.clear()
        self.document().setPlainText(text)

    def set_markdown(self, text: str) -> None:
        self._folds.clear()
        self.document().setMarkdown(text)

    def set_html(self, text: str) -> None:
        self._folds.clear()
        self.document().setHtml(text)

    def set_editable(self, editable: bool) -> None:
        if editable:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        else:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    # ---- folding --------------------------------------------------------------

    def toggle_fold_at_cursor(self, ext: str) -> None:
        cursor = self.textCursor()
        line = cursor.blockNumber()
        # If we're on a placeholder, unfold it.
        for start, section in list(self._folds.items()):
            if section.placeholder_line_index == line:
                self._unfold(start, section)
                return
        regions = find_fold_regions(self.text(), ext)
        # Find the innermost region whose start_line == this line, otherwise the
        # smallest region that contains the cursor.
        candidates = [r for r in regions if r.start_line == line]
        if not candidates:
            containing = [r for r in regions if r.start_line <= line <= r.end_line]
            if not containing:
                return
            containing.sort(key=lambda r: r.end_line - r.start_line)
            region = containing[0]
        else:
            region = candidates[0]
        if region.start_line in self._folds:
            self._unfold(region.start_line, self._folds[region.start_line])
        else:
            self._fold(region)

    def _fold(self, region: FoldRegion) -> None:
        doc = self.document()
        if region.start_line >= doc.blockCount():
            return
        first_block = doc.findBlockByNumber(region.start_line + 1)
        if not first_block.isValid():
            return
        last_block = doc.findBlockByNumber(region.end_line)
        if not last_block.isValid():
            last_block = doc.lastBlock()

        cursor = QTextCursor(first_block)
        cursor.beginEditBlock()
        end_pos = last_block.position() + last_block.length() - 1
        cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        hidden_text = cursor.selectedText().replace(" ", "\n")
        cursor.removeSelectedText()
        placeholder = f"⋯ ({region.end_line - region.start_line} lines)"
        cursor.insertText(placeholder)
        cursor.endEditBlock()

        self._folds[region.start_line] = _FoldedSection(
            region=region,
            hidden_lines=hidden_text.split("\n"),
            placeholder_line_index=region.start_line + 1,
        )

    def _unfold(self, start: int, section: _FoldedSection) -> None:
        doc = self.document()
        block = doc.findBlockByNumber(section.placeholder_line_index)
        if not block.isValid():
            self._folds.pop(start, None)
            return
        cursor = QTextCursor(block)
        cursor.beginEditBlock()
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
        cursor.removeSelectedText()
        cursor.insertText("\n".join(section.hidden_lines))
        cursor.endEditBlock()
        self._folds.pop(start, None)
