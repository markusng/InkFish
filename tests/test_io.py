from pathlib import Path

import pytest

from inkfish.io import SUPPORTED_EXTS, load_file, save_file


@pytest.mark.parametrize("ext", sorted(SUPPORTED_EXTS))
def test_roundtrip_supported(ext: str, tmp_path: Path) -> None:
    sample = "hello\nworld\n— inkfish"
    path = tmp_path / f"sample{ext}"
    save_file(path, sample)
    text, got_ext = load_file(path)
    assert text == sample
    assert got_ext == ext


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    path = tmp_path / "sample.py"
    path.write_text("print('hi')", encoding="utf-8")
    with pytest.raises(ValueError):
        load_file(path)
    with pytest.raises(ValueError):
        save_file(tmp_path / "x.py", "y")


def test_case_insensitive_extension(tmp_path: Path) -> None:
    path = tmp_path / "sample.MD"
    save_file(path, "# hi")
    text, ext = load_file(path)
    assert text == "# hi"
    assert ext == ".md"
