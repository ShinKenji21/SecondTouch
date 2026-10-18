"""Stage 1b - analytics. Pure metric formulas, the impact-moment filter, and the
running match/player/tactics statistics built from the event stream.

Coordinates are percentages of the pitch. "Attack frame" (u, v) means the
acting team's view: u=100 is the goal it attacks, v<33 is its left flank.
"""
import math
from collections import deque

PITCH_L, PITCH_W = 105.0, 68.0
GOAL_W = 7.32
BACK_LINE = {"CB", "RB", "LB"}
ON_BALL = {"PASS", "DRIBBLE", "SHOT"}


def metres(du, dv):
    return math.hypot(du * PITCH_L / 100, dv * PITCH_W / 100)


def xg_model(u, v, pressure_index=0):
    """Logistic xG from distance, goal-mouth angle and defensive pressure.

    Returns (xg, distance_m). A penalty-spot shot with no pressure is ~0.23,
    a 25 m effort ~0.05; heavy pressure (index 80) roughly halves either.
    """
    dx = (100 - u) * PITCH_L / 100
    dy = (v - 50) * PITCH_W / 100
    dist = math.hypot(dx, dy)
    angle = math.atan2(GOAL_W * dx, dx * dx + dy * dy - (GOAL_W / 2) ** 2)
    if angle < 0:
        angle += math.pi
    logit = -1.2 - 0.09 * dist + 1.5 * angle - 0.005 * pressure_index
    return round(1 / (1 + math.exp(-logit)), 2), round(dist, 1)


def pressure_from_distance(nearest_m):
    """Nearest-defender distance (m) -> (index 0-100, LOW/MEDIUM/HIGH)."""
    idx = round(max(0.0, min(100.0, 100 - nearest_m * 11)))
    return idx, ("HIGH" if idx >= 66 else "MEDIUM" if idx >= 33 else "LOW")


def pass_difficulty(length_m, angle_rad, pressure_index, receiver_space_m):
    """0-100 from pass length, direction (0 = straight at goal), pressure on the
    passer, and how tightly the receiver is marked. Clamped to 5-99."""
    forward = max(0.0, math.cos(angle_rad)) * 18
    tight = max(0.0, 5 - receiver_space_m) * 3
    score = 5 + length_m * 1.2 + pressure_index * 0.3 + forward + tight
    return round(max(5, min(99, score)))


def impact_moment(ev):
    """Return (is_impact_moment, reasons). Shots, high-pressure turnovers,
    line-breaking passes, cards and goals are worth the AI's attention."""
    t, o, m = ev["event_type"], ev["outcome"], ev["metrics"]
    reasons = []
    if t == "SHOT":
        reasons.append("goal" if o == "GOAL" else "shot")
        if (m["xg"] or 0) >= 0.3:
            reasons.append("big_chance")
    if t == "PASS" and o == "COMPLETE":
        gain, diff, byp = m["forward_gain_m"] or 0, m["pass_difficulty"] or 0, m["players_bypassed"] or 0
        if (gain >= 25 and diff >= 70) or byp >= 6:
            reasons.append("line_breaking_pass")
    if m.get("pressure") == "HIGH" and (
        (t == "TACKLE" and o == "WON") or (t == "PASS" and o == "INTERCEPTED")
    ):
        reasons.append("high_press_turnover")
    if ev.get("card"):
        reasons.append("red_card" if ev["card"] == "RED" else "yellow_card")
    return bool(reasons), reasons


def attack_frame(team, home, x, y):
    return (x, y) if team == home else (100 - x, 100 - y)


def zone_of(u, v):
    third = "defensive" if u < 33.3 else "middle" if u < 66.6 else "final"
    channel = "left" if v < 33.3 else "central" if v < 66.6 else "right"
    return third, channel


