"""Stage 1b - analytics. Pure metric formulas, the impact-moment filter, and the
running match/player/tactics statistics built from the event stream: game flow
(control vs chaos, pressure shifts, tempo), milestones and threshold alerts,
possession spells for key-event stories, and half-time/full-time reports.

Coordinates are percentages of the pitch. "Attack frame" (u, v) means the
acting team's view: u=100 is the goal it attacks, v<33 is its left flank.
Teams change ends at half-time; `right_team` is whoever attacks towards x=100.
"""
import math
from collections import deque

PITCH_L, PITCH_W = 105.0, 68.0
GOAL_W = 7.32
BACK_LINE = {"CB", "RB", "LB"}
ON_BALL = {"PASS", "DRIBBLE", "SHOT"}
STATUS = {"SUBSTITUTION", "INJURY", "HALF_TIME", "FULL_TIME"}
SET_PIECE_STAT = {"CORNER": "corners", "FREE_KICK": "free_kicks", "THROW_IN": "throw_ins",
                  "PENALTY": "penalties", "GOAL_KICK": "goal_kicks"}

SPEED_ALERT_KMH = 32.0          # sprint that triggers an on-screen speed badge
DISTANCE_ALERTS_KM = (5, 10)    # distance covered that triggers a badge
JOG_M_PER_MIN = {"GK": 40}      # running between snapshots; outfield default below
JOG_DEFAULT = 92


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
    line-breaking passes, cards, penalties and goals are worth the AI's attention."""
    t, o, m = ev["event_type"], ev["outcome"], ev["metrics"]
    reasons = []
    if t == "SHOT":
        reasons.append({"GOAL": "goal", "DISALLOWED": "var_no_goal", "WOODWORK": "woodwork"}.get(o, "shot"))
        if (m["xg"] or 0) >= 0.3:
            reasons.append("big_chance")
        if ev.get("set_piece") == "PENALTY":
            reasons.append("penalty")
        elif ev.get("set_piece") == "FREE_KICK":
            reasons.append("direct_free_kick")
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
    if ev.get("restart") == "PENALTY":
        reasons.append("penalty_awarded")
    if o == "OWN_GOAL":
        reasons.append("own_goal")
    return bool(reasons), reasons


def is_key_event(ev):
    """Moments that belong in the match summary and get a story."""
    t, o = ev["event_type"], ev["outcome"]
    return (o in ("GOAL", "OWN_GOAL", "DISALLOWED", "WOODWORK") or bool(ev.get("card")) or t in ("SUBSTITUTION", "INJURY")
            or ev.get("restart") == "PENALTY"
            or (t == "SHOT" and (o == "SAVED" or ev.get("set_piece") in ("PENALTY", "FREE_KICK")
                                 or (ev["metrics"]["xg"] or 0) >= 0.3)))


def attack_frame(team, right_team, x, y):
    """Absolute pitch % -> the team's attack frame. Its own inverse."""
    return (x, y) if team == right_team else (100 - x, 100 - y)


def zone_of(u, v):
    third = "defensive" if u < 33.3 else "middle" if u < 66.6 else "final"
    channel = "left" if v < 33.3 else "central" if v < 66.6 else "right"
    return third, channel


def ball_team(ev, other):
    """Which team had the ball when the action started."""
    if ev["event_type"] == "TACKLE":
        return other(ev["team"])
    return ev["team"]


