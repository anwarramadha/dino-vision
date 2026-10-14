import base64
import json
from io import BytesIO
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image


class ChromeDevTools:
    """Small Chrome DevTools Protocol client bound to the Dino tab."""

    def __init__(self, cdp_url: str = "http://127.0.0.1:9222") -> None:
        endpoint = cdp_url.rstrip("/") + "/json"
        try:
            with urlopen(endpoint, timeout=3) as response:
                pages = json.load(response)
        except (OSError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"Chrome DevTools tidak tersedia di {endpoint}. Jalankan Chrome dengan "
                "--remote-debugging-port=9222 dan lihat docs/setup.md."
            ) from error

        dino_tab = next(
            (
                page
                for page in pages
                if page.get("type") == "page" and page.get("url", "").startswith("chrome://dino")
            ),
            None,
        )
        if not dino_tab:
            raise RuntimeError("Tab chrome://dino tidak ditemukan pada Chrome DevTools.")

        try:
            import websocket

            self.socket = websocket.create_connection(dino_tab["webSocketDebuggerUrl"], timeout=3)
        except Exception as error:
            raise RuntimeError(
                "Tidak dapat membuka koneksi Chrome DevTools ke tab Dino. Jalankan Chrome "
                "dengan --remote-allow-origins=http://127.0.0.1:9222. "
                f"Detail: {error}"
            ) from error
        self.request_id = 0
        # Chrome Dino pauses on window blur. Keep the inspected tab focused while
        # the terminal is active so capture and keyboard control can run together.
        self.command("Emulation.setFocusEmulationEnabled", {"enabled": True})

    def command(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.request_id += 1
        request_id = self.request_id
        payload = {"id": request_id, "method": method}
        if params:
            payload["params"] = params
        self.socket.send(json.dumps(payload))
        while True:
            response = json.loads(self.socket.recv())
            if response.get("id") == request_id:
                if "error" in response:
                    raise RuntimeError(f"Chrome DevTools gagal menjalankan {method}: {response['error']}")
                return response.get("result", {})

    def bring_to_front(self) -> None:
        self.command("Page.bringToFront")

    def capture_screenshot(
        self,
        image_format: str = "png",
        jpeg_quality: int = 80,
        optimize_for_speed: bool = False,
    ) -> Image.Image:
        params: dict[str, Any] = {"format": image_format}
        if image_format == "jpeg":
            params["quality"] = jpeg_quality
            params["optimizeForSpeed"] = optimize_for_speed
        result = self.command("Page.captureScreenshot", params)
        png_data = base64.b64decode(result["data"])
        with Image.open(BytesIO(png_data)) as image:
            return image.convert("RGB")

    def is_game_running(self) -> bool:
        state = self.game_state()
        return bool(state.get("activated") and not state.get("crashed"))

    def game_state(self) -> dict[str, Any]:
        result = self.command(
            "Runtime.evaluate",
            {
                "expression": (
                    "(() => { const runner = Runner.getInstance(); return {"
                    "activated: runner.activated, crashed: runner.crashed, "
                    "playing: runner.playing, jumping: runner.tRex.jumping, "
                    "ducking: runner.tRex.ducking, "
                    "y: runner.tRex.yPos, distance: runner.distanceRan}; })()"
                ),
                "returnByValue": True,
            },
        )
        return result.get("result", {}).get("value", {})
