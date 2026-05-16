from dataclasses import dataclass, field

from inkfish.modes import Mode, apply_mode, is_toggleable


@dataclass
class StubItem:
    calls: list[tuple[str, str]] = field(default_factory=list)

    def set_text(self, text: str) -> None:
        self.calls.append(("text", text))

    def set_markdown(self, text: str) -> None:
        self.calls.append(("markdown", text))

    def set_html(self, text: str) -> None:
        self.calls.append(("html", text))


def test_is_toggleable() -> None:
    assert is_toggleable(".md")
    assert is_toggleable(".html")
    assert is_toggleable(".MD")
    assert not is_toggleable(".txt")
    assert not is_toggleable("")


def test_md_rendered_uses_markdown() -> None:
    item = StubItem()
    apply_mode(item, "# title", ".md", Mode.RENDERED)
    assert item.calls == [("markdown", "# title")]


def test_md_source_uses_plain_text() -> None:
    item = StubItem()
    apply_mode(item, "# title", ".md", Mode.SOURCE)
    assert item.calls == [("text", "# title")]


def test_html_rendered_uses_html() -> None:
    item = StubItem()
    apply_mode(item, "<b>hi</b>", ".html", Mode.RENDERED)
    assert item.calls == [("html", "<b>hi</b>")]


def test_txt_always_plain_text() -> None:
    item = StubItem()
    apply_mode(item, "abc", ".txt", Mode.RENDERED)
    apply_mode(item, "abc", ".txt", Mode.SOURCE)
    assert item.calls == [("text", "abc"), ("text", "abc")]
