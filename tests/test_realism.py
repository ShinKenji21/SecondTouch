"""Added time, VAR, own goals, woodwork and rebounds, injuries, substitutions, fatigue,
score-dependent tactics, playing styles and red-card reshuffles."""
import statistics
from collections import Counter

import pytest

from analytics import MatchStats
from generator import AWAY, FORMATIONS, HOME, MAX_SUBS, SQUADS, STYLE, MatchSim
from models import Event
from persona_router import Context, alert_text, render, story

SEEDS = range(30)


def play(seed):
    sim = MatchSim(seed=seed)
    stats = MatchStats(SQUADS, FORMATIONS, HOME, AWAY)
    rows = []
    while (ev := sim.next_event()) is not None:
        stats.update(ev, sim.positions, sim.possession)
        rows.append({"ev": ev, "alerts": list(stats.alerts), "buildup": list(stats.buildup),
                     "fitness": sim.fitness(), "possession": sim.possession})
    return sim, stats, rows


@pytest.fixture(scope="module")
def matches():
    return {seed: play(seed) for seed in SEEDS}


def events(matches):
    for _, _, rows in matches.values():
        for r in rows:
            yield r["ev"]


def test_every_event_validates(matches):
    for ev in events(matches):
        Event.model_validate(ev)


def test_added_time_is_announced_once_per_half_and_played(matches):
    for sim, _, rows in matches.values():
        evs = [r["ev"] for r in rows]
        announced = [(e["period"], e["added_time"]) for e in evs if e["added_time"]]
        assert [p for p, _ in announced] == [1, 2]
        a1, a2 = announced[0][1], announced[1][1]
        assert 1 <= a1 <= 6 and 2 <= a2 <= 9
        ht = next(i for i, e in enumerate(evs) if e["event_type"] == "HALF_TIME")
        first_half = [e for e in evs[:ht] if e["event_type"] != "HALF_TIME"]
        assert first_half[-1]["minute"] >= 45 + a1 - 1
        assert all(e["period"] == 1 for e in evs[:ht + 1]) and all(e["period"] == 2 for e in evs[ht + 1:])
        assert any(e["clock"].startswith("45+") for e in first_half)
        assert evs[ht + 1]["minute"] >= 45 and evs[-1]["minute"] >= 90 + a2 - 1


def test_var_never_changes_the_score_and_restarts_with_a_free_kick(matches):
    seen = Counter()
    for _, _, rows in matches.values():
        prev = None
        for r in rows:
            ev = r["ev"]
            if ev["var"]:
                seen[ev["var"]["decision"]] += 1
                assert ev["event_type"] == "SHOT" and ev["set_piece"] != "PENALTY"
            if ev["outcome"] == "DISALLOWED":
                assert ev["var"]["decision"] == "NO_GOAL" and ev["var"]["reason"]
                assert ev["score"] == prev["score"]
                assert ev["restart"] == "FREE_KICK" and ev["restart_team"] != ev["team"]
            if ev["var"] and ev["var"]["decision"] == "GOAL_STANDS":
                assert ev["outcome"] == "GOAL"
            prev = ev
    assert seen["GOAL_STANDS"] > 0


def test_own_goals_count_for_the_other_side(matches):
    found = 0
    for _, stats, rows in matches.values():
        prev = {"home": 0, "away": 0}
        for r in rows:
            ev = r["ev"]
            if ev["outcome"] == "OWN_GOAL":
                found += 1
                side = "home" if ev["team"] == HOME else "away"
                assert ev["score"][side] == prev[side] + 1
                opp = AWAY if ev["team"] == HOME else HOME
                assert ev["opponent"] in SQUADS[opp]
            prev = ev["score"]
        og = {t: sum(p["own_goals"] for p in stats.player_rows(t)) for t in (HOME, AWAY)}
        assert stats.team_stats(HOME)["own_goals_for"] == og[AWAY]
    assert found > 0


def test_rebounds_follow_saves_or_the_woodwork(matches):
    rebounds = 0
    for _, _, rows in matches.values():
        evs = [r["ev"] for r in rows]
        for i, ev in enumerate(evs):
            if "rebound" in ev["tags"]:
                rebounds += 1
                before = next(e for e in reversed(evs[:i]) if e["event_type"] not in ("SUBSTITUTION", "INJURY"))
                assert before["outcome"] in ("SAVED", "WOODWORK") and ev["team"] == before["team"]
    assert rebounds > 0