class MatchStats:
    """Accumulates everything the dashboard shows that is not a single event."""

    def __init__(self, squads, formations, home, away):
        self.squads, self.formations = squads, formations
        self.home, self.away = home, away
        self.teams = (home, away)
        self.minute = 0.0
        self.players = {}
        for team, squad in squads.items():
            for pid, p in squad.items():
                self.players[(team, pid)] = {
                    "id": pid, "name": p["name"], "num": p["num"], "pos": p["pos"],
                    "starter": p["starter"], "on": 0.0 if p["starter"] else None, "off": None,
                    "goals": 0, "assists": 0, "shots": 0, "on_target": 0, "xg": 0.0,
                    "passes": 0, "passes_completed": 0, "key_passes": 0, "line_breaks": 0,
                    "dribbles": 0, "dribbles_won": 0, "tackles": 0, "tackles_won": 0,
                    "interceptions": 0, "fouls": 0, "yellow": 0, "red": 0, "saves": 0,
                    "touches": 0, "sprints": 0,
                }
        z = lambda: {t: 0 for t in self.teams}
        self.t_on_ball, self.t_shots, self.t_on_target, self.t_xg = z(), z(), z(), {t: 0.0 for t in self.teams}
        self.t_passes, self.t_passes_ok, self.t_big_chances = z(), z(), z()
        self.t_def_actions_high, self.t_opp_passes_deep = z(), z()
        self.t_press_wins = z()
        self.channels = {t: {"left": 0, "central": 0, "right": 0} for t in self.teams}
        self.final_third = z()
        self.shape = {t: {"in": [0.0, 0.0, 0.0, 0], "out": [0.0, 0.0, 0.0, 0]} for t in self.teams}
        self.avg_pos = {}
        self.goals_against = z()
        self.momentum_window = deque(maxlen=12)
        self.last_pass_to = {t: None for t in self.teams}

    # ---- helpers -------------------------------------------------------
    def other(self, team):
        return self.away if team == self.home else self.home

    def frame(self, team, x, y):
        return attack_frame(team, self.home, x, y)

    def p(self, team, pid):
        return self.players.get((team, pid))

    # ---- update --------------------------------------------------------
    def update(self, ev, positions, possession):
        self.minute = ev["minute"]
        t, o, team, pid = ev["event_type"], ev["outcome"], ev["team"], ev["player"]
        m, loc = ev["metrics"], ev["location"]

        if t == "SUBSTITUTION":
            self.p(team, pid)["on"] = ev["minute"]
            self.p(team, ev["player_off"])["off"] = ev["minute"]
            return
        if t in ("HALF_TIME", "FULL_TIME"):
            return

        self._update_shape(positions, possession)
        u, v = self.frame(team, loc["start_x"], loc["start_y"])
        me = self.p(team, pid)
        opp_team = self.other(team)
        weight_for = {self.home: 0.0, self.away: 0.0}

        if t in ON_BALL:
            me["touches"] += 1
            self.t_on_ball[team] += 1
            if u >= 66.6:
                self.final_third[team] += 1
                self.channels[team][zone_of(u, v)[1]] += 1
                weight_for[team] += 1

        if t == "PASS":
            me["passes"] += 1
            self.t_passes[team] += 1
            if u < 60:
                self.t_opp_passes_deep[opp_team] += 1
            if o == "COMPLETE":
                me["passes_completed"] += 1
                self.t_passes_ok[team] += 1
                rec = self.p(team, ev["receiver"])
                rec["touches"] += 1
                if (m["forward_gain_m"] or 0) >= 15:
                    rec["sprints"] += 1  # a run in behind to meet a forward pass
                self.last_pass_to[team] = (pid, ev["receiver"])
                if "line_breaking_pass" in ev["impact_reasons"]:
                    me["line_breaks"] += 1
                    weight_for[team] += 2
            else:
                self._turnover(team, ev, weight_for)
        elif t == "DRIBBLE":
            me["dribbles"] += 1
            me["dribbles_won"] += 1
            if (m["sprint_speed_kmh"] or 0) >= 25:
                me["sprints"] += 1
            if u >= 66.6:
                weight_for[team] += 0.5
        elif t == "TACKLE":
            # actor is the defender; opponent is the player who was dribbling
            me["tackles"] += 1
            victim = self.p(opp_team, ev["opponent"])
            victim["dribbles"] += 1
            victim["touches"] += 1
            if o == "WON":
                me["tackles_won"] += 1
                me["touches"] += 1
                self.last_pass_to[opp_team] = None
                self._def_action(team, u, weight_for)
            else:
                me["fouls"] += 1
                if u < 40:
                    self.t_def_actions_high[team] += 1
                if ev["card"] == "YELLOW":
                    me["yellow"] += 1
                elif ev["card"] == "RED":
                    me["red"] += 1
                    me["yellow"] = min(me["yellow"], 1)
                    me["off"] = ev["minute"]
        elif t == "SHOT":
            me["shots"] += 1
            me["xg"] = round(me["xg"] + m["xg"], 2)
            self.t_shots[team] += 1
            self.t_xg[team] = round(self.t_xg[team] + m["xg"], 2)
            if m["xg"] >= 0.3:
                self.t_big_chances[team] += 1
            weight_for[team] += 2 + m["xg"] * 8
            lp = self.last_pass_to[team]
            if lp and lp[1] == pid:
                self.p(team, lp[0])["key_passes"] += 1
            if o in ("GOAL", "SAVED"):
                me["on_target"] += 1
                self.t_on_target[team] += 1
            if o == "SAVED":
                self.p(opp_team, ev["opponent"])["saves"] += 1
            if o == "GOAL":
                me["goals"] += 1
                self.goals_against[opp_team] += 1
                weight_for[team] += 4
                if lp and lp[1] == pid:
                    self.p(team, lp[0])["assists"] += 1
            self.last_pass_to[team] = None

        for side, w in weight_for.items():
            if w:
                self.momentum_window.append((side, w))

    def _turnover(self, team, ev, weight_for):
        winner = self.other(team)
        interceptor = self.p(winner, ev["opponent"])
        interceptor["interceptions"] += 1
        interceptor["touches"] += 1
        self.last_pass_to[team] = None
        loc = ev["location"]
        u, _ = self.frame(winner, loc["end_x"], loc["end_y"])
        self._def_action(winner, u, weight_for)

    def _def_action(self, team, u, weight_for):
        """Ball won by `team` at attack-frame depth u."""
        if u > 40:
            self.t_def_actions_high[team] += 1
        if u > 50:
            self.t_press_wins[team] += 1
            weight_for[team] += 1.5

    def _update_shape(self, positions, possession):
        for team in self.teams:
            pts = []
            for pid, (x, y) in positions.get(team, {}).items():
                key = (team, pid)
                acc = self.avg_pos.setdefault(key, [0.0, 0.0, 0])
                acc[0] += x; acc[1] += y; acc[2] += 1
                pos = self.players[key]["pos"]
                if pos != "GK":
                    u, v = self.frame(team, x, y)
                    pts.append((u, v, pos in BACK_LINE))
            if not pts:
                continue
            back = [u for u, _, b in pts if b] or [min(u for u, _, _ in pts)]
            line = sum(back) / len(back)
            width = max(v for _, v, _ in pts) - min(v for _, v, _ in pts)
            depth = max(u for u, _, _ in pts) - line
            acc = self.shape[team]["in" if possession == team else "out"]
            acc[0] += line; acc[1] += width; acc[2] += depth; acc[3] += 1

    # ---- outputs -------------------------------------------------------
    def momentum(self):
        h = sum(w for s, w in self.momentum_window if s == self.home)
        a = sum(w for s, w in self.momentum_window if s == self.away)
        return round(100 * (h - a) / (h + a + 3))

    def possession(self):
        h, a = self.t_on_ball[self.home], self.t_on_ball[self.away]
        tot = h + a
        return [round(100 * h / tot), 100 - round(100 * h / tot)] if tot else [50, 50]

    def summary(self):
        return {
            "xg": [self.t_xg[self.home], self.t_xg[self.away]],
            "shots": [self.t_shots[self.home], self.t_shots[self.away]],
            "momentum": self.momentum(),
            "possession": self.possession(),
        }

    def minutes(self, p):
        if p["on"] is None:
            return 0
        end = p["off"] if p["off"] is not None else self.minute
        return max(0, int(end - p["on"]))

    def rating(self, p):
        if p["on"] is None:
            return None
        failed = p["passes"] - p["passes_completed"]
        r = (6.0 + 0.9 * p["goals"] + 0.6 * p["assists"] + 0.25 * p["key_passes"]
             + 0.04 * p["passes_completed"] - 0.08 * failed + 0.2 * p["line_breaks"]
             + 0.12 * p["dribbles_won"] - 0.1 * (p["dribbles"] - p["dribbles_won"])
             + 0.2 * p["tackles_won"] + 0.15 * p["interceptions"] + 0.1 * p["on_target"]
             + 0.6 * p["xg"] + 0.3 * p["saves"] - 0.1 * p["fouls"] - 0.3 * p["yellow"] - 1.5 * p["red"])
        return round(max(3.0, min(10.0, r)), 1)

    def team_stats(self, team):
        ps = [p for (t, _), p in self.players.items() if t == team]
        played = [(self.rating(p), self.minutes(p)) for p in ps if p["on"] is not None]
        mins = sum(m for _, m in played)
        rating = (sum(r * m for r, m in played) / mins) if mins else 6.0
        passes = self.t_passes[team]
        return {
            "rating": round(rating, 1),
            "possession": self.possession()[0 if team == self.home else 1],
            "shots": self.t_shots[team], "on_target": self.t_on_target[team],
            "xg": self.t_xg[team], "big_chances": self.t_big_chances[team],
            "passes": passes,
            "pass_pct": round(100 * self.t_passes_ok[team] / passes) if passes else 0,
            "tackles_won": sum(p["tackles_won"] for p in ps),
            "interceptions": sum(p["interceptions"] for p in ps),
            "fouls": sum(p["fouls"] for p in ps),
            "yellow": sum(p["yellow"] for p in ps), "red": sum(p["red"] for p in ps),
            "saves": sum(p["saves"] for p in ps),
        }

    def player_rows(self, team):
        rows = []
        for (t, pid), p in self.players.items():
            if t != team:
                continue
            row = {k: p[k] for k in ("id", "name", "num", "pos", "starter", "goals", "assists",
                                     "shots", "on_target", "xg", "passes", "passes_completed",
                                     "key_passes", "line_breaks", "dribbles", "dribbles_won",
                                     "tackles", "tackles_won", "interceptions", "fouls", "yellow",
                                     "red", "saves", "touches", "sprints")}
            row["minutes"] = self.minutes(p)
            row["rating"] = self.rating(p)
            row["sub_on"] = None if p["starter"] or p["on"] is None else int(p["on"])
            row["sub_off"] = None if p["off"] is None else int(p["off"])
            rows.append(row)
        return rows

    def tactics(self, team):
        def avg(phase):
            s = self.shape[team][phase]
            if not s[3]:
                return None
            return {
                "line_height_m": round(s[0] / s[3] * PITCH_L / 100, 1),
                "width_m": round(s[1] / s[3] * PITCH_W / 100, 1),
                "length_m": round(s[2] / s[3] * PITCH_L / 100, 1),
            }
        ch = self.channels[team]
        tot = sum(ch.values())
        opp = self.other(team)
        acts = self.t_def_actions_high[team]
        avg_positions = {}
        for (t, pid), (sx, sy, n) in self.avg_pos.items():
            if t == team and n:
                avg_positions[pid] = [round(sx / n, 1), round(sy / n, 1)]
        return {
            "formation": self.formations[team],
            "in_possession": avg("in"),
            "out_of_possession": avg("out"),
            "channels": {k: (round(100 * c / tot) if tot else 0) for k, c in ch.items()},
            "final_third_actions": self.final_third[team],
            "press_wins": self.t_press_wins[team],
            "ppda": round(self.t_opp_passes_deep[opp] / acts, 1) if acts else None,
            "avg_positions": avg_positions,
        }

    def snapshot(self):
        return {
            "teams": {t: self.team_stats(t) for t in self.teams},
            "players": {t: self.player_rows(t) for t in self.teams},
            "tactics": {t: self.tactics(t) for t in self.teams},
        }

    def player_line(self, team, pid):
        """Compact stats for Player Cam text."""
        p = self.p(team, pid)
        if not p:
            return None
        return {"touches": p["touches"], "sprints": p["sprints"], "passes": p["passes"],
                "passes_completed": p["passes_completed"], "shots": p["shots"], "goals": p["goals"],
                "tackles_won": p["tackles_won"], "rating": self.rating(p)}
