"""DocumentItem — QGraphicsTextItem wrapping a QTextDocument with fold support."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QFontMetricsF, QKeyEvent, QPainter, QTextCursor, QTextDocument,
)
from PyQt6.QtWidgets import QGraphicsTextItem, QStyleOptionGraphicsItem

from . import lod
from .folding import FoldRegion, find_fold_regions


@dataclass
class _FoldedSection:
    region: FoldRegion
    hidden_lines: list[str]
    placeholder_line_index: int


# Motion string → QTextCursor.MoveOperation mapping
_MO = QTextCursor.MoveOperation
_MM = QTextCursor.MoveMode

_SIMPLE_MOTIONS: dict[str, QTextCursor.MoveOperation] = {
    "left":             _MO.Left,
    "right":            _MO.Right,
    "up":               _MO.Up,
    "down":             _MO.Down,
    "word_next":        _MO.NextWord,
    "word_prev":        _MO.PreviousWord,
    "word_end":         _MO.EndOfWord,
    "line_start":       _MO.StartOfLine,
    "line_end":         _MO.EndOfLine,
    "start":            _MO.Start,
    "end":              _MO.End,
    "para_prev":        _MO.PreviousBlock,
    "para_next":        _MO.NextBlock,
}


class DocumentItem(QGraphicsTextItem):
    # Vim signals — emitted when engine produces the corresponding action
    vim_mode_changed   = pyqtSignal(str)   # mode.name
    ex_command         = pyqtSignal(str)   # ex command string
    command_buf_changed = pyqtSignal(str)  # current : buffer text
    scroll_half_page   = pyqtSignal(bool)  # True = down
    scroll_page        = pyqtSignal(bool)  # True = down (full page)
    search_requested   = pyqtSignal(str)   # pattern (empty = prompt user)
    search_next_signal = pyqtSignal(bool)  # True = forward

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
        self._vim = None          # VimEngine | None
        self._last_search: str = ""

        fm = QFontMetricsF(font)
        self._font_line_height_px: float = fm.height()
        self._char_w: float = fm.horizontalAdvance("M")
        self._dom_color_cache: dict[int, tuple[int, QColor]] = {}

    _DOM_COLOR_CACHE_MAX = 50000

    # ---- paint (LOD optimisation) ---------------------------------------------

    def paint(self, painter: QPainter, option, widget=None) -> None:
        if lod.lod_enabled():
            lod_val = QStyleOptionGraphicsItem.levelOfDetailFromTransform(
                painter.worldTransform()
            )
            if self._font_line_height_px * lod_val < lod.threshold_px():
                self._paint_lod(painter, option.exposedRect)
                return
        super().paint(painter, option, widget)

    def _paint_lod(self, painter: QPainter, exposed: QRectF) -> None:
        doc = self.document()
        dl = doc.documentLayout()
        pos = dl.hitTest(QPointF(0.0, exposed.top()), Qt.HitTestAccuracy.FuzzyHit)
        if pos < 0:
            pos = 0
        block = doc.findBlock(pos)
        if not block.isValid():
            return
        bottom_y = exposed.bottom()
        char_w = self._char_w
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)
        while block.isValid():
            br = dl.blockBoundingRect(block)
            if br.top() > bottom_y:
                break
            text = block.text()
            n = len(text.rstrip())
            if n > 0:
                indent = len(text) - len(text.lstrip())
                w = (n - indent) * char_w
                if w > 0.0:
                    color = self._dominant_color(block)
                    x = br.left() + indent * char_w
                    y = br.top() + br.height() * 0.3
                    h = br.height() * 0.4
                    painter.fillRect(QRectF(x, y, w, h), color)
            block = block.next()
        painter.restore()

    def _dominant_color(self, block) -> QColor:
        key = block.blockNumber()
        rev = block.revision()
        entry = self._dom_color_cache.get(key)
        if entry is not None and entry[0] == rev:
            return entry[1]
        color = lod.FALLBACK_BAR_COLOR
        layout = block.layout()
        if layout is not None:
            best_len = 0
            for fr in layout.formats():
                if fr.length > best_len:
                    fg = fr.format.foreground()
                    if fg.style() != Qt.BrushStyle.NoBrush:
                        color = fg.color()
                        best_len = fr.length
        if len(self._dom_color_cache) >= self._DOM_COLOR_CACHE_MAX:
            self._dom_color_cache.clear()
        self._dom_color_cache[key] = (rev, color)
        return color

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

    # ---- Vim integration ------------------------------------------------------

    def set_vim(self, engine) -> None:
        """Enable (engine is VimEngine) or disable (engine is None) Vim mode."""
        self._vim = engine
        self._sync_interaction_flags()

    def is_vim_navigation_mode(self) -> bool:
        """True when vim is active and in NORMAL/VISUAL/VISUAL_LINE (not INSERT/COMMAND)."""
        if self._vim is None:
            return False
        from .vim import VimMode
        return self._vim.mode in (VimMode.NORMAL, VimMode.VISUAL, VimMode.VISUAL_LINE)

    def _sync_interaction_flags(self) -> None:
        from .vim import VimMode
        if self._vim is None or self._vim.mode == VimMode.INSERT:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        else:
            # Keep cursor visible; our keyPressEvent intercepts keys before Qt edits
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._vim is None:
            super().keyPressEvent(event)
            return

        from .vim import VimMode
        actions = self._vim.process_key(event.key(), event.modifiers().value, event.text())

        if self._vim.mode == VimMode.INSERT and not actions:
            # Handle insert-mode shortcuts not covered by Qt natively
            ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
            if ctrl and event.key() == Qt.Key.Key_W:
                cursor = self.textCursor()
                cursor.movePosition(_MO.PreviousWord, _MM.KeepAnchor)
                cursor.removeSelectedText()
                event.accept()
                return
            if ctrl and event.key() == Qt.Key.Key_U:
                cursor = self.textCursor()
                cursor.movePosition(_MO.StartOfLine, _MM.KeepAnchor)
                cursor.removeSelectedText()
                event.accept()
                return
            # Normal typing — let Qt handle it
            super().keyPressEvent(event)
            return

        self._apply_vim_actions(actions)
        event.accept()

    def _apply_vim_actions(self, actions: list) -> None:
        from .vim import (
            ChangeMode, DeleteChar, DeleteMotion, ExCommand,
            FindChar, JoinLines, JumpToMark, MoveCursor, OpenLine,
            PasteAfter, PasteBefore, Redo, ReplaceChar, ScrollHalfPage,
            ScrollPage, SearchForward, SearchNext, SetMark, ToggleCase, Undo,
            UpdateCommandBuf, YankMotion, VimMode,
        )
        cursor = self.textCursor()
        pending_mode: str | None = None
        pending_ex: str | None = None

        for action in actions:
            if isinstance(action, ChangeMode):
                pending_mode = action.mode.name
                self._vim.state.mode = action.mode
                self._sync_interaction_flags()

            elif isinstance(action, MoveCursor):
                self._apply_move(cursor, action.motion, action.count, action.keep_anchor)

            elif isinstance(action, DeleteMotion):
                self._apply_delete(cursor, action.motion, action.count)
                cursor = self.textCursor()

            elif isinstance(action, YankMotion):
                self._apply_yank(cursor, action.motion, action.count)

            elif isinstance(action, PasteAfter):
                self._apply_paste(cursor, after=True)
                cursor = self.textCursor()

            elif isinstance(action, PasteBefore):
                self._apply_paste(cursor, after=False)
                cursor = self.textCursor()

            elif isinstance(action, Undo):
                self.document().undo()
                cursor = self.textCursor()

            elif isinstance(action, Redo):
                self.document().redo()
                cursor = self.textCursor()

            elif isinstance(action, OpenLine):
                self._apply_open_line(cursor, action.above)
                cursor = self.textCursor()

            elif isinstance(action, ReplaceChar):
                self._apply_replace_char(cursor, action.char)

            elif isinstance(action, DeleteChar):
                self._apply_delete_char(cursor, action.before, action.count)
                cursor = self.textCursor()

            elif isinstance(action, ToggleCase):
                self._apply_toggle_case(cursor)

            elif isinstance(action, JoinLines):
                self._apply_join_lines(cursor, action.count)

            elif isinstance(action, FindChar):
                self._apply_find_char(cursor, action.char, action.forward, action.till)

            elif isinstance(action, ScrollHalfPage):
                self.scroll_half_page.emit(action.down)

            elif isinstance(action, ScrollPage):
                self.scroll_page.emit(action.down)

            elif isinstance(action, SearchForward):
                if action.pattern == "__word_under_cursor__":
                    pat = self._word_under_cursor(cursor)
                else:
                    pat = action.pattern
                self.search_requested.emit(pat)

            elif isinstance(action, SearchNext):
                self.search_next_signal.emit(not action.reverse)

            elif isinstance(action, SetMark):
                if self._vim:
                    self._vim.state.marks[action.name] = cursor.position()

            elif isinstance(action, JumpToMark):
                if self._vim:
                    pos = self._vim.state.marks.get(action.name)
                    if pos is not None:
                        cursor.setPosition(pos)

            elif isinstance(action, UpdateCommandBuf):
                self.command_buf_changed.emit(action.buf)

            elif isinstance(action, ExCommand):
                pending_ex = action.command

        self.setTextCursor(cursor)
        if pending_mode is not None:
            self.vim_mode_changed.emit(pending_mode)
        if pending_ex is not None:
            self.ex_command.emit(pending_ex)

    # ---- Vim cursor helpers ---------------------------------------------------

    def _apply_move(self, cursor: QTextCursor, motion: str, count: int,
                    keep_anchor: bool = False) -> None:
        mode = _MM.KeepAnchor if keep_anchor else _MM.MoveAnchor

        if motion in _SIMPLE_MOTIONS:
            for _ in range(count):
                cursor.movePosition(_SIMPLE_MOTIONS[motion], mode)

        elif motion == "line_start_nonws":
            cursor.movePosition(_MO.StartOfLine, mode)
            block_text = cursor.block().text()
            ws = len(block_text) - len(block_text.lstrip())
            cursor.movePosition(_MO.Right, mode, ws)

        elif motion == "line_n":
            block = self.document().findBlockByNumber(count - 1)
            if block.isValid():
                cursor.setPosition(block.position(), mode)

        elif motion in ("WORD_next", "WORD_prev", "WORD_end"):
            full = self.document().toPlainText()
            pos = cursor.position()
            for _ in range(count):
                pos = self._word_pos(full, pos, motion)
            cursor.setPosition(pos, mode)

        elif motion == "selection_other_end":
            anchor = cursor.anchor()
            pos = cursor.position()
            cursor.setPosition(pos, _MM.MoveAnchor)
            cursor.setPosition(anchor, _MM.KeepAnchor)

        self.setTextCursor(cursor)

    def _word_pos(self, text: str, pos: int, motion: str) -> int:
        n = len(text)
        if motion == "WORD_next":
            while pos < n and not text[pos].isspace():
                pos += 1
            while pos < n and text[pos].isspace():
                pos += 1
        elif motion == "WORD_prev":
            pos = max(0, pos - 1)
            while pos > 0 and text[pos].isspace():
                pos -= 1
            while pos > 0 and not text[pos - 1].isspace():
                pos -= 1
        elif motion == "WORD_end":
            pos += 1
            while pos < n and text[pos].isspace():
                pos += 1
            while pos < n and not text[pos].isspace():
                pos += 1
            pos = max(0, pos - 1)
        return max(0, min(n, pos))

    def _select_by_motion(self, cursor: QTextCursor, motion, count: int) -> None:
        """Extend cursor selection to cover the region defined by motion."""
        from .vim import FindChar
        if isinstance(motion, FindChar):
            self._apply_find_char(cursor, motion.char, motion.forward, motion.till,
                                  keep_anchor=True)
            return
        if motion == "selection":
            return  # already selected in visual mode
        if motion == "line":
            self._select_lines(cursor, count)
            return
        if motion == "to_line_end":
            cursor.movePosition(_MO.EndOfLine, _MM.KeepAnchor)
            return
        if motion in _SIMPLE_MOTIONS:
            for _ in range(count):
                cursor.movePosition(_SIMPLE_MOTIONS[motion], _MM.KeepAnchor)
        elif motion in ("WORD_next", "WORD_prev", "WORD_end"):
            full = self.document().toPlainText()
            pos = cursor.position()
            for _ in range(count):
                pos = self._word_pos(full, pos, motion)
            cursor.setPosition(pos, _MM.KeepAnchor)
        elif motion == "line_start_nonws":
            cursor.movePosition(_MO.StartOfLine, _MM.KeepAnchor)
        elif motion == "line_n":
            block = self.document().findBlockByNumber(count - 1)
            if block.isValid():
                cursor.setPosition(block.position(), _MM.KeepAnchor)
        elif motion == "start":
            cursor.movePosition(_MO.Start, _MM.KeepAnchor)
        elif motion == "end":
            cursor.movePosition(_MO.End, _MM.KeepAnchor)

    def _select_lines(self, cursor: QTextCursor, count: int) -> None:
        """Select count complete lines including the trailing newline."""
        block = cursor.block()
        start = block.position()
        for _ in range(count - 1):
            nxt = block.next()
            if nxt.isValid():
                block = nxt
        if block.next().isValid():
            end = block.position() + block.length()  # includes \n
        else:
            # Last block — include preceding \n instead
            end = block.position() + block.length()
            if start > 0:
                start -= 1
        end = min(end, self.document().characterCount())
        cursor.setPosition(start)
        cursor.setPosition(end, _MM.KeepAnchor)

    def _apply_delete(self, cursor: QTextCursor, motion, count: int) -> None:
        from .vim import FindChar
        if motion == "selection":
            if self._vim:
                self._vim.state.register = cursor.selectedText().replace(" ", "\n")
            cursor.removeSelectedText()
            self.setTextCursor(cursor)
            return
        self._select_by_motion(cursor, motion, count)
        if self._vim:
            self._vim.state.register = cursor.selectedText().replace(" ", "\n")
        cursor.removeSelectedText()
        self.setTextCursor(cursor)

    def _apply_yank(self, cursor: QTextCursor, motion, count: int) -> None:
        saved = cursor.position()
        self._select_by_motion(cursor, motion, count)
        if self._vim:
            self._vim.state.register = cursor.selectedText().replace(" ", "\n")
        cursor.setPosition(saved)
        self.setTextCursor(cursor)

    def _apply_paste(self, cursor: QTextCursor, after: bool) -> None:
        if not self._vim:
            return
        text = self._vim.state.register
        if not text:
            return
        if after:
            cursor.movePosition(_MO.Right)
        cursor.insertText(text)
        self.setTextCursor(cursor)

    def _apply_delete_char(self, cursor: QTextCursor, before: bool, count: int) -> None:
        for _ in range(count):
            if before:
                cursor.deletePreviousChar()
            else:
                cursor.deleteChar()
        self.setTextCursor(cursor)

    def _apply_replace_char(self, cursor: QTextCursor, char: str) -> None:
        cursor.deleteChar()
        cursor.insertText(char)
        cursor.movePosition(_MO.Left)
        self.setTextCursor(cursor)

    def _apply_toggle_case(self, cursor: QTextCursor) -> None:
        if cursor.hasSelection():
            text = cursor.selectedText()
            toggled = "".join(c.lower() if c.isupper() else c.upper() for c in text)
            cursor.insertText(toggled)
        else:
            cursor.movePosition(_MO.Right, _MM.KeepAnchor)
            ch = cursor.selectedText()
            if ch:
                cursor.insertText(ch.lower() if ch.isupper() else ch.upper())
        self.setTextCursor(cursor)

    def _apply_join_lines(self, cursor: QTextCursor, count: int) -> None:
        for _ in range(count):
            cursor.movePosition(_MO.EndOfLine)
            if not cursor.atEnd():
                cursor.deleteChar()         # delete \n
                cursor.insertText(" ")      # replace with space
                cursor.movePosition(_MO.Left)
        self.setTextCursor(cursor)

    def _apply_find_char(self, cursor: QTextCursor, char: str, forward: bool,
                         till: bool, keep_anchor: bool = False) -> None:
        mode = _MM.KeepAnchor if keep_anchor else _MM.MoveAnchor
        block_text = cursor.block().text()
        col = cursor.positionInBlock()
        if forward:
            idx = block_text.find(char, col + 1)
            if idx >= 0:
                target = idx - 1 if till else idx
                cursor.movePosition(_MO.StartOfLine, mode)
                cursor.movePosition(_MO.Right, mode, target)
        else:
            idx = block_text.rfind(char, 0, col)
            if idx >= 0:
                target = idx + 1 if till else idx
                cursor.movePosition(_MO.StartOfLine, mode)
                cursor.movePosition(_MO.Right, mode, target)
        self.setTextCursor(cursor)

    def _apply_open_line(self, cursor: QTextCursor, above: bool) -> None:
        if above:
            cursor.movePosition(_MO.StartOfLine)
            cursor.insertText("\n")
            cursor.movePosition(_MO.Up)
        else:
            cursor.movePosition(_MO.EndOfLine)
            cursor.insertText("\n")
        self.setTextCursor(cursor)

    def _word_under_cursor(self, cursor: QTextCursor) -> str:
        c = QTextCursor(cursor)
        c.select(QTextCursor.SelectionType.WordUnderCursor)
        return c.selectedText()

    def do_search(self, pattern: str, forward: bool = True) -> None:
        """Search for pattern in document, wrapping around."""
        if pattern:
            self._last_search = pattern
        else:
            pattern = self._last_search
        if not pattern:
            return
        flags = QTextDocument.FindFlag(0)
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
        result = self.document().find(pattern, self.textCursor(), flags)
        if result.isNull():
            # wrap around
            start = QTextCursor(self.document())
            if not forward:
                start.movePosition(_MO.End)
            result = self.document().find(pattern, start, flags)
        if not result.isNull():
            self.setTextCursor(result)

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
        hidden_text = cursor.selectedText().replace(" ", "\n")
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
