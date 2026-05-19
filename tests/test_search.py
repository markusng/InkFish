"""Tests for vim '/' / 'n' / 'N' search behaviour."""
from __future__ import annotations

import pytest

from inkfish.canvas import InkfishView


@pytest.fixture
def view(qtbot):
    v = InkfishView()
    qtbot.addWidget(v)
    v.resize(400, 300)
    v.show()
    qtbot.waitExposed(v)
    return v


def _set_text(view: InkfishView, text: str) -> None:
    view.document_item.setPlainText(text)


def _cursor_pos(view: InkfishView) -> int:
    return view.document_item.textCursor().position()


def _set_cursor(view: InkfishView, pos: int) -> None:
    c = view.document_item.textCursor()
    c.setPosition(pos)
    view.document_item.setTextCursor(c)


def test_do_search_forward_moves_cursor(view: InkfishView) -> None:
    _set_text(view, "alpha beta gamma delta")
    _set_cursor(view, 0)
    view.document_item.do_search("gamma", forward=True)
    pos = _cursor_pos(view)
    # Cursor should now be at the end of "gamma" (find selects the match,
    # cursor lands at end of selection).
    assert pos == len("alpha beta gamma")


def test_do_search_remembers_last_pattern(view: InkfishView) -> None:
    _set_text(view, "foo bar foo baz foo")
    _set_cursor(view, 0)
    view.document_item.do_search("foo", forward=True)
    first = _cursor_pos(view)
    # Repeat with empty pattern (simulates 'n')
    view.document_item.do_search("", forward=True)
    second = _cursor_pos(view)
    assert second > first


def test_do_search_wraps_around(view: InkfishView) -> None:
    _set_text(view, "needle haystack haystack")
    # Position cursor past the only "needle"
    _set_cursor(view, 10)
    view.document_item.do_search("needle", forward=True)
    pos = _cursor_pos(view)
    # Should have wrapped back to the start and found "needle" at the beginning.
    assert pos == len("needle")


def test_search_next_backward(view: InkfishView) -> None:
    _set_text(view, "foo bar foo baz foo")
    _set_cursor(view, 0)
    view.document_item.do_search("foo", forward=True)  # establishes _last_search
    # Move past the last "foo" so 'N' has something behind us.
    _set_cursor(view, len("foo bar foo baz foo"))
    view.document_item.do_search("", forward=False)
    c = view.document_item.textCursor()
    # Backward find should land on the last "foo" in the text (positions 16-19).
    # Qt returns the cursor with anchor/position spanning the match; check both ends.
    assert min(c.position(), c.anchor()) == len("foo bar foo baz ")
    assert max(c.position(), c.anchor()) == len("foo bar foo baz foo")