class MatchStats:
    """Accumulates everything the dashboard shows that is not a single event."""

    def __init__(self, squads, formations, home, away):
        self.squads, self.formations = squads, formations
        self.home, self.away = home, away
        self.teams = (home, away)
        self.right_team = home
        self.minute = 0.0
        self.n = 0
        self.players = {}
        for team, squad in squads.items():
            for pid, p in squad.items():
                self.players[(team, pid)] = {
                    "id": pid, "name": p["name"], "num": p["num"], "pos": p["pos"],
                    "starter": p["starter"], "on": 0.0 if p["starter"] else None, "off": None,
                    "goals": 0, "assists": 0, "shots": 0, "on_target": 0, "xg": 0.0,
                    "passes": 0, "passes_completed": 0, "key_passes": 0, "line_breaks": 0,
                    "dribbles": 0, "dribbles_won": 0, "tackles": 0, "tackles_won": 0,
                    "interceptions": 0, "fouls": 0, "fouls_won": 0, "offsides": 0,
                    "xa": 0.0, "crosses": 0, "crosses_completed": 0, "long_balls": 0, "long_balls_completed": 0,
                    "progressive_passes": 0, "aerials": 0, "aerials_won": 0, "clearances": 0, "blocks": 0,
                    "big_chances_missed": 0, "own_goals": 0,
                    "yellow": 0, "red": 0, "saves": 0,
                    "touches": 0, "sprints": 0, "distance_m": 0.0, "top_speed": 0.0,
                }
        z = lambda: {t: 0 for t in self.teams}
        self.t_on_ball, self.t_shots, self.t_on_target, self.t_xg = z(), z(), z(), {t: 0.0 for t in self.teams}
        self.t_passes, self.t_passes_ok, self.t_big_chances = z(), z(), z()
        self.t_def_actions_high, self.t_opp_passes_deep = z(), z()
        self.t_press_wins = z()
        self.t_set = {t: {k: 0 for k in SET_PIECE_STAT.values()} for t in self.teams}
        self.t_offsides = z()
        self.t_woodwork, self.t_disallowed, self.t_own_goals_for = z(), z(), z()
        self.half = 1
        self.t_diff_sum, self.t_diff_n, self.t_top_ball = z(), z(), {t: 0.0 for t in self.teams}
        self.channels = {t: {"left": 0, "central": 0, "right": 0} for t in self.teams}
        self.final_third = z()
        self.shape = {t: {"in": [0.0, 0.0, 0.0, 0], "out": [0.0, 0.0, 0.0, 0]} for t in self.teams}
        self.avg_pos = {}
        self.goals_against = z()
        self.momentum_window = deque(maxlen=12)
        self.last_pass_to = {t: None for t in self.teams}
        # game flow
        self.flow_window = deque(maxlen=16)
        self.press_under = {t: deque(maxlen=12) for t in self.teams}
        self.press_hist = {t: [] for t in self.teams}
        self.direct = {t: deque(maxlen=12) for t in self.teams}
        self.action_minutes = deque()
        self.total_actions = 0
        self.state, self.state_team = "BALANCED", None
        self.flow_log = []
        self.last_flow_alert = -99
        self.last_press_alert = {t: -99 for t in self.teams}
        # spells, milestones, alerts
        self.spell, self.spell_team, self.spell_alerted = [], None, False
        self.max_spell = z()
        self.buildup = []
        self.done = set()
        self.match_top_speed = 0.0
        self.prev_positions = None
        self.key_moments = []
        self.momentum_log = []
        self.alerts = []

    # ---- helpers -------------------------------------------------------
    def other(self, team):
        return self.away if team == self.home else self.home

    def frame(self, team, x, y):
        return attack_frame(team, self.right_team, x, y)

    def p(self, team, pid):
        return self.players.get((team, pid))

    def _alert(self, kind, key, team=None, player=None, value=None, value2=None):
        self.alerts.append({"kind": kind, "key": key, "team": team, "player": player,
                            "value": value, "value2": value2})

    def _once(self, tag):
        if tag in self.done:
            return False
        self.done.add(tag)
        return True

    # ---- update --------------------------------------------------------
    def update(self, ev, positions, possession):
        self.alerts = []
        self.n += 1
        dt = max(0.0, ev["minute"] - self.minute)
        self.minute = ev["minute"]
        t, o, team, pid = ev["event_type"], ev["outcome"], ev["team"], ev["player"]
        m, loc = ev["metrics"], ev["location"]
        if ev.get("added_time"):
            self._alert("milestone", "added_time", value=ev["added_time"])
        for side, stance in (ev.get("stance_change") or {}).items():
            if stance != "BALANCED":
                self._alert("flow", stance.lower(), team=side)

        if t in ("HALF_TIME", "FULL_TIME"):
            self.right_team = ev.get("right_team", self.right_team)
            self.prev_positions = positions  # ends swapped: don't count the walk as running
            if t == "HALF_TIME":
                self.half = 2
            return
        self._distance(positions, dt)
        if t == "SUBSTITUTION":
            self.p(team, pid)["on"] = ev["minute"]
            self.p(team, ev["player_off"])["off"] = ev["minute"]
            self.key_moments.append(self._moment(ev))
            return
        if t == "INJURY":
            self.key_moments.append(self._moment(ev))
            return

        self._update_shape(positions, possession)
        u, v = self.frame(team, loc["start_x"], loc["start_y"])
        me = self.p(team, pid)
        opp_team = self.other(team)
        weight_for = {self.home: 0.0, self.away: 0.0}
        holder = ball_team(ev, self.other)
        self.buildup = [e for e in self.spell if self.spell_team == holder][-4:]

        if ev.get("set_piece"):
            self.t_set[team][SET_PIECE_STAT[ev["set_piece"]]] += 1
        if t in ON_BALL:
            me["touches"] += 1
            self.t_on_ball[team] += 1
            if u >= 66.6:
                self.final_third[team] += 1
                self.channels[team][zone_of(u, v)[1]] += 1
                weight_for[team] += 1
            if m["ball_speed_kmh"]:
                self.t_top_ball[team] = max(self.t_top_ball[team], m["ball_speed_kmh"])

        tags = ev.get("tags") or []
        if t == "PASS":
            ok = o == "COMPLETE"
            if "cross" in tags:
                me["crosses"] += 1
                me["crosses_completed"] += ok
            if "long_ball" in tags:
                me["long_balls"] += 1
                me["long_balls_completed"] += ok
            if ok and (m["forward_gain_m"] or 0) >= 10 and not ev.get("set_piece"):
                me["progressive_passes"] += 1
            if "delivery" in tags:
                if ok:
                    rec = self.p(team, ev["receiver"])
                    rec["aerials"] += 1
                    rec["aerials_won"] += 1
                elif ev["opponent"] and "claimed" not in tags:
                    d = self.p(opp_team, ev["opponent"])
                    d["aerials"] += 1
                    d["aerials_won"] += 1
                    d["clearances"] += 1
            me["passes"] += 1
            self.t_passes[team] += 1
            self.t_diff_sum[team] += m["pass_difficulty"] or 0
            self.t_diff_n[team] += 1
            self.direct[team].append((m["forward_gain_m"] or 0) >= 15)
            if u < 60:
                self.t_opp_passes_deep[opp_team] += 1
            if o == "COMPLETE":
                me["passes_completed"] += 1
                self.t_passes_ok[team] += 1
                rec = self.p(team, ev["receiver"])
                rec["touches"] += 1
                if (m["forward_gain_m"] or 0) >= 15:
                    rec["sprints"] += 1  # a run in behind to meet a forward pass
                if m["sprint_speed_kmh"]:
                    self._speed(team, ev["receiver"], m["sprint_speed_kmh"])
                self.last_pass_to[team] = (pid, ev["receiver"])
                if "line_breaking_pass" in ev["impact_reasons"]:
                    me["line_breaks"] += 1
                    weight_for[team] += 2
                self._milestone_count(team, ev["receiver"], "touches", (25, 50))
            elif o == "INTERCEPTED":
                self._turnover(team, ev, weight_for)
            elif o == "OFFSIDE":
                self.p(team, ev["receiver"])["offsides"] += 1
                self.t_offsides[team] += 1
                self.last_pass_to[team] = None
            elif o == "OWN_GOAL":
                self.p(opp_team, ev["opponent"])["own_goals"] += 1
                self.t_own_goals_for[team] += 1
                self.goals_against[opp_team] += 1
                weight_for[team] += 4
                self.last_pass_to[team] = None
            else:  # OUT of play
                self.last_pass_to[team] = None
            self._milestone_count(team, pid, "passes_completed", (20, 40))
            for n in (50, 100, 150):
                if self.t_passes_ok[team] >= n and self._once(f"tp{team}{n}"):
                    self._alert("milestone", "team_passes", team=team, value=n)
        elif t == "DRIBBLE":
            me["dribbles"] += 1
            me["dribbles_won"] += 1
            if (m["sprint_speed_kmh"] or 0) >= 25:
                me["sprints"] += 1
            if m["sprint_speed_kmh"]:
                self._speed(team, pid, m["sprint_speed_kmh"])
            if u >= 66.6:
                weight_for[team] += 0.5
        elif t == "TACKLE":
            # actor is the defender; opponent is the player on the ball
            victim = self.p(opp_team, ev["opponent"])
            victim["touches"] += 1
            if o == "WON":
                me["tackles"] += 1
                victim["dribbles"] += 1
                me["tackles_won"] += 1
                me["touches"] += 1
                self.last_pass_to[opp_team] = None
                self._def_action(team, u, weight_for)
                self._milestone_count(team, pid, "tackles_won", (3, 5))
            else:
                me["fouls"] += 1
                victim["fouls_won"] += 1
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
            if ev.get("body_part") == "HEAD":
                me["aerials"] += 1
                me["aerials_won"] += 1
            if m["xg"] >= 0.3 and o != "GOAL":
                me["big_chances_missed"] += 1
            if o == "BLOCKED" and ev["opponent"]:
                self.p(opp_team, ev["opponent"])["blocks"] += 1
            if o == "WOODWORK":
                self.t_woodwork[team] += 1
            if o == "DISALLOWED":
                self.t_disallowed[team] += 1
            self.t_shots[team] += 1
            self.t_xg[team] = round(self.t_xg[team] + m["xg"], 2)
            if m["xg"] >= 0.3:
                self.t_big_chances[team] += 1
            weight_for[team] += 2 + m["xg"] * 8
            lp = self.last_pass_to[team]
            if lp and lp[1] == pid:
                self.p(team, lp[0])["key_passes"] += 1
                self.p(team, lp[0])["xa"] = round(self.p(team, lp[0])["xa"] + m["xg"], 2)
            if o in ("GOAL", "SAVED"):
                me["on_target"] += 1
                self.t_on_target[team] += 1
            if o == "SAVED":
                keeper = self.p(opp_team, ev["opponent"])
                keeper["saves"] += 1
                self._milestone_count(opp_team, ev["opponent"], "saves", (3, 5))
            if o == "GOAL":
                me["goals"] += 1
                self.goals_against[opp_team] += 1
                weight_for[team] += 4
                if lp and lp[1] == pid:
                    self.p(team, lp[0])["assists"] += 1
                if sum(ev["score"].values()) == 1:
                    self._alert("milestone", "first_goal", team=team, player=pid)
                if me["goals"] == 2:
                    self._alert("milestone", "brace", team=team, player=pid)
                elif me["goals"] == 3:
                    self._alert("milestone", "hat_trick", team=team, player=pid)
            self.last_pass_to[team] = None

        if t in ON_BALL:
            self._milestone_count(team, pid, "touches", (25, 50))
        if is_key_event(ev):
            self.key_moments.append(self._moment(ev))
        for side, w in weight_for.items():
            if w:
                self.momentum_window.append((side, w))
        self.momentum_log.append((self.half, self.momentum()))
        self._flow(ev, holder)
        self._spells(ev, holder)

    def _moment(self, ev):
        return {"seq": ev["seq"], "clock": ev["clock"], "team": ev["team"], "player": ev["player"],
                "type": ev["event_type"], "outcome": ev["outcome"], "card": ev["card"],
                "xg": ev["metrics"]["xg"], "player_off": ev["player_off"], "opponent": ev["opponent"],
                "set_piece": ev.get("set_piece"), "restart": ev.get("restart"), "tags": ev.get("tags") or [],
                "var": ev.get("var")}

    def _milestone_count(self, team, pid, stat, thresholds):
        p = self.p(team, pid)
        for n in thresholds:
            if p[stat] == n and self._once(f"{stat}{team}{pid}{n}"):
                self._alert("milestone", stat, team=team, player=pid, value=n)

    def _speed(self, team, pid, kmh):
        p = self.p(team, pid)
        p["top_speed"] = max(p["top_speed"], kmh)
        if kmh >= SPEED_ALERT_KMH:
            self._alert("speed", "speed", team=team, player=pid, value=kmh)
        if kmh >= 30 and kmh > self.match_top_speed + 0.2:
            if self.match_top_speed:
                self._alert("milestone", "top_speed", team=team, player=pid, value=kmh)
            self.match_top_speed = kmh

    def _distance(self, positions, dt):
        prev = self.prev_positions or {}
        for team, ps in positions.items():
            for pid, (x, y) in ps.items():
                p = self.p(team, pid)
                before = p["distance_m"]
                moved = 0.0
                if pid in prev.get(team, {}):
                    px, py = prev[team][pid]
                    moved = metres(x - px, y - py)
                p["distance_m"] = before + moved + dt * JOG_M_PER_MIN.get(p["pos"], JOG_DEFAULT)
                for km in DISTANCE_ALERTS_KM:
                    if before < km * 1000 <= p["distance_m"] and p["pos"] != "GK":
                        self._alert("distance", "distance", team=team, player=pid, value=km)
        self.prev_positions = positions

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
                # average positions are stored as if the home side always attacked right
                hx, hy = attack_frame(self.home, self.right_team, x, y)
                acc = self.avg_pos.setdefault(key, [0.0, 0.0, 0])
                acc[0] += hx; acc[1] += hy; acc[2] += 1
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

    # ---- game flow: control vs chaos, pressure shifts, tempo ----------
    def _flow(self, ev, holder):
        m = ev["metrics"]
        self.flow_window.append((holder, bool(ev.get("possession_change"))))
        if ev["event_type"] in ON_BALL:
            self.press_under[holder].append(m["pressure_index"] or 0)
            self.action_minutes.append(self.minute)
            self.total_actions += 1
        while self.action_minutes and self.action_minutes[0] < self.minute - 6:
            self.action_minutes.popleft()

        f = self.flow()
        new_state = (f["state"], f["state_team"])
        if new_state != (self.state, self.state_team) and f["state"] != "BALANCED" \
                and self.n - self.last_flow_alert >= 12:
            self.last_flow_alert = self.n
            if f["state"] == "CHAOS":
                self._alert("flow", "chaos", value=f["turnover_rate"])
            else:
                self._alert("flow", "control", team=f["state_team"], value=f["control_share"])
        self.state, self.state_team = new_state
        for t in self.teams:
            self.press_hist[t].append(f["press"][t])
            hist = self.press_hist[t]
            if len(hist) > 12 and self.n - self.last_press_alert[t] >= 15:
                before = hist[-11]
                if f["press"][t] - before >= 15 and f["press"][t] >= 45:
                    self.last_press_alert[t] = self.n
                    self._alert("flow", "press_up", team=t, value=f["press"][t], value2=before)
        self.flow_log.append((self.minute, f["state"], f["state_team"]))

    def flow(self):
        w = list(self.flow_window)
        changes = sum(1 for _, c in w if c)
        rate = changes / len(w) if w else 0.0
        share_home = sum(1 for h, _ in w if h == self.home) / len(w) if w else 0.5
        leader = self.home if share_home >= 0.5 else self.away
        share = max(share_home, 1 - share_home)
        state, state_team = "BALANCED", None
        if len(w) >= 8:
            if rate >= 0.38:
                state = "CHAOS"
            elif rate <= 0.2 and share >= 0.6:
                state, state_team = "CONTROL", leader
        press = {}
        for t in self.teams:
            under = self.press_under[self.other(t)]
            press[t] = round(sum(under) / len(under)) if under else 0
        recent_rate = len(self.action_minutes) / min(6.0, max(self.minute, 1.0))
        avg_rate = self.total_actions / max(self.minute, 1.0)
        ratio = recent_rate / avg_rate if avg_rate else 1.0
        tempo = "HIGH" if ratio >= 1.2 else "SLOW" if ratio <= 0.8 else "STEADY"
        direct = {t: (round(100 * sum(d) / len(d)) if d else 0) for t, d in self.direct.items()}
        return {"state": state, "state_team": state_team, "turnover_rate": round(100 * rate),
                "control_share": round(100 * share), "press": press, "tempo": tempo,
                "tempo_ratio": round(ratio, 2), "directness": direct}

    def _spells(self, ev, holder):
        """Track the current possession spell, the raw material of key-event stories."""
        compact = {k: ev.get(k) for k in ("seq", "clock", "team", "player", "event_type", "outcome",
                                          "receiver", "opponent", "impact_reasons", "set_piece", "body_part", "tags")}
        if not ev.get("possession_change"):
            if self.spell_team != holder:
                self.spell, self.spell_team, self.spell_alerted = [], holder, False
            self.spell.append(compact)
            length = sum(1 for e in self.spell if e["event_type"] in ON_BALL and e["team"] == holder)
            if length >= 7 and length > self.max_spell[holder]:
                self.max_spell[holder] = length
                if not self.spell_alerted and self._once(f"spell{holder}{length // 3}"):
                    self.spell_alerted = True
                    self._alert("milestone", "spell", team=holder, value=length)
            return
        # possession changed: a won ball starts the new spell, anything else starts it empty
        winner = self.other(holder)
        won = ev["event_type"] == "TACKLE" or (ev["event_type"] == "PASS" and ev["outcome"] == "INTERCEPTED")
        self.spell, self.spell_team, self.spell_alerted = ([compact] if won else []), winner, False

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
            "on_target": [self.t_on_target[self.home], self.t_on_target[self.away]],
            "momentum": self.momentum(),
            "possession": self.possession(),
            "flow": self.flow(),
            "right_team": self.right_team,
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
             + 0.6 * p["xg"] + 0.3 * p["saves"] - 0.1 * p["fouls"] - 0.3 * p["yellow"] - 1.5 * p["red"]
             + 0.4 * p["xa"] + 0.05 * p["aerials_won"] + 0.06 * p["clearances"] + 0.12 * p["blocks"]
             + 0.03 * p["progressive_passes"] - 0.15 * p["big_chances_missed"] - 0.6 * p["own_goals"])
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
            "avg_pass_difficulty": round(self.t_diff_sum[team] / self.t_diff_n[team]) if self.t_diff_n[team] else 0,
            "top_ball_speed": self.t_top_ball[team],
            "tackles_won": sum(p["tackles_won"] for p in ps),
            "interceptions": sum(p["interceptions"] for p in ps),
            "fouls": sum(p["fouls"] for p in ps),
            **self.t_set[team], "offsides": self.t_offsides[team],
            **{k: sum(p[k] for p in ps) for k in ("crosses", "crosses_completed", "long_balls", "long_balls_completed",
                                                  "progressive_passes", "aerials_won", "clearances", "blocks",
                                                  "big_chances_missed")},
            "xa": round(sum(p["xa"] for p in ps), 2),
            "woodwork": self.t_woodwork[team], "goals_disallowed": self.t_disallowed[team],
            "own_goals_for": self.t_own_goals_for[team],
            "field_tilt": round(100 * self.final_third[team] / max(1, sum(self.final_third.values()))),
            "yellow": sum(p["yellow"] for p in ps), "red": sum(p["red"] for p in ps),
            "saves": sum(p["saves"] for p in ps),
            "distance_km": round(sum(p["distance_m"] for p in ps) / 1000, 1),
            "top_speed": max(p["top_speed"] for p in ps),
            "press_wins": self.t_press_wins[team],
        }

    def player_rows(self, team):
        rows = []
        for (t, pid), p in self.players.items():
            if t != team:
                continue
            row = {k: p[k] for k in ("id", "name", "num", "pos", "starter", "goals", "assists",
                                     "shots", "on_target", "xg", "passes", "passes_completed",
                                     "key_passes", "line_breaks", "dribbles", "dribbles_won",
                                     "tackles", "tackles_won", "interceptions", "fouls", "fouls_won",
                                     "offsides", "xa", "crosses", "crosses_completed", "long_balls",
                                     "long_balls_completed", "progressive_passes", "aerials", "aerials_won",
                                     "clearances", "blocks", "big_chances_missed", "own_goals", "yellow",
                                     "red", "saves", "touches", "sprints", "top_speed")}
            row["distance_km"] = round(p["distance_m"] / 1000, 1)
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
            "directness": self.flow()["directness"][team],
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
                "tackles_won": p["tackles_won"], "rating": self.rating(p), "saves": p["saves"],
                "distance_km": round(p["distance_m"] / 1000, 1), "top_speed": p["top_speed"],
                "minutes": self.minutes(p), "yellow": p["yellow"]}

    def report(self, ev):
        """Structured half-time / full-time report."""
        teams = {t: self.team_stats(t) for t in self.teams}
        rows = [(t, r) for t in self.teams for r in self.player_rows(t) if r["minutes"] >= 20]
        rows.sort(key=lambda tr: tr[1]["rating"] or 0, reverse=True)
        best = None
        if rows:
            t, r = rows[0]
            best = {"team": t, "id": r["id"], "name": r["name"], "rating": r["rating"], "goals": r["goals"],
                    "assists": r["assists"], "shots": r["shots"], "tackles_won": r["tackles_won"],
                    "interceptions": r["interceptions"], "passes_completed": r["passes_completed"],
                    "touches": r["touches"]}
        top = {t: [{"id": r["id"], "name": r["name"], "rating": r["rating"]} for tt, r in rows if tt == t][:3]
               for t in self.teams}
        states = [(s, st) for _, s, st in self.flow_log]
        n = len(states) or 1
        control = {t: round(100 * sum(1 for s, st in states if s == "CONTROL" and st == t) / n) for t in self.teams}
        chaos = round(100 * sum(1 for s, _ in states if s == "CHAOS") / n)
        # momentum of the half just finished
        half = [mo for h, mo in self.momentum_log if h == (1 if ev["event_type"] == "HALF_TIME" else 2)]
        moments = [k for k in self.key_moments if k["type"] != "SUBSTITUTION"][-8:]
        return {
            "kind": ev["event_type"], "clock": ev["clock"], "score": ev["score"],
            "home": self.home, "away": self.away,
            "teams": {t: {k: teams[t][k] for k in ("xg", "shots", "on_target", "possession", "pass_pct",
                                                    "big_chances", "tackles_won", "press_wins", "distance_km",
                                                    "corners", "free_kicks", "fouls", "offsides", "yellow", "red",
                                                    "woodwork", "big_chances_missed", "field_tilt")}
                      for t in self.teams},
            "best_player": best, "top_performers": top,
            "control": control, "chaos_pct": chaos,
            "momentum_avg": round(sum(half) / len(half)) if half else 0,
            "key_moments": moments,
        }
