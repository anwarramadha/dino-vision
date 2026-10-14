"""Agen Chrome Dino untuk Windows dengan screenshot melalui DXCam.

Skrip ini tidak memakai ``mss`` atau CDP untuk mengambil frame. Screenshot
diambil dari Desktop Duplication API (DirectX) Windows melalui ``dxcam``.
Konfigurasi ``capture.region`` pada ``config/settings.yaml`` tetap digunakan.
"""

import argparse
import ctypes
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import dxcam
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dino_vision.config import load_settings
from dino_vision.control import GameControl
from dino_vision.detector import DinoDetector
from dino_vision.policy import ObstaclePolicy


def enable_dpi_awareness() -> None:
    """Gunakan koordinat piksel fisik agar region cocok dengan layar Windows."""
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        # Tidak tersedia pada Windows lama; DXCam masih dapat digunakan.
        pass


class WindowsScreenCapture:
    """Capture desktop Windows melalui Desktop Duplication API DirectX."""

    backend = "windows-dxcam"

    def __init__(self, settings: dict[str, Any]) -> None:
        region = settings.get("region")
        self.bbox = self._region_to_bbox(region) if region else None
        monitor = settings.get("monitor", 1)
        try:
            output_idx = int(monitor) - 1
        except (TypeError, ValueError) as error:
            raise ValueError("capture.monitor harus berupa angka positif.") from error
        if output_idx < 0:
            raise ValueError("capture.monitor harus bernilai minimal 1.")
        self.camera = dxcam.create(
            output_idx=output_idx,
            output_color="RGB",
            backend="dxgi",
            processor_backend="numpy",
        )

    @staticmethod
    def _region_to_bbox(region: dict[str, Any]) -> tuple[int, int, int, int]:
        try:
            left = int(region["left"])
            top = int(region["top"])
            width = int(region["width"])
            height = int(region["height"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "capture.region harus berisi left, top, width, dan height berupa angka."
            ) from error
        if width <= 0 or height <= 0:
            raise ValueError("capture.region.width dan capture.region.height harus lebih dari 0.")
        return left, top, left + width, top + height

    def capture(self) -> Image.Image:
        frame = self.camera.grab(region=self.bbox, new_frame_only=False)
        if frame is None:
            raise RuntimeError("DXCam tidak mengembalikan frame dari monitor yang dipilih.")
        return Image.fromarray(frame, "RGB")

    def close(self) -> None:
        self.camera.release()


def draw_preview(
    frame: Image.Image,
    detections: list[Any],
    action: Any,
    sent_action: str | None,
    policy: ObstaclePolicy,
    decision_age_ms: float,
) -> Image.Image:
    preview = frame.copy()
    draw = ImageDraw.Draw(preview)
    for detection in detections:
        draw.rectangle(
            (detection.left, detection.top, detection.right, detection.bottom),
            outline="red",
            width=3,
        )
        draw.text(
            (detection.left, max(0, detection.top - 16)),
            f"{detection.label} {detection.confidence:.0%}",
            fill="red",
        )
    draw.text(
        (10, 10),
        f"proposed: {action.name if action else 'none'}  result: {sent_action or 'none'}",
        fill="lime",
    )
    ttc = f"{policy.effective_ttc_seconds:.2f}s" if policy.effective_ttc_seconds is not None else "unknown"
    predicted = f"{policy.predicted_left:.0f}" if policy.predicted_left is not None else "unknown"
    draw.text(
        (10, 28),
        f"speed: {policy.speed_px_s:.0f}px/s  predicted_x: {predicted} "
        f"ttc: {ttc}/{policy.ttc_limit_seconds:.2f}s size: {policy.size_score:.2f} "
        f"cluster: {policy.clustered} age: {decision_age_ms:.0f}ms",
        fill="lime",
    )
    return preview


def run_benchmark(capture: WindowsScreenCapture, detector: DinoDetector, frames: int) -> None:
    """Ukur capture dan inferensi tanpa mengirim input ke game."""
    warmup_frames = min(10, frames)
    print(f"Pemanasan {warmup_frames} frame, lalu benchmark {frames} frame tanpa input keyboard.")
    for _ in range(warmup_frames):
        detector.detect(capture.capture())

    capture_samples: list[float] = []
    inference_samples: list[float] = []
    for _ in range(frames):
        capture_started_at = time.perf_counter()
        frame = capture.capture()
        capture_samples.append((time.perf_counter() - capture_started_at) * 1000)

        inference_started_at = time.perf_counter()
        detector.detect(frame)
        inference_samples.append((time.perf_counter() - inference_started_at) * 1000)

    def p95(values: list[float]) -> float:
        return sorted(values)[max(0, round(len(values) * 0.95) - 1)]

    print(
        "Benchmark DXCam "
        f"({frames} frame): capture rata-rata={statistics.mean(capture_samples):.1f}ms "
        f"p95={p95(capture_samples):.1f}ms; "
        f"inference rata-rata={statistics.mean(inference_samples):.1f}ms "
        f"p95={p95(inference_samples):.1f}ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Jalankan agen Chrome Dino Windows dengan screenshot desktop DXCam."
    )
    parser.add_argument("--save-interval", type=float, default=0)
    parser.add_argument("--log-interval", type=float, default=0)
    parser.add_argument("--start-game", action="store_true")
    parser.add_argument(
        "--model-path",
        help="Path model Ultralytics; gunakan direktori *_openvino_model untuk OpenVINO.",
    )
    parser.add_argument(
        "--benchmark-frames",
        type=int,
        default=0,
        help="Ukur capture dan inferensi selama N frame tanpa mengirim input keyboard.",
    )
    parser.add_argument(
        "--decision-mode",
        choices=("predictive", "direct-distance"),
        default="predictive",
        help="Pilih policy predictive atau direct-distance; default predictive.",
    )
    parser.add_argument(
        "--direct-distance-ratio",
        type=float,
        help="Ambang jarak minimum sebagai rasio lebar ROI; default 0.08.",
    )
    parser.add_argument(
        "--direct-cluster-distance-ratio",
        type=float,
        help="Tambahan ambang maksimum untuk rintangan berkelompok; default 0.08.",
    )
    parser.add_argument(
        "--direct-speed-seconds",
        type=float,
        help="Waktu lead lompatan untuk kompensasi kecepatan; default 0.20 detik.",
    )
    args = parser.parse_args()
    if args.save_interval < 0 or args.log_interval < 0:
        parser.error("--save-interval dan --log-interval tidak boleh negatif.")
    if args.benchmark_frames < 0:
        parser.error("--benchmark-frames tidak boleh negatif.")
    if args.direct_distance_ratio is not None and not 0 < args.direct_distance_ratio <= 1:
        parser.error("--direct-distance-ratio harus lebih dari 0 dan paling besar 1.")
    if args.direct_cluster_distance_ratio is not None and not 0 <= args.direct_cluster_distance_ratio <= 1:
        parser.error("--direct-cluster-distance-ratio harus berada di antara 0 dan 1.")
    if args.direct_speed_seconds is not None and args.direct_speed_seconds < 0:
        parser.error("--direct-speed-seconds tidak boleh negatif.")

    enable_dpi_awareness()
    settings = load_settings()
    if args.model_path:
        settings["detector"]["model_path"] = args.model_path
    settings["policy"]["decision_mode"] = args.decision_mode.replace("-", "_")
    if args.direct_distance_ratio is not None:
        settings["policy"]["direct_distance_ratio"] = args.direct_distance_ratio
    if args.direct_cluster_distance_ratio is not None:
        settings["policy"]["direct_cluster_distance_ratio"] = args.direct_cluster_distance_ratio
    if args.direct_speed_seconds is not None:
        settings["policy"]["direct_speed_seconds"] = args.direct_speed_seconds
    capture = WindowsScreenCapture(settings["capture"])
    detector = DinoDetector(settings["detector"])
    policy = ObstaclePolicy(settings["policy"])
    if args.benchmark_frames:
        try:
            run_benchmark(capture, detector, args.benchmark_frames)
        finally:
            capture.close()
        return
    try:
        control = GameControl(settings["control"])
    except RuntimeError as error:
        raise SystemExit(f"Kontrol gagal: {error}") from error

    cooldown = settings["policy"].get("action_cooldown_seconds", 0.20)
    print(f"Fokuskan Chrome Dino. Agen mulai dalam {control.startup_delay} detik.")
    print(f"Capture backend: {capture.backend}. Model: {settings['detector']['model_path']}")
    control.wait_for_focus()
    if args.start_game:
        control.start_or_jump()
        print("Space startup terkirim.")

    last_action_at = 0.0
    last_frame_saved_at = 0.0
    last_log_at = 0.0
    try:
        while True:
            capture_started_at = time.perf_counter()
            frame = capture.capture()
            frame_time = time.monotonic()
            capture_ms = (time.perf_counter() - capture_started_at) * 1000

            inference_started_at = time.perf_counter()
            detections = detector.detect(frame)
            now = time.monotonic()
            inference_ms = (time.perf_counter() - inference_started_at) * 1000

            policy_started_at = time.perf_counter()
            action = policy.choose(detections, frame.width, frame.height, frame_time, now)
            policy_ms = (time.perf_counter() - policy_started_at) * 1000
            decision_age_ms = (now - frame_time) * 1000

            sent_action = None
            input_ms = 0.0
            if action and now - last_action_at >= cooldown:
                input_started_at = time.perf_counter()
                if action.name == "jump":
                    control.start_or_jump()
                elif action.name == "duck":
                    control.duck()
                input_ms = (time.perf_counter() - input_started_at) * 1000
                last_action_at = now
                sent_action = action.name
                policy.mark_action_sent(action.track_id)

            save_ms = 0.0
            if args.save_interval and now - last_frame_saved_at >= args.save_interval:
                save_started_at = time.perf_counter()
                output = ROOT / "assets" / "screenshots" / datetime.now().strftime(
                    "agent-windows-%Y%m%d-%H%M%S-%f.png"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                draw_preview(frame, detections, action, sent_action, policy, decision_age_ms).save(output)
                save_ms = (time.perf_counter() - save_started_at) * 1000
                print(f"Frame debug tersimpan: {output}")
                last_frame_saved_at = now

            if (args.log_interval and now - last_log_at >= args.log_interval) or sent_action:
                detection_text = ", ".join(
                    f"{item.label} {item.confidence:.0%} x={item.left:.0f} y={item.center_y:.0f}"
                    for item in detections
                ) or "none"
                raw_ttc = f"{policy.raw_ttc_seconds:.2f}s" if policy.raw_ttc_seconds is not None else "unknown"
                effective_ttc = (
                    f"{policy.effective_ttc_seconds:.2f}s"
                    if policy.effective_ttc_seconds is not None
                    else "unknown"
                )
                predicted_left = (
                    f"{policy.predicted_left:.0f}" if policy.predicted_left is not None else "unknown"
                )
                print(
                    f"detections=[{detection_text}] proposed={action.name if action else 'none'} "
                    f"sent={sent_action or 'none'} speed={policy.speed_px_s:.0f}px/s "
                    f"x_predicted={predicted_left} ttc_raw={raw_ttc} "
                    f"ttc_effective={effective_ttc} ttc_limit={policy.ttc_limit_seconds:.2f}s "
                    f"size={policy.size_score:.2f} clustered={policy.clustered} "
                    f"latency_ms(capture={capture_ms:.0f} inference={inference_ms:.0f} "
                    f"policy={policy_ms:.0f} decision_age={decision_age_ms:.0f} "
                    f"input={input_ms:.0f} save={save_ms:.0f}) reason={policy.trigger_reason} "
                    f"track={policy.selected_track_id} active_tracks={len(policy.tracks)} "
                    f"tracks=[{policy.track_summary()}] armed={policy.armed}"
                )
                last_log_at = now
    except KeyboardInterrupt:
        print("Agen dihentikan.")
    except RuntimeError as error:
        raise SystemExit(f"Kontrol gagal: {error}") from error
    finally:
        capture.close()


if __name__ == "__main__":
    main()
