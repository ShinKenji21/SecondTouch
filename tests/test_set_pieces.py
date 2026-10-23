"""Set pieces, fouls, cards, offside and the ball going out of play."""
import math
from collections import Counter

import pytest

import overlays
from analytics import MatchStats, attack_frame, is_key_event
from generator import (AWAY, BOX_HALF_V, BOX_U, FORMATIONS, HOME, PENALTY_XG, PLAYERS, REFEREE, SIX_HALF_V,
                       SIX_U, SQUADS, MatchSim)
from models import Event
from persona_router import Context, render, story

SEEDS = range(40)


def play(seed):
    """Every event with the sim state right after it."""
    sim = MatchSim(seed=seed)
    stats = MatchStats(SQUADS, FORMATIONS, HOME, AWAY)
    rows = []
    while (ev := sim.next_event()) is not None:
        stats.update(ev, sim.positions, sim.possession)
        rows.append({"ev": ev, "positions": {t: dict(p) for t, p in sim.positions.items()},
                     "ball": sim.ball, "carrier": sim.carrier, "possession": sim.possession,
                     "slots": {t: dict(s) for t, s in sim.slots.items()}, "buildup": list(stats.buildup)})
    return sim, stats, rows


@pytest.fixture(scope="module")
def matches():
    return {seed: play(seed) for seed in SEEDS}


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 1.05, (a[1] - b[1]) * 0.68)


def test_events_validate_and_new_fields_are_consistent(matches):
    for _, _, rows in matches.values():
        for r in rows:
            ev = r["ev"]
            Event.model_validate(ev)
            assert (ev["restart"] is None) == (ev["restart_team"] is None)
            if ev["body_part"]:
                assert ev["event_type"] == "SHOT"
            if ev["outcome"] in ("OUT", "OFFSIDE"):
                assert ev["restart"] and ev["restart_team"] != ev["team"] or ev["restart"] == "CORNER"


def test_every_restart_is_taken_next_by_the_right_team(matches):
    for _, _, rows in matches.values():
        for i, r in enumerate(rows):
            ev = r["ev"]
            if not ev["restart"]:
                continue
            # treatment and substitutions may happen while play is stopped; half-time cancels the restart
            nxt = next(x["ev"] for x in rows[i + 1:] if x["ev"]["event_type"] not in ("SUBSTITUTION", "INJURY"))
            if nxt["event_type"] in ("HALF_TIME", "FULL_TIME"):
                continue
            assert nxt["set_piece"] == ev["restart"]
            assert nxt["team"] == ev["restart_team"]
            assert r["possession"] == ev["restart_team"]


def test_set_pieces_are_taken_from_the_right_place(matches):
    for _, _, rows in matches.values():
        for r in rows:
            ev = r["ev"]
            sp, loc = ev["set_piece"], ev["location"]
            if not sp:
                continue
            u, v = attack_frame(ev["team"], ev["right_team"], loc["start_x"], loc["start_y"])
            if sp == "CORNER":
                assert u == 100 and v in (0, 100)
            elif sp == "THROW_IN":
                assert v in (0, 100)
                assert ev["event_type"] == "PASS" and ev["length_m"] <= 44
            elif sp == "GOAL_KICK":
                assert r["slots"][ev["team"]][ev["player"]][0] == "GK"
                assert u <= SIX_U + 0.1 and abs(v - 50) <= SIX_HALF_V + 0.1
            elif sp == "PENALTY":
                assert ev["event_type"] == "SHOT" and ev["metrics"]["xg"] == PENALTY_XG and ev["length_m"] == 11.0


def test_players_line_up_for_the_restart(matches):
    for _, _, rows in matches.values():
        for r in rows:
            ev, pos = r["ev"], r["positions"]
            kind, team = ev["restart"], ev["restart_team"]
            if not kind or ev["event_type"] in ("SUBSTITUTION", "INJURY"):
                continue
            opp = AWAY if team == HOME else HOME
            right = ev["right_team"]
            assert pos[team][r["carrier"]] == (round(r["ball"][0], 1), round(r["ball"][1], 1))  # taker on the ball
            if kind == "PENALTY":
                keeper = next(p for p, s in r["slots"][opp].items() if s[0] == "GK")
                for t in (HOME, AWAY):
                    for pid, (x, y) in pos[t].items():
                        if pid in (r["carrier"], keeper):
                            continue
                        u, vv = attack_frame(team, right, x, y)
                        assert not (u > BOX_U - 1 and abs(vv - 50) <= BOX_HALF_V), (pid, u, vv)
            elif kind in ("FREE_KICK", "CORNER", "GOAL_KICK"):
                for pid, xy in pos[opp].items():
                    assert metres(xy, r["ball"]) >= 8.9, (kind, pid, metres(xy, r["ball"]))