def test_injuries_lead_to_a_forced_change_when_subs_are_left(matches):
    injuries = 0
    for _, _, rows in matches.values():
        evs = [r["ev"] for r in rows]
        for i, ev in enumerate(evs):
            if ev["event_type"] != "INJURY":
                continue
            injuries += 1
            assert evs[i - 1]["outcome"] == "FOUL" and evs[i - 1]["opponent"] == ev["player"]
            later = [e for e in evs[i + 1:] if e["event_type"] == "SUBSTITUTION" and e["team"] == ev["team"]]
            used_before = sum(1 for e in evs[:i] if e["event_type"] == "SUBSTITUTION" and e["team"] == ev["team"])
            if used_before < MAX_SUBS and evs[-1]["event_type"] == "FULL_TIME":
                forced = [e for e in later if "injury" in e["tags"]]
                if forced:
                    assert forced[0]["player_off"] == ev["player"]
    assert injuries > 0


def test_substitution_rules(matches):
    for _, _, rows in matches.values():
        evs = [r["ev"] for r in rows]
        for team in (HOME, AWAY):
            subs = [e for e in evs if e["event_type"] == "SUBSTITUTION" and e["team"] == team]
            assert len(subs) <= MAX_SUBS
            off = {e["player_off"] for e in subs}
            assert not off & {e["player"] for e in subs}, "a player who came off came back on"
            assert all(e["tags"] in ([], ["injury"]) for e in subs)  # only an injury is shown as a reason
            assert all(e["player"] in SQUADS[team] and not SQUADS[team][e["player"]]["starter"] for e in subs)


def test_players_tire_and_substitutes_are_fresher(matches):
    early, late, fresh = [], [], []
    for _, _, rows in matches.values():
        at20 = next(r["fitness"] for r in rows if r["ev"]["minute"] >= 20)
        end = rows[-1]["fitness"]
        subs_on = {(r["ev"]["team"], r["ev"]["player"]) for r in rows if r["ev"]["event_type"] == "SUBSTITUTION"}
        for t in (HOME, AWAY):
            for pid, v in end[t].items():
                (fresh if (t, pid) in subs_on else late).append(v)
            early += list(at20[t].values())
    assert statistics.mean(early) > statistics.mean(late) + 15
    assert statistics.mean(fresh) > statistics.mean(late)


def test_managers_change_approach_with_the_score(matches):
    changes = Counter()
    for _, _, rows in matches.values():
        for r in rows:
            ev = r["ev"]
            for team, stance in (ev["stance_change"] or {}).items():
                changes[stance] += 1
                diff = ev["score"]["home" if team == HOME else "away"] - ev["score"]["away" if team == HOME else "home"]
                if stance == "CHASING":
                    assert diff < 0 and ev["period"] == 2
                elif stance == "PROTECTING":
                    assert diff > 0 and ev["period"] == 2
            for a in r["alerts"]:
                if a["key"] in ("chasing", "protecting", "added_time"):
                    for lang in ("en", "es", "ja"):
                        assert alert_text(a, lang)
    assert changes["CHASING"] > 0 and changes["PROTECTING"] > 0


def test_playing_styles_from_the_reference_data_show(matches):
    poss, length = {HOME: [], AWAY: []}, {HOME: [], AWAY: []}
    for _, stats, rows in matches.values():
        p = stats.possession()
        poss[HOME].append(p[0])
        poss[AWAY].append(p[1])
        for r in rows:
            ev = r["ev"]
            if ev["event_type"] == "PASS" and ev["outcome"] == "COMPLETE" and not ev["set_piece"]:
                length[ev["team"]].append(ev["length_m"])
    more_possession = max((HOME, AWAY), key=lambda t: STYLE[t]["possession_bias"])
    more_direct = max((HOME, AWAY), key=lambda t: STYLE[t]["directness"])
    other = lambda t: AWAY if t == HOME else HOME
    assert statistics.mean(poss[more_possession]) > statistics.mean(poss[other(more_possession)])
    assert statistics.mean(length[more_direct]) > statistics.mean(length[other(more_direct)])


def test_crosses_lead_to_headers(matches):
    c = Counter()
    for ev in events(matches):
        if "cross" in ev["tags"]:
            c["cross"] += 1
        if ev["body_part"] == "HEAD":
            c["header"] += 1
    assert c["cross"] / len(SEEDS) >= 3 and c["header"] / len(SEEDS) >= 2


