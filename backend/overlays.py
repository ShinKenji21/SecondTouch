"""Overlay cues: timed, machine-readable graphics instructions.

Each event produces a list of cues a broadcast graphics engine could render in
sync with the match feed. Times are milliseconds relative to the event's
`generated_at`; `at_ms` is the absolute epoch time. Pitch anchors are in the
same percentage coordinates as the event (x: 0-100 left to right).

Cue types
  player_tag      name tag over a player             anchor = player position
  action          pass/shot/dribble/tackle graphic   path = [start, end]
  speed_badge     sprint above the speed threshold   anchor = player position
  distance_badge  distance milestone                 anchor = player position
  lower_third     commentary for an impact moment    layout = lower_third
  stat_card       milestone or game-flow note        layout = corner
  set_piece       corner, free kick, throw-in, ...   anchor = where it is taken
  banner          goal, card, penalty, sub, HT, FT   layout = top_banner
  report_card     half-time / full-time report       layout = fullscreen
"""

SCHEMA_VERSION = 1


def build(ev, positions, commentary, alerts, story, report, interval_ms):
    cues = []
    seq = ev["seq"]
    base = ev["generated_at"]

    def add(cue_type, start, duration, priority, **fields):
        cue = {"id": f"{seq}-{len(cues) + 1}", "type": cue_type, "start_ms": start, "duration_ms": duration,
               "at_ms": round(base + start), "priority": priority}
        cue.update(fields)
        cues.append(cue)

    def pos_of(team, pid):
        p = positions.get(team, {}).get(pid)
        return {"x": p[0], "y": p[1]} if p else None

    t, team, loc = ev["event_type"], ev["team"], ev["location"]
    if team and t not in ("SUBSTITUTION",):
        add("player_tag", 0, interval_ms, 2, team=team, player=ev["player"],
            anchor={"x": loc["start_x"], "y": loc["start_y"]})
        add("action", 0, interval_ms, 2, action=t, outcome=ev["outcome"], team=team,
            path=[{"x": loc["start_x"], "y": loc["start_y"]}, {"x": loc["end_x"], "y": loc["end_y"]}],
            metrics={k: v for k, v in ev["metrics"].items() if v is not None},
            set_piece=ev.get("set_piece"), body_part=ev.get("body_part"), restart=ev.get("restart"))
        if ev.get("set_piece"):
            add("set_piece", 0, interval_ms, 2, kind=ev["set_piece"], team=team, player=ev["player"],
                anchor={"x": loc["start_x"], "y": loc["start_y"]})
        if ev["receiver"]:
            add("player_tag", round(interval_ms * 0.5), round(interval_ms * 0.5), 3, team=team,
                player=ev["receiver"], anchor=pos_of(team, ev["receiver"]))

    for a in alerts:
        if a["kind"] == "speed":
            add("speed_badge", 300, 2600, 2, team=a["team"], player=a["player"], value_kmh=a["value"],
                anchor=pos_of(a["team"], a["player"]), text=a["text"])
        elif a["kind"] == "distance":
            add("distance_badge", 300, 2600, 3, team=a["team"], player=a["player"], value_km=a["value"],
                anchor=pos_of(a["team"], a["player"]), text=a["text"])
        else:
            add("stat_card", 500, 4500, 2, layout="corner", key=a["key"], team=a["team"],
                player=a["player"], text=a["text"])

    if ev["is_impact_moment"]:
        add("lower_third", 400, 5000, 1, layout="lower_third", reasons=ev["impact_reasons"],
            text=commentary)

    penalty = ev.get("restart") == "PENALTY"
    if ev["outcome"] == "GOAL" or ev.get("card") or penalty or t in ("SUBSTITUTION", "HALF_TIME", "FULL_TIME"):
        kind = "GOAL" if ev["outcome"] == "GOAL" else "PENALTY" if penalty else ev["card"] or t
        add("banner", 0, 4000, 1, layout="top_banner", kind=kind, team=team, player=ev["player"],
            player_off=ev["player_off"], score=ev["score"], story=story)

    if report:
        add("report_card", 800, 12000, 1, layout="fullscreen", report=report)
    return cues
