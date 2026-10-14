import os
import shutil
import subprocess
import time
from typing import Any

from dino_vision.cdp import ChromeDevTools


class GameControl:
    def __init__(self, settings: dict[str, Any]) -> None:
        self.backend = self._select_backend(settings.get("backend", "auto"))
        self.startup_delay = settings.get("startup_delay_seconds", 3)
        self.duck_duration = settings.get("duck_duration_seconds", 0.25)

        if self.backend == "cdp":
            self.cdp = ChromeDevTools(settings.get("cdp_url", "http://127.0.0.1:9222"))
            self.cdp.bring_to_front()
        elif self.backend == "pyautogui":
            # WSLg exposes XWayland without a per-user Xauthority file.
            if self._is_wsl():
                os.environ.setdefault("XAUTHORITY", "/dev/null")
            try:
                import pyautogui
            except Exception as error:
                raise RuntimeError(
                    "pyautogui tidak dapat terhubung ke display. Pada Wayland gunakan "
                    "backend yang sesuai dan lihat docs/setup.md."
                ) from error
            pyautogui.PAUSE = 0
            self.pyautogui = pyautogui

    @staticmethod
    def _is_wsl() -> bool:
        return bool(os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"))

    @staticmethod
    def _select_backend(requested_backend: str) -> str:
        if requested_backend == "auto":
            if GameControl._is_wsl():
                return "pyautogui"
            return "ydotool" if os.environ.get("WAYLAND_DISPLAY") else "pyautogui"
        if requested_backend not in {"pyautogui", "ydotool", "cdp"}:
            raise ValueError("control.backend harus bernilai auto, pyautogui, ydotool, atau cdp.")
        return requested_backend

    def _cdp_key(self, key: str, code: str, keycode: int, pressed: bool) -> None:
        self.cdp.command(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown" if pressed else "keyUp",
                "key": key,
                "code": code,
                "windowsVirtualKeyCode": keycode,
                "nativeVirtualKeyCode": keycode,
            },
        )

    def _ydotool_key(self, keycode: int, pressed: bool) -> None:
        if not shutil.which("ydotool"):
            raise RuntimeError(
                "Backend ydotool dipilih, tetapi perintah ydotool tidak ditemukan. "
                "Instal ydotool sesuai docs/setup.md."
            )
        try:
            subprocess.run(
                ["ydotool", "key", f"{keycode}:{int(pressed)}"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            detail = error.stderr.strip() or error.stdout.strip()
            raise RuntimeError(
                "ydotool gagal mengirim input. Pastikan backend ydotool memiliki izin "
                f"untuk /dev/uinput atau socket daemon dapat diakses. Detail: {detail}"
            ) from error

    def wait_for_focus(self) -> None:
        time.sleep(self.startup_delay)

    def start_or_jump(self) -> None:
        if self.backend == "cdp":
            self._cdp_key(" ", "Space", 32, True)
            self._cdp_key(" ", "Space", 32, False)
        elif self.backend == "ydotool":
            self._ydotool_key(57, True)  # Linux input-event code for Space.
            self._ydotool_key(57, False)
        else:
            self.pyautogui.press("space")

    def duck(self) -> None:
        if self.backend == "cdp":
            self._cdp_key("ArrowDown", "ArrowDown", 40, True)
            time.sleep(self.duck_duration)
            self._cdp_key("ArrowDown", "ArrowDown", 40, False)
        elif self.backend == "ydotool":
            self._ydotool_key(108, True)  # Linux input-event code for ArrowDown.
            time.sleep(self.duck_duration)
            self._ydotool_key(108, False)
        else:
            self.pyautogui.keyDown("down")
            time.sleep(self.duck_duration)
            self.pyautogui.keyUp("down")
