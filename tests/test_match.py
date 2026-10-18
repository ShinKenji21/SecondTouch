import json

import pytest

from analytics import MatchStats
from generator import AWAY, FORMATIONS, HOME, SQUADS, MatchSim
from models import Event, PersonaCommentary
from persona_router import Context, render


def play(seed):
    sim = MatchSim(seed=seed)
    stats = MatchStats(SQUADS, FORMATIONS, HOME, AWAY)
    events = []
    while (ev := sim.next_event()) is not None:
        stats.update(ev, sim.positions, sim.possession)
        events.append((ev, {t: dict(p) for t, p in sim.positions.items()}))
    return sim, stats, events


@pytest.mark.parametrize("seed", range(8))
def test_full_match_is_consistent(seed):
    sim, stats, events = play(seed)
    evs = [e for e, _ in events]
    assert evs[-1]["event_type"] == "FULL_TIME"
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    assert sum(e["event_type"] == "HALF_TIME" for e in evs) == 1
    for ev, positions in events:
        Event.model_validate(ev)
        for team in (HOME, AWAY):
            assert 9 <= len(positions[team]) <= 11
            assert all(0 <= x <= 100 and 0 <= y <= 100 for x, y in positions[team].values())


@pytest.mark.parametrize("seed", range(8))
def test_each_goal_increments_score_exactly_once(seed):
    _, stats, events = play(seed)
    home = away = 0
    for ev, _ in events:
        if ev["event_type"] == "SHOT" and ev["outcome"] == "GOAL":
            home += ev["team"] == HOME
            away += ev["team"] == AWAY
        assert ev["score"] == {"home": home, "away": away}
    teams = stats.snapshot()["teams"]
    goals = {t: sum(p["goals"] for p in stats.player_rows(t)) for t in (HOME, AWAY)}
    assert goals == {HOME: home, AWAY: away}
    assert teams[HOME]["possession"] + teams[AWAY]["possession"] == 100


def test_receiver_is_where_the_ball_ends():
    _, _, events = play(3)
    for ev, positions in events:
        if ev["event_type"] == "PASS" and ev["outcome"] == "COMPLETE":
            x, y = positions[ev["team"]][ev["receiver"]]
            assert (x, y) == (ev["location"]["end_x"], ev["location"]["end_y"])


def test_substitutes_get_minutes_and_starters_who_left_stop():
    _, stats, events = play(5)
    subs = [e for e, _ in events if e["event_type"] == "SUBSTITUTION"]
    assert subs
    for ev in subs:
        rows = {r["id"]: r for r in stats.player_rows(ev["team"])}
        on, off = rows[ev["player"]], rows[ev["player_off"]]
        assert on["sub_on"] == int(ev["minute"]) and abs(on["minutes"] - (90 - ev["minute"])) <= 1
        assert off["sub_off"] == int(ev["minute"])


@pytest.mark.parametrize("lang", ["en", "es", "ja"])
def test_every_event_renders_three_personas(lang):
    sim = MatchSim(seed=11)
    stats = MatchStats(SQUADS, FORMATIONS, HOME, AWAY)
    while (ev := sim.next_event()) is not None:
        stats.update(ev, sim.positions, sim.possession)
        teams = {t: stats.team_stats(t) for t in (HOME, AWAY)}
        ctx = Context(HOME, AWAY, stats.summary(), sim.positions, HOME, "Saka",
                      stats.player_line(HOME, "Saka"), {t: (teams[t]["xg"], teams[t]["shots"]) for t in teams})
        out = render(ev, ctx, lang)
        assert set(out) == {"analyst", "casual", "player_cam"}
        assert all(isinstance(v, str) and v for v in out.values())
        if ev["is_impact_moment"] and ev["event_type"] == "SHOT":
            assert f"{ev['metrics']['xg']:.2f}" in out["analyst"]  # cites a computed metric


def test_model_output_validation_rejects_malformed_json():
    good = {"analyst": "Saka shoots, 0.21 xG.", "casual": "What a hit!", "player_cam": "On the ball: Saka shoots."}
    assert PersonaCommentary.model_validate_json(json.dumps(good)).casual == "What a hit!"
    with pytest.raises(Exception):
        PersonaCommentary.model_validate_json('{"analyst": "only one key"}')
    with pytest.raises(Exception):
        PersonaCommentary.model_validate_json("not json")
