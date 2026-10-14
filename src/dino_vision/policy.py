from collections import deque
from dataclasses import dataclass, field

from dino_vision.types import Detection


@dataclass(frozen=True)
class Action:
    name: str
    track_id: int


@dataclass
class ObstacleTrack:
    track_id: int
    label: str
    history_size: int
    history: deque[tuple[float, float]] = field(init=False)
    detection: Detection | None = None
    speed_px_s: float = 0.0
    missed_frames: int = 0
    handled: bool = False

    def __post_init__(self) -> None:
        self.history = deque(maxlen=self.history_size)

    @property
    def left(self) -> float:
        assert self.detection is not None
        return self.detection.left

    def update(self, detection: Detection, observed_at: float) -> None:
        self.detection = detection
        self.history.append((observed_at, detection.left))
        self.missed_frames = 0
        if len(self.history) >= 2:
            first_time, first_left = self.history[0]
            last_time, last_left = self.history[-1]
            elapsed = last_time - first_time
            movement = first_left - last_left
            if elapsed > 0 and movement > 0:
                self.speed_px_s = movement / elapsed


class ObstaclePolicy:
    def __init__(self, settings: dict[str, float]) -> None:
        self.decision_mode = settings.get("decision_mode", "predictive")
        if self.decision_mode not in {"predictive", "direct_distance"}:
            raise ValueError("policy.decision_mode harus predictive atau direct_distance.")
        self.direct_distance_ratio = settings.get("direct_distance_ratio", 0.08)
        if not 0 < self.direct_distance_ratio <= 1:
            raise ValueError("policy.direct_distance_ratio harus lebih dari 0 dan paling besar 1.")
        self.direct_cluster_distance_ratio = settings.get("direct_cluster_distance_ratio", 0.08)
        if not 0 <= self.direct_cluster_distance_ratio <= 1:
            raise ValueError(
                "policy.direct_cluster_distance_ratio harus berada di antara 0 dan 1."
            )
        self.direct_speed_seconds = settings.get("direct_speed_seconds", 0.20)
        if self.direct_speed_seconds < 0:
            raise ValueError("policy.direct_speed_seconds tidak boleh negatif.")
        self.jump_ttc_seconds = settings.get("jump_ttc_seconds", 0.35)
        self.duck_ttc_seconds = settings.get("duck_ttc_seconds", 0.28)
        self.emergency_distance_ratio = settings.get("emergency_distance_ratio", 0.06)
        self.high_bird_ratio = settings.get("high_bird_ratio", 0.30)
        self.low_bird_ratio = settings.get("low_bird_ratio", 0.45)
        if not 0 <= self.high_bird_ratio < self.low_bird_ratio <= 1:
            raise ValueError(
                "policy.high_bird_ratio harus lebih kecil dari policy.low_bird_ratio, "
                "dan keduanya berada di antara 0 dan 1."
            )
        self.cactus_size_ttc_reduction = settings.get("cactus_size_ttc_reduction", 0.30)
        self.cactus_reference_height_ratio = settings.get("cactus_reference_height_ratio", 0.20)
        self.cactus_reference_width_ratio = settings.get("cactus_reference_width_ratio", 0.12)
        self.obstacle_cluster_gap_ratio = settings.get("obstacle_cluster_gap_ratio", 0.25)
        self.cluster_ttc_bonus_seconds = settings.get("cluster_ttc_bonus_seconds", 0.12)
        self.input_latency_seconds = settings.get("input_latency_seconds", 0.03)
        self.history_size = settings.get("history_size", 4)
        self.max_missed_frames = settings.get("track_max_missed_frames", 3)
        self.min_match_distance_px = settings.get("track_min_match_distance_px", 90)
        self.tracks: dict[int, ObstacleTrack] = {}
        self.next_track_id = 1
        self.speed_px_s = 0.0
        self.raw_ttc_seconds: float | None = None
        self.effective_ttc_seconds: float | None = None
        self.predicted_left: float | None = None
        self.size_score = 0.0
        self.ttc_limit_seconds = self.jump_ttc_seconds
        self.clustered = False
        self.cluster_ttc_bonus = 0.0
        self.trigger_reason = "none"
        self.selected_track_id: int | None = None

    @property
    def armed(self) -> bool:
        return any(not track.handled for track in self.tracks.values())

    def choose(
        self,
        detections: list[Detection],
        frame_width: int,
        frame_height: int,
        observed_at: float,
        decision_at: float,
    ) -> Action | None:
        self._clear_diagnostics()
        obstacles = [
            item
            for item in detections
            if item.label in {"cactus", "bird"} and not self._is_high_bird(item, frame_height)
        ]
        if self.decision_mode == "direct_distance":
            self._update_tracks(obstacles, observed_at)
            unhandled = [track for track in self.tracks.values() if not track.handled]
            return self._choose_by_distance(
                unhandled, frame_width, frame_height, observed_at, decision_at
            )
        self._update_tracks(obstacles, observed_at)
        unhandled = [track for track in self.tracks.values() if not track.handled]
        if not unhandled:
            return None

        scored = [
            (self._predict(track, frame_width, frame_height, observed_at, decision_at), track)
            for track in unhandled
        ]
        self._apply_cluster_bonus(scored, frame_width)
        actionable = [item for item in scored if self._should_act(item[0], frame_width)]
        metrics, track = min(actionable or scored, key=self._urgency)
        self._set_diagnostics(track, metrics)

        if not actionable:
            return None

        emergency_distance = frame_width * self.emergency_distance_ratio
        self.trigger_reason = (
            "predicted-emergency"
            if metrics["predicted_left"] <= emergency_distance
            else "latency-compensated-ttc"
        )
        return Action("duck" if metrics["is_duck_bird"] else "jump", track.track_id)

    def _choose_by_distance(
        self,
        tracks: list[ObstacleTrack],
        frame_width: int,
        frame_height: int,
        observed_at: float,
        decision_at: float,
    ) -> Action | None:
        """Pilih aksi dari jarak saat ini dengan ambang yang mengikuti kecepatan."""
        if not tracks:
            return None
        track, threshold, clustered = self._select_direct_obstacle(
            tracks, frame_width, observed_at, decision_at
        )
        assert track.detection is not None
        obstacle = track.detection
        self.predicted_left = obstacle.left
        self.ttc_limit_seconds = threshold
        self.clustered = clustered
        self.selected_track_id = track.track_id
        self.speed_px_s = track.speed_px_s
        self.raw_ttc_seconds = obstacle.left / track.speed_px_s if track.speed_px_s > 0 else None
        self.trigger_reason = "direct-distance"
        is_duck_bird = (
            obstacle.label == "bird"
            and frame_height * self.high_bird_ratio
            <= obstacle.center_y
            < frame_height * self.low_bird_ratio
        )
        if obstacle.left > threshold:
            return None
        return Action("duck" if is_duck_bird else "jump", track.track_id)

    def _select_direct_obstacle(
        self,
        tracks: list[ObstacleTrack],
        frame_width: int,
        observed_at: float,
        decision_at: float,
    ) -> tuple[ObstacleTrack, float, bool]:
        """Pilih rintangan memakai jarak dasar, kecepatan, dan kepadatan cluster."""
        base_threshold = frame_width * self.direct_distance_ratio
        cluster_gap = frame_width * self.obstacle_cluster_gap_ratio
        max_bonus = frame_width * self.direct_cluster_distance_ratio
        decision_delay = max(0.0, decision_at - observed_at) + self.input_latency_seconds
        scored: list[tuple[ObstacleTrack, float, bool]] = []
        for track in sorted(tracks, key=lambda item: item.left):
            speed_bonus = track.speed_px_s * (self.direct_speed_seconds + decision_delay)
            follower_gaps = [
                other.left - track.left
                for other in tracks
                if 0 < other.left - track.left <= cluster_gap
            ]
            if follower_gaps:
                closest_gap = min(follower_gaps)
                proximity = 1 - closest_gap / cluster_gap
                threshold = base_threshold + speed_bonus + max_bonus * proximity
                scored.append((track, threshold, True))
            else:
                scored.append((track, base_threshold + speed_bonus, False))

        actionable = [item for item in scored if item[0].left <= item[1]]
        return min(actionable or scored, key=lambda item: item[0].left)

    def _is_high_bird(self, detection: Detection, frame_height: int) -> bool:
        """Burung tinggi dapat dilewati Dino, sehingga tidak memerlukan aksi."""
        return (
            detection.label == "bird"
            and detection.center_y < frame_height * self.high_bird_ratio
        )

    def mark_action_sent(self, track_id: int) -> None:
        if track_id in self.tracks:
            self.tracks[track_id].handled = True

    def reset(self) -> None:
        self.tracks.clear()
        self.next_track_id = 1
        self._clear_diagnostics()

    def track_summary(self) -> str:
        if not self.tracks:
            return "none"
        return ", ".join(
            f"#{track.track_id}:{track.label}@x={track.left:.0f}:{'handled' if track.handled else 'ready'}"
            for track in sorted(self.tracks.values(), key=lambda item: item.left)
        )

    def _update_tracks(self, detections: list[Detection], observed_at: float) -> None:
        matched_track_ids: set[int] = set()
        for detection in sorted(detections, key=lambda item: item.left):
            track = self._match_track(detection, observed_at, matched_track_ids)
            if track is None:
                track = ObstacleTrack(self.next_track_id, detection.label, self.history_size)
                self.tracks[track.track_id] = track
                self.next_track_id += 1
            track.update(detection, observed_at)
            matched_track_ids.add(track.track_id)

        for track_id, track in list(self.tracks.items()):
            if track_id not in matched_track_ids:
                track.missed_frames += 1
                if track.missed_frames > self.max_missed_frames:
                    del self.tracks[track_id]

    def _match_track(
        self,
        detection: Detection,
        observed_at: float,
        matched_track_ids: set[int],
    ) -> ObstacleTrack | None:
        candidates: list[tuple[float, ObstacleTrack]] = []
        for track in self.tracks.values():
            if track.track_id in matched_track_ids or track.label != detection.label:
                continue
            last_time, last_left = track.history[-1]
            # Obstacles only travel from right to left. A rightward jump is a new object.
            if detection.left > last_left + self.min_match_distance_px:
                continue
            elapsed = observed_at - last_time
            expected_left = last_left - track.speed_px_s * max(0.0, elapsed)
            distance = abs(detection.left - expected_left)
            max_distance = max(
                self.min_match_distance_px,
                track.speed_px_s * max(0.0, elapsed) * 1.7 + self.min_match_distance_px,
                600 if track.speed_px_s == 0 else 0,
            )
            if distance <= max_distance:
                candidates.append((distance, track))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

    def _predict(
        self,
        track: ObstacleTrack,
        frame_width: int,
        frame_height: int,
        observed_at: float,
        decision_at: float,
    ) -> dict[str, float | bool | None]:
        assert track.detection is not None
        observation_age = decision_at - observed_at + self.input_latency_seconds
        raw_ttc = track.left / track.speed_px_s if track.speed_px_s > 0 else None
        effective_ttc = raw_ttc - observation_age if raw_ttc is not None else None
        predicted_left = max(0.0, track.left - track.speed_px_s * observation_age)
        is_duck_bird = (
            track.label == "bird"
            and frame_height * self.high_bird_ratio
            <= track.detection.center_y
            < frame_height * self.low_bird_ratio
        )
        size_score = 0.0
        ttc_limit = self.duck_ttc_seconds if is_duck_bird else self.jump_ttc_seconds
        if track.label == "cactus":
            height_score = track.detection.height / (frame_height * self.cactus_reference_height_ratio)
            width_score = track.detection.width / (frame_width * self.cactus_reference_width_ratio)
            size_score = min(1.0, max(height_score, width_score))
            ttc_limit *= 1 - self.cactus_size_ttc_reduction * size_score
        return {
            "raw_ttc": raw_ttc,
            "effective_ttc": effective_ttc,
            "predicted_left": predicted_left,
            "is_duck_bird": is_duck_bird,
            "size_score": size_score,
            "ttc_limit": ttc_limit,
            "clustered": False,
            "cluster_bonus": 0.0,
        }

    def _apply_cluster_bonus(
        self,
        scored: list[tuple[dict[str, float | bool | None], ObstacleTrack]],
        frame_width: int,
    ) -> None:
        max_gap = frame_width * self.obstacle_cluster_gap_ratio
        for metrics, track in scored:
            has_near_follower = any(
                0 < other.left - track.left <= max_gap
                for _, other in scored
                if other.track_id != track.track_id
            )
            if has_near_follower:
                metrics["clustered"] = True
                metrics["cluster_bonus"] = self.cluster_ttc_bonus_seconds
                metrics["ttc_limit"] += self.cluster_ttc_bonus_seconds

    def _should_act(self, metrics: dict[str, float | bool | None], frame_width: int) -> bool:
        emergency_distance = frame_width * self.emergency_distance_ratio
        return bool(
            metrics["predicted_left"] <= emergency_distance
            or metrics["effective_ttc"] is not None
            and metrics["effective_ttc"] <= metrics["ttc_limit"]
        )

    @staticmethod
    def _urgency(item: tuple[dict[str, float | bool | None], ObstacleTrack]) -> tuple[float, float]:
        metrics, _ = item
        effective_ttc = metrics["effective_ttc"]
        ttc_limit = metrics["ttc_limit"]
        slack = effective_ttc - ttc_limit if effective_ttc is not None else float("inf")
        return slack, metrics["predicted_left"]

    def _set_diagnostics(
        self,
        track: ObstacleTrack,
        metrics: dict[str, float | bool | None],
    ) -> None:
        self.selected_track_id = track.track_id
        self.speed_px_s = track.speed_px_s
        self.raw_ttc_seconds = metrics["raw_ttc"]  # type: ignore[assignment]
        self.effective_ttc_seconds = metrics["effective_ttc"]  # type: ignore[assignment]
        self.predicted_left = metrics["predicted_left"]  # type: ignore[assignment]
        self.size_score = metrics["size_score"]  # type: ignore[assignment]
        self.ttc_limit_seconds = metrics["ttc_limit"]  # type: ignore[assignment]
        self.clustered = metrics["clustered"]  # type: ignore[assignment]
        self.cluster_ttc_bonus = metrics["cluster_bonus"]  # type: ignore[assignment]

    def _clear_diagnostics(self) -> None:
        self.speed_px_s = 0.0
        self.raw_ttc_seconds = None
        self.effective_ttc_seconds = None
        self.predicted_left = None
        self.size_score = 0.0
        self.ttc_limit_seconds = self.jump_ttc_seconds
        self.clustered = False
        self.cluster_ttc_bonus = 0.0
        self.trigger_reason = "none"
        self.selected_track_id = None