def test_a_midfielder_drops_in_when_a_defender_is_sent_off():
    sim = MatchSim(seed=1)
    cb = next(p for p, s in sim.slots[HOME].items() if s[0] == "CB")
    slot = sim.slots[HOME][cb]
    cover = sim._send_off(HOME, cb)
    assert cover and sim.slots[HOME][cover["player"]] == slot and cb not in sim.slots[HOME]
    assert len(sim.slots[HOME]) == 10


def test_new_moments_render_and_tell_stories_in_every_language(matches):
    kinds = set()
    for seed in SEEDS:
        sim, stats, rows = matches[seed]
        lines = {(t, p): stats.player_line(t, p) for t in (HOME, AWAY) for p in SQUADS[t]}
        for r in rows:
            ev = r["ev"]
            kind = ev["outcome"] if ev["outcome"] in ("OWN_GOAL", "WOODWORK", "DISALLOWED") else \
                ev["event_type"] if ev["event_type"] in ("INJURY", "SUBSTITUTION") else \
                next((t for t in ev["tags"] if t in ("cross", "rebound", "claimed")), None)
            if not kind or (kind in kinds and seed > 3):
                continue
            kinds.add(kind)
            ctx = Context(HOME, AWAY, stats.summary(), sim.positions, HOME, "Thornquist", lines[(HOME, "Thornquist")],
                          {t: (0.0, 0) for t in (HOME, AWAY)}, right_team=ev["right_team"], fav_team=AWAY)
            for lang in ("en", "es", "ja"):
                out = render(ev, ctx, lang)
                assert all(v and "{" not in v for v in out.values()), (kind, lang, out)
                assert "{" not in story(ev, r["buildup"], ctx, lines, lang)
    assert {"OWN_GOAL", "WOODWORK", "INJURY", "SUBSTITUTION", "cross", "rebound", "claimed"} <= kinds


def test_recaps_read_well_in_every_language(matches):
    from persona_router import recap_text
    sim, stats, rows = matches[4]
    ev = rows[len(rows) // 3]["ev"]
    s = stats.summary()
    r = {"kind": "PERIODIC", "start": "0'", "end": ev["clock"], "clock": ev["clock"], "score": ev["score"],
         "home": HOME, "away": AWAY, "xg": s["xg"], "shots": s["shots"], "possession": s["possession"],
         "momentum": s["momentum"], "fav_team": HOME, "moments": stats.key_moments[-8:]}
    for lang in ("en", "es", "ja"):
        periodic, catchup = recap_text(r, lang), recap_text(dict(r, kind="CATCHUP", start="12'"), lang)
        assert "{" not in periodic + catchup and len(periodic) > 40
        assert periodic.split()[0] != catchup.split()[0]
    assert "Brackenford fans" in recap_text(dict(r, kind="CATCHUP", start="12'"), "en")
    assert "fans" not in recap_text(r, "en")  # only a personal catch-up speaks to the viewer's club


def test_full_time_story_tells_the_turning_points_in_order():
    from persona_router import story_text
    arc = {"final_score": {"home": 2, "away": 1}, "half_time_score": {"home": 0, "away": 1}, "winner": "Brackenford",
           "on_top": {"half_1": "Kestermouth", "half_2": "Kestermouth"},
           "turning_points": [
               {"clock": "30'", "kind": "opener", "team": "Kestermouth", "player": "Strachley", "own_goal": False, "score": {"home": 0, "away": 1}},
               {"clock": "58'", "kind": "equaliser", "team": "Brackenford", "player": "Thornquist", "own_goal": False, "score": {"home": 1, "away": 1}},
               {"clock": "63'", "kind": "red_card", "team": "Kestermouth", "player": "Ekwuruke"},
               {"clock": "80'", "kind": "ahead", "team": "Brackenford", "player": "Adewolu-Hart", "own_goal": False, "score": {"home": 2, "away": 1}}]}
    en = story_text(arc, "Brackenford", "en")
    assert en.index("Strachley") < en.index("Thornquist") < en.index("Ekwuruke") < en.index("Adewolu-Hart")
    assert "0-1 at the break" in en and "held on" not in en          # they came from behind
    arc["turning_points"].append({"clock": "84'", "kind": "momentum_swing", "team": "Kestermouth"})
    assert story_text(arc, "Brackenford", "en").endswith("Brackenford held on for the win.")
    for lang in ("es", "ja"):
        assert "Adewolu-Hart" in story_text(arc, "Brackenford", lang)
