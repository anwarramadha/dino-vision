import os
from typing import Any

import mss
from PIL import Image

from dino_vision.cdp import ChromeDevTools


class ScreenCapture:
    def __init__(self, settings: dict[str, Any]) -> None:
        self.backend = self._select_backend(settings.get("backend", "auto"))
        self.monitor_number = settings.get("monitor", 1)
        self.region = settings.get("region")
        self.image_format = settings.get("image_format", "png")
        self.jpeg_quality = settings.get("jpeg_quality", 80)
        self.optimize_for_speed = settings.get("optimize_for_speed", False)
        if self.backend == "cdp":
            self.cdp = ChromeDevTools(settings.get("cdp_url", "http://127.0.0.1:9222"))

    @staticmethod
    def _select_backend(requested_backend: str) -> str:
        if requested_backend == "auto":
            return "cdp" if os.environ.get("WSL_INTEROP") else "mss"
        if requested_backend not in {"mss", "cdp"}:
            raise ValueError("capture.backend harus bernilai auto, mss, atau cdp.")
        return requested_backend

    def capture(self) -> Image.Image:
        if self.backend == "cdp":
            frame = self.cdp.capture_screenshot(
                self.image_format,
                self.jpeg_quality,
                self.optimize_for_speed,
            )
            if self.region:
                left = self.region["left"]
                top = self.region["top"]
                right = left + self.region["width"]
                bottom = top + self.region["height"]
                return frame.crop((left, top, right, bottom))
            return frame
        with mss.mss() as screen:
            monitor = self.region or screen.monitors[self.monitor_number]
            frame = screen.grab(monitor)
        return Image.frombytes("RGB", frame.size, frame.bgra, "raw", "BGRX")
