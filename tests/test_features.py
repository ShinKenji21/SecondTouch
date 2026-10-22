"""Half-time side switch, possession changes, game flow, milestones, stories,
reports, overlay cues and the dataset export."""
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

import overlays
from analytics import MatchStats, is_key_event
from generator import AWAY, FORMATIONS, HOME, SQUADS, MatchSim
from persona_router import Context, alert_text, report_text, story

BACKEND = Path(__file__).resolve().parent.parent / "backend"


def run_match(seed):
    sim = MatchSim(seed=seed)
    stats = MatchStats(SQUADS, FORMATIONS, HOME, AWAY)
    out = []
    while (ev := sim.next_event()) is not None:
        before = sim.half_time_done
        stats.update(ev, sim.positions, sim.possession)
        out.append({"ev": ev, "alerts": list(stats.alerts), "buildup": list(stats.buildup),
                    "report": stats.report(ev) if ev["event_type"] in ("HALF_TIME", "FULL_TIME") else None,
                    "summary": stats.summary(), "second_half": before or ev["event_type"] == "HALF_TIME",
                    "possession": sim.possession, "positions": {t: dict(p) for t, p in sim.positions.items()}})
    return sim, stats, out


@pytest.mark.parametrize("seed", range(4))
def test_teams_change_ends_at_half_time(seed):
    _, _, rows = run_match(seed)
    for r in rows:
        assert r["ev"]["right_team"] == (AWAY if r["second_half"] else HOME)
    # Arsenal's keeper starts on the left and finishes on the right
    first = next(r for r in rows if not r["second_half"])
    last = rows[-1]
    assert first["positions"][HOME]["Raya"][0] < 50 < last["positions"][HOME]["Raya"][0]


@pytest.mark.parametrize("seed", range(4))
def test_goals_go_into_the_right_net_each_half(seed):
    _, _, rows = run_match(seed)
    for r in rows:
        ev = r["ev"]
        if ev["event_type"] == "SHOT" and ev["outcome"] == "GOAL":
            expected_x = 100.0 if ev["team"] == ev["right_team"] else 0.0
            assert ev["location"]["end_x"] == expected_x


def test_possession_change_flag_matches_the_ball():
    _, _, rows = run_match(2)
    prev = None
    for r in rows:
        ev = r["ev"]
        if prev is not None and ev["event_type"] in ("PASS", "DRIBBLE", "SHOT", "TACKLE"):
            assert ev["possession_change"] == (r["possession"] != prev)
        if ev["event_type"] in ("PASS", "DRIBBLE", "SHOT", "TACKLE"):
            prev = r["possession"]
        elif ev["event_type"] == "HALF_TIME":
            prev = r["possession"]


def test_game_flow_summary_is_well_formed():
    _, _, rows = run_match(5)
    for r in rows:
        f = r["summary"]["flow"]
        assert f["state"] in ("CONTROL", "BALANCED", "CHAOS")
        assert (f["state_team"] in (HOME, AWAY)) == (f["state"] == "CONTROL")
        assert 0 <= f["turnover_rate"] <= 100 and f["tempo"] in ("HIGH", "STEADY", "SLOW")
        assert all(0 <= v <= 100 for v in f["press"].values())


def test_alerts_render_in_every_language():
    seen = set()
    for seed in range(6):
        _, _, rows = run_match(seed)
        for r in rows:
            for a in r["alerts"]:
                seen.add(a["key"])
                for lang in ("en", "es", "ja"):
                    assert alert_text(a, lang)
    assert {"speed", "distance", "first_goal", "chaos", "control"} <= seen


def test_distance_and_speed_are_realistic():
    _, stats, _ = run_match(9)
    full = [r for t in (HOME, AWAY) for r in stats.player_rows(t) if r["minutes"] >= 89 and r["pos"] != "GK"]
    assert all(8.5 <= r["distance_km"] <= 12.5 for r in full)
    assert all(r["top_speed"] <= 36 for r in full)


def test_key_events_get_a_story_and_reports_a_narrative():
    sim, stats, rows = run_match(1)
    lines = {(t, p): stats.player_line(t, p) for t in (HOME, AWAY) for p in SQUADS[t]}
    ctx = Context(HOME, AWAY, stats.summary(), sim.positions, HOME, "Saka", lines[(HOME, "Saka")],
                  {t: (0.0, 0) for t in (HOME, AWAY)})
    stories = 0
    for r in rows:
        ev = r["ev"]
        if is_key_event(ev):
            for lang in ("en", "es", "ja"):
                assert story(ev, r["buildup"], ctx, lines, lang)
            stories += 1
        if r["report"]:
            for lang in ("en", "es", "ja"):
                text = report_text(r["report"], lang)
                assert len(text) > 40
    assert stories >= 6
    kinds = [r["report"]["kind"] for r in rows if r["report"]]
    assert kinds == ["HALF_TIME", "FULL_TIME"]


def test_overlay_cues_are_timed_and_serialisable():
    _, _, rows = run_match(4)
    types = set()
    for r in rows:
        alerts = [dict(a, text="x") for a in r["alerts"]]
        cues = overlays.build(r["ev"], r["positions"], {"analyst": "a"}, alerts, None, r["report"], 1500)
        json.dumps(cues)
        for c in cues:
            types.add(c["type"])
            assert c["at_ms"] >= r["ev"]["generated_at"] and c["duration_ms"] > 0
    assert {"player_tag", "action", "speed_badge", "lower_third", "banner", "report_card"} <= types


def test_dataset_export(tmp_path):
    out = tmp_path / "ds"
    subprocess.run([sys.executable, "export_dataset.py", "--matches", "2", "--seed", "3", "--out", str(out)],
                   cwd=BACKEND, check=True, capture_output=True)
    matches = list(csv.DictReader(open(out / "matches.csv", encoding="utf-8")))
    events = list(csv.DictReader(open(out / "events.csv", encoding="utf-8")))
    jsonl = [json.loads(line) for line in open(out / "events.jsonl", encoding="utf-8")]
    assert len(matches) == 2 and len(events) == len(jsonl) > 200
    assert "positions" in jsonl[0] and (out / "players.csv").exists() and (out / "README.md").exists()