def test_takers_come_from_the_reference_attributes(matches):
    for _, _, rows in matches.values():
        for r in rows:
            ev = r["ev"]
            team = ev["team"]
            if ev["set_piece"] not in ("PENALTY", "CORNER"):
                continue
            on_pitch = [p for p, s in r["slots"][team].items() if s[0] != "GK"]
            attr = lambda p, k: PLAYERS[team][p]["attributes"][k]
            if ev["set_piece"] == "PENALTY":
                assert attr(ev["player"], "shooting") == max(attr(p, "shooting") for p in on_pitch + [ev["player"]])
            elif ev["set_piece"] == "CORNER":
                assert attr(ev["player"], "passing") == max(attr(p, "passing") for p in on_pitch + [ev["player"]])


def test_stats_add_up(matches):
    for _, stats, rows in matches.values():
        evs = [r["ev"] for r in rows]
        for team in (HOME, AWAY):
            ts = stats.team_stats(team)
            mine = [e for e in evs if e["team"] == team]
            assert ts["corners"] == sum(e["set_piece"] == "CORNER" for e in mine)
            assert ts["penalties"] == sum(e["set_piece"] == "PENALTY" for e in mine)
            assert ts["throw_ins"] == sum(e["set_piece"] == "THROW_IN" for e in mine)
            assert ts["offsides"] == sum(e["outcome"] == "OFFSIDE" for e in mine)
            assert ts["fouls"] == sum(e["outcome"] == "FOUL" for e in mine)
            assert ts["red"] == sum(e["card"] == "RED" for e in mine)
            opp = AWAY if team == HOME else HOME
            assert sum(p["fouls_won"] for p in stats.player_rows(team)) == stats.team_stats(opp)["fouls"]


def test_rates_are_realistic_and_follow_the_referee(matches):
    n = len(matches)
    c = Counter()
    for _, _, rows in matches.values():
        for r in rows:
            ev = r["ev"]
            c[ev["set_piece"]] += 1
            c[ev["outcome"]] += 1
            c[ev["card"]] += 1
            c["head"] += ev["body_part"] == "HEAD"
    per = {k: v / n for k, v in c.items()}
    assert 4 <= per["CORNER"] <= 12
    assert 7 <= per["FOUL"] <= 16
    assert 6 <= per["THROW_IN"]
    assert 1 <= per["OFFSIDE"] <= 6
    assert 2 <= per["GOAL_KICK"]
    assert per.get("PENALTY", 0) <= 0.8
    assert abs(per["YELLOW"] - REFEREE["avg_yellows_per_match"]) <= 1.0
    assert per.get("RED", 0) <= 0.45
    assert per["head"] >= 0.5


def test_set_pieces_render_and_tell_stories_in_every_language(matches):
    sim, stats, rows = matches[1]
    lines = {(t, p): stats.player_line(t, p) for t in (HOME, AWAY) for p in SQUADS[t]}
    kinds = set()
    for seed in (1, 2, 3, 4):
        sim, stats, rows = matches[seed]
        for r in rows:
            ev = r["ev"]
            if not (ev["set_piece"] or ev["restart"] or ev["body_part"] == "HEAD"):
                continue
            kinds.add(ev["set_piece"] or ev["restart"])
            ctx = Context(HOME, AWAY, stats.summary(), r["positions"], HOME, "Thornquist", lines[(HOME, "Thornquist")],
                          {t: (0.0, 0) for t in (HOME, AWAY)}, right_team=ev["right_team"], fav_team=HOME)
            for lang in ("en", "es", "ja"):
                out = render(ev, ctx, lang)
                assert all(v and "{" not in v for v in out.values()), out
                if is_key_event(ev):
                    assert story(ev, r["buildup"], ctx, lines, lang)
    assert {"CORNER", "FREE_KICK", "THROW_IN", "GOAL_KICK"} <= kinds


def test_overlay_cues_carry_set_pieces_and_penalties(matches):
    types, banners = set(), set()
    for _, _, rows in matches.values():
        for r in rows:
            for cue in overlays.build(r["ev"], r["positions"], {"analyst": "a"}, [], None, None, 1500):
                types.add(cue["type"])
                if cue["type"] == "banner":
                    banners.add(cue["kind"])
    assert "set_piece" in types and "PENALTY" in banners
