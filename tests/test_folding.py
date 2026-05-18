from inkfish.folding import FoldRegion, find_fold_regions


def test_markdown_headings_nested() -> None:
    text = "\n".join([
        "# Top",          # 0
        "intro",          # 1
        "## Section A",   # 2
        "a body",         # 3
        "## Section B",   # 4
        "b body",         # 5
        "# Other",        # 6
        "tail",           # 7
    ])
    regions = find_fold_regions(text, ".md")
    assert FoldRegion(0, 5, "heading") in regions
    assert FoldRegion(2, 3, "heading") in regions
    assert FoldRegion(4, 5, "heading") in regions
    assert FoldRegion(6, 7, "heading") in regions


def test_markdown_no_regions_for_single_line_heading() -> None:
    text = "# Only heading"
    assert find_fold_regions(text, ".md") == []


def test_html_paired_tags() -> None:
    text = "\n".join([
        "<html>",     # 0
        "  <body>",   # 1
        "    <p>x</p>",  # 2
        "  </body>",  # 3
        "</html>",    # 4
    ])
    regions = find_fold_regions(text, ".html")
    assert FoldRegion(0, 3, "tag") in regions
    assert FoldRegion(1, 2, "tag") in regions


def test_html_void_tags_ignored() -> None:
    text = "<br>\n<img src='x'>\n<p>hi\n</p>"
    regions = find_fold_regions(text, ".html")
    # <br> and <img> are void → no regions for them. <p> opens on line 2, closes on
    # line 3, so the hidden span is line 2..2.
    assert regions == [FoldRegion(2, 2, "tag")]


def test_bracket_multiline() -> None:
    text = "\n".join([
        "func(",  # 0
        "  a,",   # 1
        "  b,",   # 2
        ")",      # 3
    ])
    regions = find_fold_regions(text, ".txt")
    assert FoldRegion(0, 2, "bracket") in regions


def test_bracket_single_line_ignored() -> None:
    text = "x = (1 + 2)\ny = [3, 4]"
    assert find_fold_regions(text, ".txt") == []
