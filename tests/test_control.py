from dino_vision.control import GameControl


def test_auto_selects_ydotool_on_wayland(monkeypatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("WSL_INTEROP", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    assert GameControl._select_backend("auto") == "ydotool"


def test_auto_selects_pyautogui_on_wsl(monkeypatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("WSL_INTEROP", "/run/WSL/interop")
    assert GameControl._select_backend("auto") == "pyautogui"


def test_explicit_backend_does_not_depend_on_session(monkeypatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert GameControl._select_backend("ydotool") == "ydotool"


def test_cdp_backend_is_accepted() -> None:
    assert GameControl._select_backend("cdp") == "cdp"
