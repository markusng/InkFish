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


def test_unsupported_extension_defaults_to_txt(tmp_path: Path) -> None:
    path = tmp_path / "sample.xyz"
    path.write_text("data", encoding="utf-8")
    text, ext = load_file(path)
    assert text == "data"
    assert ext == ".txt"


def test_unsupported_extension_save_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "x.xyz"
    save_file(path, "hello")
    assert path.read_text(encoding="utf-8") == "hello"


def test_case_insensitive_extension(tmp_path: Path) -> None:
    path = tmp_path / "sample.MD"
    save_file(path, "# hi")
    text, ext = load_file(path)
    assert text == "# hi"
    assert ext == ".md"
