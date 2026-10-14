import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dino_vision.capture import ScreenCapture
from dino_vision.config import load_settings
from dino_vision.control import GameControl
from dino_vision.detector import DinoDetector
from dino_vision.policy import ObstaclePolicy


def main() -> None:
    parser = argparse.ArgumentParser(description="Jalankan agen Chrome Dino berbasis YOLO.")
    parser.add_argument(
        "--save-interval",
        type=float,
        default=0,
        help="Simpan frame debug setiap N detik; 0 berarti tidak menyimpan frame.",
    )
    parser.add_argument(
        "--log-interval",
        type=float,
        default=0,
        help="Tampilkan status inferensi setiap N detik; 0 berarti tidak menampilkan log.",
    )
    parser.add_argument(
        "--start-game",
        action="store_true",
        help="Kirim Space sekali saat startup untuk memulai atau mengulang game.",
    )
    args = parser.parse_args()
    if args.save_interval < 0 or args.log_interval < 0:
        parser.error("--save-interval dan --log-interval tidak boleh negatif.")

    settings = load_settings()
    capture = ScreenCapture(settings["capture"])
    detector = DinoDetector(settings["detector"])
    policy = ObstaclePolicy(settings["policy"])
    try:
        control = GameControl(settings["control"])
    except RuntimeError as error:
        raise SystemExit(f"Kontrol gagal: {error}") from error
    cooldown = settings["policy"].get("action_cooldown_seconds", 0.20)

    print(f"Fokuskan Chrome Dino. Agen mulai dalam {control.startup_delay} detik.")
    print(f"Capture backend: {capture.backend}. Model: {settings['detector']['model_path']}")
    control.wait_for_focus()
    if args.start_game:
        try:
            control.start_or_jump()
        except RuntimeError as error:
            raise SystemExit(f"Kontrol gagal: {error}") from error
        print("Space startup terkirim.")
    last_action_at = 0.0
    last_frame_saved_at = 0.0
    last_log_at = 0.0
    previous_game_running = None

    try:
        while True:
            state_started_at = time.perf_counter()
            game_running = capture.backend != "cdp" or capture.cdp.is_game_running()
            state_ms = (time.perf_counter() - state_started_at) * 1000
            now = time.monotonic()
            if game_running != previous_game_running:
                if game_running:
                    print("Game aktif; capture dan inferensi YOLO dimulai.")
                else:
                    print("Game belum aktif atau sudah GAME OVER; menunggu game dimulai.")
                previous_game_running = game_running
            if not game_running:
                policy.reset()
                should_log = args.log_interval and now - last_log_at >= args.log_interval
                if should_log:
                    print("game_running=False; menunggu game dimulai, inferensi dan input dilewati")
                    last_log_at = now
                time.sleep(0.1)
                continue

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
            action_verified = None
            input_ms = 0.0
            verification_ms = 0.0
            if action and now - last_action_at >= cooldown:
                state = control.cdp.game_state() if control.backend == "cdp" else {}
                if state.get("jumping"):
                    sent_action = "covered-by-current-jump"
                    action_verified = True
                else:
                    input_started_at = time.perf_counter()
                    if action.name == "jump":
                        control.start_or_jump()
                    elif action.name == "duck":
                        control.duck()
                    input_ms = (time.perf_counter() - input_started_at) * 1000
                    last_action_at = now
                    sent_action = action.name
                    policy.mark_action_sent(action.track_id)
                if control.backend == "cdp" and sent_action == action.name:
                    verification_started_at = time.perf_counter()
                    state = control.cdp.game_state()
                    verification_ms = (time.perf_counter() - verification_started_at) * 1000
                    action_verified = (
                        state.get("jumping") if action.name == "jump" else state.get("ducking")
                    )

            save_ms = 0.0
            if args.save_interval and now - last_frame_saved_at >= args.save_interval:
                save_started_at = time.perf_counter()
                preview = frame.copy()
                draw = ImageDraw.Draw(preview)
                for detection in detections:
                    box = (detection.left, detection.top, detection.right, detection.bottom)
                    draw.rectangle(box, outline="red", width=3)
                    draw.text(
                        (detection.left, max(0, detection.top - 16)),
                        f"{detection.label} {detection.confidence:.0%}",
                        fill="red",
                    )
                proposed_text = action.name if action else "none"
                result_text = sent_action or "none"
                draw.text(
                    (10, 10),
                    f"proposed: {proposed_text}  result: {result_text}",
                    fill="lime",
                )
                ttc_text = (
                    f"{policy.effective_ttc_seconds:.2f}s"
                    if policy.effective_ttc_seconds is not None
                    else "unknown"
                )
                predicted_text = (
                    f"{policy.predicted_left:.0f}" if policy.predicted_left is not None else "unknown"
                )
                draw.text(
                    (10, 28),
                    f"speed: {policy.speed_px_s:.0f}px/s  predicted_x: {predicted_text} "
                    f"ttc: {ttc_text}/{policy.ttc_limit_seconds:.2f}s size: {policy.size_score:.2f} "
                    f"cluster: {policy.clustered} age: {decision_age_ms:.0f}ms",
                    fill="lime",
                )
                output = Path("assets/screenshots") / datetime.now().strftime(
                    "agent-%Y%m%d-%H%M%S-%f.png"
                )
                preview.save(output)
                save_ms = (time.perf_counter() - save_started_at) * 1000
                print(f"Frame debug tersimpan: {output}")
                last_frame_saved_at = now

            should_log = args.log_interval and now - last_log_at >= args.log_interval
            if should_log or sent_action:
                if detections:
                    detection_text = ", ".join(
                        f"{item.label} {item.confidence:.0%} x={item.left:.0f} y={item.center_y:.0f}"
                        for item in detections
                    )
                else:
                    detection_text = "none"
                proposed = action.name if action else "none"
                sent = sent_action or "none"
                verified = action_verified if action_verified is not None else "n/a"
                raw_ttc = (
                    f"{policy.raw_ttc_seconds:.2f}s"
                    if policy.raw_ttc_seconds is not None
                    else "unknown"
                )
                effective_ttc = (
                    f"{policy.effective_ttc_seconds:.2f}s"
                    if policy.effective_ttc_seconds is not None
                    else "unknown"
                )
                predicted_left = (
                    f"{policy.predicted_left:.0f}" if policy.predicted_left is not None else "unknown"
                )
                print(
                    f"game_running=True detections=[{detection_text}] proposed={proposed} sent={sent} "
                    f"speed={policy.speed_px_s:.0f}px/s x_predicted={predicted_left} "
                    f"ttc_raw={raw_ttc} ttc_effective={effective_ttc} "
                    f"ttc_limit={policy.ttc_limit_seconds:.2f}s size={policy.size_score:.2f} "
                    f"clustered={policy.clustered} cluster_bonus={policy.cluster_ttc_bonus:.2f}s "
                    f"latency_ms(state={state_ms:.0f} capture={capture_ms:.0f} "
                    f"inference={inference_ms:.0f} policy={policy_ms:.0f} "
                    f"decision_age={decision_age_ms:.0f} input={input_ms:.0f} "
                    f"verify={verification_ms:.0f} save={save_ms:.0f}) "
                    f"reason={policy.trigger_reason} "
                    f"track={policy.selected_track_id} active_tracks={len(policy.tracks)} "
                    f"tracks=[{policy.track_summary()}] action_verified={verified} armed={policy.armed}"
                )
                last_log_at = now
    except KeyboardInterrupt:
        print("Agen dihentikan.")
    except RuntimeError as error:
        raise SystemExit(f"Kontrol gagal: {error}") from error


if __name__ == "__main__":
    main()
