import inkfish.app


def test_main_is_callable() -> None:
    assert callable(inkfish.app.main)


def test_version_flag(capsys) -> None:
    rc = inkfish.app.main(["--version"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out  # something printed
