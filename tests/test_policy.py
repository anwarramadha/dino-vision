from dino_vision.policy import ObstaclePolicy
from dino_vision.types import Detection


SETTINGS = {
    "jump_ttc_seconds": 0.35,
    "duck_ttc_seconds": 0.28,
    "emergency_distance_ratio": 0.06,
    "high_bird_ratio": 0.30,
    "low_bird_ratio": 0.45,
    "cactus_size_ttc_reduction": 0.30,
    "cactus_reference_height_ratio": 0.20,
    "cactus_reference_width_ratio": 0.12,
    "obstacle_cluster_gap_ratio": 0.25,
    "cluster_ttc_bonus_seconds": 0.12,
    "input_latency_seconds": 0.03,
    "history_size": 4,
    "track_max_missed_frames": 3,
    "track_min_match_distance_px": 90,
}


def cactus(left: float) -> Detection:
    return Detection("cactus", 0.9, left, 100, left + 50, 200)


def choose(policy: ObstaclePolicy, items: list[Detection], observed: float, decision: float):
    return policy.choose(items, 1140, 520, observed, decision)


def test_fast_obstacle_uses_latency_compensated_ttc() -> None:
    policy = ObstaclePolicy(SETTINGS)
    assert choose(policy, [cactus(750)], 0.0, 0.0) is None
    action = choose(policy, [cactus(510)], 0.2, 0.5)
    assert action and action.name == "jump"
    assert policy.trigger_reason == "latency-compensated-ttc"


def test_tracks_two_obstacles_independently() -> None:
    policy = ObstaclePolicy(SETTINGS)
    assert choose(policy, [cactus(700), cactus(1050)], 0.0, 0.0) is None
    first_action = choose(policy, [cactus(300), cactus(650)], 0.3, 0.35)
    assert first_action and first_action.name == "jump"
    first_id = first_action.track_id
    policy.mark_action_sent(first_id)

    second_action = choose(policy, [cactus(70), cactus(350)], 0.5, 0.55)
    assert second_action and second_action.name == "jump"
    assert second_action.track_id != first_id


def test_handled_track_does_not_trigger_again() -> None:
    policy = ObstaclePolicy(SETTINGS)
    choose(policy, [cactus(500)], 0.0, 0.0)
    action = choose(policy, [cactus(100)], 0.3, 0.35)
    assert action
    policy.mark_action_sent(action.track_id)
    assert choose(policy, [cactus(40)], 0.5, 0.55) is None


def test_middle_bird_ducks() -> None:
    policy = ObstaclePolicy(SETTINGS)
    bird = Detection("bird", 0.9, 500, 150, 550, 250)
    assert choose(policy, [bird], 0.0, 0.0) is None
    action = choose(policy, [Detection("bird", 0.9, 250, 150, 300, 250)], 0.2, 0.25)
    assert action and action.name == "duck"


def test_low_bird_jumps() -> None:
    policy = ObstaclePolicy(SETTINGS)
    bird = Detection("bird", 0.9, 500, 250, 550, 350)
    assert choose(policy, [bird], 0.0, 0.0) is None
    action = choose(policy, [Detection("bird", 0.9, 250, 250, 300, 350)], 0.2, 0.25)
    assert action and action.name == "jump"


def test_high_bird_is_ignored() -> None:
    policy = ObstaclePolicy(SETTINGS)
    high_bird = Detection("bird", 0.9, 100, 20, 150, 100)
    assert choose(policy, [high_bird], 0.0, 0.0) is None
    assert choose(policy, [high_bird], 0.2, 0.2) is None
    assert not policy.tracks


def test_direct_distance_uses_current_distance_and_handles_a_track_once() -> None:
    settings = SETTINGS | {"decision_mode": "direct_distance", "direct_distance_ratio": 0.30}
    policy = ObstaclePolicy(settings)
    assert choose(policy, [cactus(343)], 0.0, 0.0) is None
    action = choose(policy, [cactus(342)], 0.1, 0.1)
    assert action and action.name == "jump"
    assert action.track_id == 1
    assert len(policy.tracks) == 1
    assert policy.trigger_reason == "direct-distance"
    policy.mark_action_sent(action.track_id)
    assert choose(policy, [cactus(250)], 0.2, 0.2) is None
    policy.reset()
    assert choose(policy, [cactus(342)], 0.3, 0.3)


def test_direct_distance_increases_threshold_for_a_close_follower() -> None:
    settings = SETTINGS | {
        "decision_mode": "direct_distance",
        "direct_distance_ratio": 0.15,
        "direct_cluster_distance_ratio": 0.08,
    }
    policy = ObstaclePolicy(settings)
    assert choose(policy, [cactus(200)], 0.0, 0.0) is None
    action = choose(policy, [cactus(200), cactus(220)], 0.1, 0.1)
    assert action and action.name == "jump"
    assert policy.clustered is True
    assert policy.ttc_limit_seconds > 1140 * 0.15


def test_direct_distance_increases_threshold_for_a_faster_obstacle() -> None:
    settings = SETTINGS | {
        "decision_mode": "direct_distance",
        "direct_distance_ratio": 0.10,
        "direct_speed_seconds": 0.20,
    }
    policy = ObstaclePolicy(settings)
    assert choose(policy, [cactus(500)], 0.0, 0.0) is None
    action = choose(policy, [cactus(330)], 0.17, 0.17)
    assert action and action.name == "jump"
    assert abs(policy.speed_px_s - 1000) < 0.01
    assert policy.ttc_limit_seconds > 1140 * 0.10


def test_track_is_removed_after_consecutive_missed_frames() -> None:
    policy = ObstaclePolicy(SETTINGS)
    choose(policy, [cactus(500)], 0.0, 0.0)
    for index in range(policy.max_missed_frames + 1):
        choose(policy, [], 0.1 + index * 0.1, 0.1 + index * 0.1)
    assert not policy.tracks


def test_large_cactus_waits_closer_than_small_cactus() -> None:
    small_policy = ObstaclePolicy(SETTINGS)
    small_start = Detection("cactus", 0.9, 610, 100, 660, 150)
    small_now = Detection("cactus", 0.9, 310, 100, 360, 150)
    assert choose(small_policy, [small_start], 0.0, 0.0) is None
    small_action = choose(small_policy, [small_now], 0.3, 0.3)
    assert small_action and small_action.name == "jump"

    large_policy = ObstaclePolicy(SETTINGS)
    large_start = Detection("cactus", 0.9, 610, 50, 660, 200)
    large_now = Detection("cactus", 0.9, 310, 50, 360, 200)
    assert choose(large_policy, [large_start], 0.0, 0.0) is None
    assert choose(large_policy, [large_now], 0.3, 0.3) is None
    assert large_policy.ttc_limit_seconds < small_policy.ttc_limit_seconds


def test_selects_actionable_track_when_nearest_track_is_not_actionable() -> None:
    policy = ObstaclePolicy(SETTINGS)
    assert choose(policy, [cactus(300), cactus(700)], 0.0, 0.0) is None
    action = choose(policy, [cactus(270), cactus(300)], 0.3, 0.3)
    assert action and action.track_id == 2


def test_clustered_cacti_trigger_earlier() -> None:
    policy = ObstaclePolicy(SETTINGS)
    assert choose(policy, [cactus(900), cactus(1150)], 0.0, 0.0) is None
    action = choose(policy, [cactus(580), cactus(830)], 0.2, 0.2)
    assert action and action.track_id == 1
    assert policy.clustered is True
    assert policy.cluster_ttc_bonus == 0.12
