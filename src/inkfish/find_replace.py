"""Find / Replace bar — inline panel docked at the bottom of EditorPane."""
from __future__ import annotations

from PyQt6.QtCore import QRegularExpression, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor, QTextDocument
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

_STYLE_OK  = ""
_STYLE_BAD = "QLineEdit { border: 1px solid #e05050; background: #3a1a1a; }"


class FindReplaceBar(QWidget):
    """Compact two-row find/replace panel; hidden by default."""

    closed = pyqtSignal()

    def __init__(self, pane, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pane = pane
        self._doc_item = pane._doc_item
        self._last_flags = QTextDocument.FindFlag(0)
        self._build_ui()
        self.setVisible(False)

    # ---- construction ---------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(2)

        # ---- find row ----
        find_row = QHBoxLayout()
        find_row.setSpacing(4)

        find_lbl = QLabel("Find:")
        find_lbl.setFixedWidth(52)
        find_row.addWidget(find_lbl)

        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("search…")
        self._find_edit.returnPressed.connect(self._find_next)
        self._find_edit.textChanged.connect(self._on_pattern_changed)
        find_row.addWidget(self._find_edit, 1)

        self._regex_cb = QCheckBox("Regex")
        self._regex_cb.stateChanged.connect(self._on_pattern_changed)
        find_row.addWidget(self._regex_cb)

        self._case_cb = QCheckBox("Case")
        self._case_cb.stateChanged.connect(self._on_pattern_changed)
        find_row.addWidget(self._case_cb)

        btn_prev = QPushButton("▲")
        btn_prev.setFixedWidth(28)
        btn_prev.setToolTip("Find previous (Shift+Enter)")
        btn_prev.clicked.connect(self._find_prev)
        find_row.addWidget(btn_prev)

        btn_next = QPushButton("▼")
        btn_next.setFixedWidth(28)
        btn_next.setToolTip("Find next (Enter)")
        btn_next.clicked.connect(self._find_next)
        find_row.addWidget(btn_next)

        self._count_lbl = QLabel("")
        self._count_lbl.setFixedWidth(72)
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._count_lbl.setStyleSheet("color: #888;")
        find_row.addWidget(self._count_lbl)

        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Close (Esc)")
        close_btn.clicked.connect(self.deactivate)
        find_row.addWidget(close_btn)

        root.addLayout(find_row)

        # ---- replace row ----
        self._replace_row = QWidget()
        repl_layout = QHBoxLayout(self._replace_row)
        repl_layout.setContentsMargins(0, 0, 0, 0)
        repl_layout.setSpacing(4)

        repl_lbl = QLabel("Replace:")
        repl_lbl.setFixedWidth(52)
        repl_layout.addWidget(repl_lbl)

        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("replacement…")
        self._replace_edit.returnPressed.connect(self._replace_one)
        repl_layout.addWidget(self._replace_edit, 1)

        btn_repl = QPushButton("Replace")
        btn_repl.clicked.connect(self._replace_one)
        repl_layout.addWidget(btn_repl)

        btn_all = QPushButton("Replace All")
        btn_all.clicked.connect(self._replace_all)
        repl_layout.addWidget(btn_all)

        # spacer to align with close button column
        repl_layout.addSpacing(28 + 4)

        root.addWidget(self._replace_row)

    # ---- public ---------------------------------------------------------------

    def activate(self, replace: bool = False) -> None:
        self.setVisible(True)
        self._replace_row.setVisible(replace)
        self._find_edit.setFocus()
        self._find_edit.selectAll()
        self._update_count()

    def deactivate(self) -> None:
        self.setVisible(False)
        self._count_lbl.setText("")
        self.closed.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.deactivate()
            return
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._find_prev()
            return
        super().keyPressEvent(event)

    # ---- pattern helpers ------------------------------------------------------

    def _make_pattern(self):
        """Return QRegularExpression (regex mode) or str, or None if invalid/empty."""
        text = self._find_edit.text()
        if not text:
            return None
        if self._regex_cb.isChecked():
            opts = QRegularExpression.PatternOption.NoPatternOption
            if not self._case_cb.isChecked():
                opts |= QRegularExpression.PatternOption.CaseInsensitiveOption
            rx = QRegularExpression(text, opts)
            if not rx.isValid():
                self._find_edit.setStyleSheet(_STYLE_BAD)
                return None
            self._find_edit.setStyleSheet(_STYLE_OK)
            return rx
        self._find_edit.setStyleSheet(_STYLE_OK)
        return text

    def _find_flags(self, forward: bool = True) -> QTextDocument.FindFlag:
        flags = QTextDocument.FindFlag(0)
        if not forward:
            flags |= QTextDocument.FindFlag.FindBackward
        # case sensitivity only relevant for plain-text search
        if self._case_cb.isChecked() and not self._regex_cb.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        return flags

    # ---- find -----------------------------------------------------------------

    def _find_next(self) -> None:
        self._search(forward=True)

    def _find_prev(self) -> None:
        self._search(forward=False)

    def _search(self, forward: bool) -> None:
        pattern = self._make_pattern()
        if pattern is None:
            return
        doc   = self._doc_item.document()
        start = self._doc_item.textCursor()
        # For forward: search from end of selection; backward: from start
        if forward:
            start.setPosition(start.selectionEnd())
        else:
            start.setPosition(start.selectionStart())

        found = doc.find(pattern, start, self._find_flags(forward))
        if found.isNull():
            # Wrap around
            wrap = QTextCursor(doc)
            if forward:
                wrap.movePosition(QTextCursor.MoveOperation.Start)
            else:
                wrap.movePosition(QTextCursor.MoveOperation.End)
            found = doc.find(pattern, wrap, self._find_flags(forward))

        if not found.isNull():
            self._doc_item.setTextCursor(found)
            self._pane.center_on_cursor()
        self._update_count()

    # ---- replace --------------------------------------------------------------

    def _replace_one(self) -> None:
        pattern = self._make_pattern()
        if pattern is None:
            return
        cursor = self._doc_item.textCursor()
        replacement = self._replace_edit.text()

        # Check if current selection matches the pattern
        if cursor.hasSelection():
            selected = cursor.selectedText()
            is_match = False
            if isinstance(pattern, QRegularExpression):
                m = pattern.match(selected)
                is_match = m.hasMatch() and m.capturedLength() == len(selected)
            else:
                is_match = (
                    selected == pattern if self._case_cb.isChecked()
                    else selected.lower() == pattern.lower()
                )
            if is_match:
                cursor.insertText(replacement)

        # Move to next match
        self._search(forward=True)

    def _replace_all(self) -> None:
        pattern = self._make_pattern()
        if pattern is None:
            return
        doc = self._doc_item.document()
        replacement = self._replace_edit.text()
        flags = self._find_flags(forward=True)

        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        count = 0
        cursor.beginEditBlock()
        while True:
            found = doc.find(pattern, cursor, flags)
            if found.isNull():
                break
            found.insertText(replacement)
            cursor.setPosition(found.position())
            count += 1
        cursor.endEditBlock()
        self._count_lbl.setText(f"{count} replaced")

    # ---- match count ----------------------------------------------------------

    def _on_pattern_changed(self) -> None:
        self._update_count()

    def _update_count(self) -> None:
        pattern = self._make_pattern()
        if pattern is None:
            self._count_lbl.setText("")
            return
        doc = self._doc_item.document()
        flags = self._find_flags(forward=True)
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        total = 0
        current_idx = 0
        sel_start = self._doc_item.textCursor().selectionStart()
        while True:
            found = doc.find(pattern, cursor, flags)
            if found.isNull():
                break
            total += 1
            if found.selectionStart() <= sel_start:
                current_idx = total
            cursor.setPosition(found.selectionEnd())
        if total == 0:
            self._count_lbl.setText("no matches")
            self._count_lbl.setStyleSheet("color: #e05050;")
        else:
            self._count_lbl.setText(f"{current_idx} / {total}")
            self._count_lbl.setStyleSheet("color: #888;")
