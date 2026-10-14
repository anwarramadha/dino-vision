from dino_vision.capture import ScreenCapture


def test_auto_selects_cdp_on_wsl(monkeypatch) -> None:
    monkeypatch.setenv("WSL_INTEROP", "/run/WSL/interop")
    assert ScreenCapture._select_backend("auto") == "cdp"


def test_auto_selects_mss_outside_wsl(monkeypatch) -> None:
    monkeypatch.delenv("WSL_INTEROP", raising=False)
    assert ScreenCapture._select_backend("auto") == "mss"
