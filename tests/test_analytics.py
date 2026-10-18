import math

from analytics import impact_moment, pass_difficulty, pressure_from_distance, xg_model


def base_event(**kw):
    ev = {"event_type": "PASS", "outcome": "COMPLETE", "card": None,
          "metrics": {"xg": None, "pass_difficulty": 20, "pressure": "LOW", "pressure_index": 10,
                      "forward_gain_m": 3.0, "players_bypassed": 0}}
    ev.update(kw)
    return ev


def test_xg_falls_with_distance():
    near, _ = xg_model(90, 50)
    far, _ = xg_model(70, 50)
    assert near > far


def test_xg_rises_with_wider_angle():
    central, _ = xg_model(88, 50)
    tight, _ = xg_model(88, 80)
    assert central > tight


def test_xg_reference_points():
    penalty, d = xg_model(100 - 11 / 1.05, 50)
    assert abs(d - 11) < 0.2 and 0.20 <= penalty <= 0.26
    long_range, _ = xg_model(100 - 25 / 1.05, 50)
    assert 0.03 <= long_range <= 0.07


def test_pressure_lowers_xg():
    assert xg_model(88, 50, 80)[0] < xg_model(88, 50, 0)[0]


def test_pressure_thresholds():
    assert pressure_from_distance(0.5) == (94, "HIGH")
    assert pressure_from_distance(3.09)[1] == "HIGH"   # index 66
    assert pressure_from_distance(3.2)[1] == "MEDIUM"  # index 65
    assert pressure_from_distance(6.0)[1] == "MEDIUM"  # index 34
    assert pressure_from_distance(6.2)[1] == "LOW"     # index 32
    assert pressure_from_distance(20) == (0, "LOW")


def test_pass_difficulty_grows_with_length_pressure_and_direction():
    short = pass_difficulty(8, math.pi / 2, 10, 8)
    assert pass_difficulty(30, math.pi / 2, 10, 8) > short
    assert pass_difficulty(8, math.pi / 2, 90, 8) > short
    assert pass_difficulty(8, 0, 10, 8) > short          # straight forward is harder than square
    assert pass_difficulty(8, math.pi / 2, 10, 1) > short  # tightly marked receiver
    assert 5 <= pass_difficulty(0, math.pi, 0, 20) and pass_difficulty(200, 0, 100, 0) <= 99


def test_impact_true_for_every_shot():
    for outcome in ("GOAL", "SAVED", "MISS", "BLOCKED"):
        ev = base_event(event_type="SHOT", outcome=outcome,
                        metrics={"xg": 0.04, "pass_difficulty": None, "pressure": "LOW", "pressure_index": 0,
                                 "forward_gain_m": None, "players_bypassed": None})
        assert impact_moment(ev)[0]


def test_impact_false_for_short_unpressured_pass():
    assert impact_moment(base_event()) == (False, [])


def test_line_breaking_pass_is_impact():
    ev = base_event(metrics={"xg": None, "pass_difficulty": 72, "pressure": "MEDIUM", "pressure_index": 40,
                             "forward_gain_m": 28.0, "players_bypassed": 3})
    assert impact_moment(ev) == (True, ["line_breaking_pass"])


def test_high_press_turnover_is_impact():
    ev = base_event(event_type="TACKLE", outcome="WON",
                    metrics={"xg": None, "pass_difficulty": None, "pressure": "HIGH", "pressure_index": 80,
                             "forward_gain_m": None, "players_bypassed": None})
    assert "high_press_turnover" in impact_moment(ev)[1]
