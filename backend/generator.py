"""Stage 1a - synthetic match telemetry for SecondTouch.

A possession-based 11-a-side simulation. Every call to next_event() advances
the match by one on-ball action and returns the event plus where all 22
players are standing when it finishes, so the pitch shows the same match the
numbers describe.

Coordinates are percentages of the pitch (0-100). Arsenal (home) attacks
towards x=100, Man City towards x=0. Distances are converted to metres
(105 x 68) before any maths.
"""
import math
import random
import time

from analytics import (PITCH_L, PITCH_W, attack_frame, impact_moment, metres,
                       pass_difficulty, pressure_from_distance, xg_model)

HOME, AWAY = "Arsenal", "ManCity"

# id -> (name, shirt number, role, slot u, slot v). Slots are in the team's
# attack frame: u=100 is the goal it attacks, v<50 is its left flank.
STARTERS = {
    HOME: [
        ("Raya", "David Raya", 22, "GK", 5, 50),
        ("White", "Ben White", 4, "RB", 26, 84),
        ("Saliba", "William Saliba", 2, "CB", 20, 62),
        ("Gabriel", "Gabriel Magalhães", 6, "CB", 20, 38),
        ("Timber", "Jurriën Timber", 12, "LB", 26, 16),
        ("Rice", "Declan Rice", 41, "CDM", 38, 50),
        ("Ødegaard", "Martin Ødegaard", 8, "CAM", 55, 64),
        ("Merino", "Mikel Merino", 23, "CM", 52, 36),
        ("Saka", "Bukayo Saka", 7, "RW", 72, 84),
        ("Havertz", "Kai Havertz", 29, "ST", 77, 50),
        ("Martinelli", "Gabriel Martinelli", 11, "LW", 72, 16),
    ],
    AWAY: [
        ("Ederson", "Ederson", 31, "GK", 5, 50),
        ("Walker", "Kyle Walker", 2, "RB", 26, 84),
        ("Dias", "Rúben Dias", 3, "CB", 20, 62),
        ("Akanji", "Manuel Akanji", 25, "CB", 20, 38),
        ("Gvardiol", "Joško Gvardiol", 24, "LB", 26, 16),
        ("Rodri", "Rodri", 16, "CDM", 38, 50),
        ("De Bruyne", "Kevin De Bruyne", 17, "CM", 54, 62),
        ("Foden", "Phil Foden", 47, "CM", 54, 38),
        ("Bernardo", "Bernardo Silva", 20, "RW", 68, 82),
        ("Haaland", "Erling Haaland", 9, "ST", 79, 50),
        ("Doku", "Jérémy Doku", 11, "LW", 68, 18),
    ],
}
# (id, name, number, role, replaces)
BENCH = {
    HOME: [("Trossard", "Leandro Trossard", 19, "LW", "Martinelli"),
           ("Jorginho", "Jorginho", 20, "CDM", "Merino"),
           ("Kiwior", "Jakub Kiwior", 15, "CB", "Gabriel")],
    AWAY: [("Grealish", "Jack Grealish", 10, "LW", "Doku"),
           ("Kovačić", "Mateo Kovačić", 8, "CM", "De Bruyne"),
           ("Stones", "John Stones", 5, "CB", "Akanji")],
}
FORMATIONS = {HOME: "4-3-3", AWAY: "4-1-4-1"}

SQUADS = {
    team: {
        **{pid: {"name": n, "num": num, "pos": role, "starter": True} for pid, n, num, role, _, _ in STARTERS[team]},
        **{pid: {"name": n, "num": num, "pos": role, "starter": False} for pid, n, num, role, _ in BENCH[team]},
    }
    for team in (HOME, AWAY)
}
SLOTS = {team: {pid: (role, u, v) for pid, _, _, role, u, v in STARTERS[team]} for team in (HOME, AWAY)}

SHOT_W = {"ST": 55, "LW": 32, "RW": 32, "CAM": 26, "CM": 13, "CDM": 6, "RB": 3, "LB": 3, "CB": 3}
DRIBBLE_W = {"LW": 34, "RW": 34, "CAM": 22, "ST": 16, "CM": 12, "RB": 12, "LB": 12, "CDM": 7, "CB": 4}


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


class MatchSim:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.minute = 0.0
        self.seq = 0
        self.score = {HOME: 0, AWAY: 0}
        self.half_time_done = False
        self.full_time = False
        # pid -> (role, slot u, slot v); a substitute inherits the slot
        self.slots = {t: dict(SLOTS[t]) for t in (HOME, AWAY)}
        self.yellows = {}
        self.jitter = {}
        self.subs = self._plan_subs()
        self.positions = self._kickoff_positions(HOME)  # also sets ball, possession, carrier

    # ---- geometry ------------------------------------------------------
    def frame(self, team, x, y):
        return attack_frame(team, HOME, x, y)

    def absolute(self, team, u, v):
        return attack_frame(team, HOME, u, v)  # the mirror is its own inverse

    def other(self, team):
        return AWAY if team == HOME else HOME

    def dist_m(self, a, b):
        return metres(a[0] - b[0], a[1] - b[1])

    def nearest(self, team, point, exclude=()):
        """Nearest player of `team` to an absolute point -> (pid, metres)."""
        best = (None, 1e9)
        for pid, pos in self.positions[team].items():
            if pid in exclude:
                continue
            d = self.dist_m(pos, point)
            if d < best[1]:
                best = (pid, d)
        return best

    def gk(self, team):
        return next(pid for pid, s in self.slots[team].items() if s[0] == "GK")

    # ---- shapes --------------------------------------------------------
    def _shape(self, team, in_possession):
        """Where each player of `team` stands for the current ball position."""
        bu, bv = self.frame(team, *self.ball)
        out = {}
        for pid, (role, su, sv) in self.slots[team].items():
            j = self.jitter.setdefault((team, pid), [0.0, 0.0])
            if role == "GK":
                u = 4 + bu * (0.14 if in_possession else 0.08)
                v = 50 + (bv - 50) * 0.2
            elif in_possession:
                u = su * 0.6 + bu * 0.45 + 6
                v = 50 + (sv - 50) * 1.1 + (bv - 50) * 0.25
            else:
                u = su * 0.55 + bu * 0.42 - 2
                v = 50 + (sv - 50) * 0.8 + (bv - 50) * 0.45
            out[pid] = [clamp(u + j[0], 2, 97), clamp(v + j[1], 3, 97)]
        return out

    def _drift(self):
        for j in self.jitter.values():
            j[0] = clamp(j[0] + self.rng.uniform(-1.2, 1.2), -4, 4)
            j[1] = clamp(j[1] + self.rng.uniform(-1.2, 1.2), -4, 4)

    def _reposition(self, receiver=None):
        """Recompute both teams around the ball after an action."""
        self._drift()
        att, dfn = self.possession, self.other(self.possession)
        a = self._shape(att, True)
        d = self._shape(dfn, False)
        # offside line: attackers stay level with the second-last defender
        def_us = sorted((100 - u for pid, (u, _) in d.items() if self.slots[dfn][pid][0] != "GK"), reverse=True)
        line = max(def_us[0] if def_us else 50, self.frame(att, *self.ball)[0], 50)
        for pid, uv in a.items():
            if self.slots[att][pid][0] != "GK":
                uv[0] = min(uv[0], line + 1)
        pos = {
            att: {pid: self.absolute(att, *uv) for pid, uv in a.items()},
            dfn: {pid: self.absolute(dfn, *uv) for pid, uv in d.items()},
        }
        pos[att][receiver or self.carrier] = self.ball
        self.positions = pos
        self._press(dfn)
        self.positions = {t: {pid: (round(x, 1), round(y, 1)) for pid, (x, y) in ps.items()} for t, ps in self.positions.items()}

    def _press(self, dfn):
        """Move the nearest one or two defenders onto the ball, between it and their goal."""
        bu = self.frame(self.possession, *self.ball)[0]
        mean = max(3.0, 10 - bu / 12)  # closer to goal, tighter marking
        goal = (0.0, 50.0) if dfn == HOME else (100.0, 50.0)
        gx, gy = goal[0] - self.ball[0], goal[1] - self.ball[1]
        norm = math.hypot(gx * PITCH_L / 100, gy * PITCH_W / 100) or 1
        placed = []
        for k in range(2):
            pid, _ = self.nearest(dfn, self.ball, exclude=placed + [self.gk(dfn)])
            if pid is None:
                break
            d = self.rng.expovariate(1 / mean) + 1.8 if k == 0 else self.rng.uniform(6, 12)
            ang = self.rng.uniform(-0.7, 0.7) if k == 0 else self.rng.choice([-1, 1]) * self.rng.uniform(0.9, 1.6)
            dx_m, dy_m = gx * PITCH_L / 100 / norm, gy * PITCH_W / 100 / norm
            rx = dx_m * math.cos(ang) - dy_m * math.sin(ang)
            ry = dx_m * math.sin(ang) + dy_m * math.cos(ang)
            x = clamp(self.ball[0] + rx * d * 100 / PITCH_L, 1, 99)
            y = clamp(self.ball[1] + ry * d * 100 / PITCH_W, 1, 99)
            self.positions[dfn][pid] = (x, y)
            placed.append(pid)

    def _kickoff_positions(self, kicking):
        self.ball = (50.0, 50.0)
        self.possession = kicking
        self.carrier = next((pid for pid, s in self.slots[kicking].items() if s[0] == "ST"), None) \
            or next(pid for pid, s in self.slots[kicking].items() if s[0] != "GK")
        pos = {}
        for team in (HOME, AWAY):
            ps = {}
            for pid, (role, su, sv) in self.slots[team].items():
                u = 4 if role == "GK" else min(48, su * 0.62)
                ps[pid] = self.absolute(team, u, sv)
            pos[team] = ps
        pos[kicking][self.carrier] = self.ball
        return {t: {pid: (round(x, 1), round(y, 1)) for pid, (x, y) in ps.items()} for t, ps in pos.items()}

    # ---- substitutions -------------------------------------------------
    def _plan_subs(self):
        plan = []
        for team in (HOME, AWAY):
            for on_id, _, _, _, off_id in BENCH[team]:
                plan.append([self.rng.uniform(58, 82), team, on_id, off_id])
        return sorted(plan)

    def _due_sub(self):
        for i, (minute, team, on_id, off_id) in enumerate(self.subs):
            if minute > self.minute:
                break
            if off_id not in self.slots[team] or (team == self.possession and off_id == self.carrier):
                continue
            return self.subs.pop(i)
        return None

    # ---- the step ------------------------------------------------------
    def next_event(self, focus_team=None, focus_player=None, focus_bias=0.0):
        """Advance one action. `focus_bias` nudges passes towards the Player Cam target."""
        if self.full_time:
            return None
        if self.minute >= 90:
            self.full_time = True
            return self._status_event("FULL_TIME", 90.0)
        if self.minute >= 45 and not self.half_time_done:
            self.half_time_done = True
            self.minute = 45.0
            self.positions = self._kickoff_positions(AWAY)
            return self._status_event("HALF_TIME", 45.0)
        sub = self._due_sub()
        if sub:
            return self._substitution(*sub[1:])

        self.minute += self.rng.uniform(0.3, 0.8)
        self.seq += 1
        team, pid = self.possession, self.carrier
        role = self.slots[team][pid][0]
        u, v = self.frame(team, *self.ball)
        opp = self.other(team)
        presser, near_m = self.nearest(opp, self.ball)
        p_idx, pressure = pressure_from_distance(near_m)

        goal_m = metres(100 - u, 50 - v)
        w_shot = SHOT_W.get(role, 0) * max(0.0, (30 - goal_m) / 6) ** 2.5
        w_drib = 0 if role == "GK" else DRIBBLE_W.get(role, 8)
        etype = self.rng.choices(["PASS", "DRIBBLE", "SHOT"], weights=[60, w_drib, w_shot])[0]

        base = dict(team=team, player=pid, u=u, v=v, p_idx=p_idx, pressure=pressure, near_m=near_m)
        if etype == "SHOT":
            ev = self._shot(base)
        elif etype == "DRIBBLE":
            ev = self._dribble(base, presser)
        else:
            ev = self._pass(base, focus_team, focus_player, focus_bias)
        return self._finish(ev)

    def _metrics(self, b, **kw):
        m = {"xg": None, "pass_difficulty": None, "pressure": b["pressure"], "pressure_index": b["p_idx"],
             "nearest_defender_m": round(b["near_m"], 1), "sprint_speed_kmh": None, "ball_speed_kmh": None,
             "forward_gain_m": None, "players_bypassed": None}
        m.update(kw)
        return m

    def _pass(self, b, focus_team, focus_player, focus_bias):
        team, pid, opp = b["team"], b["player"], self.other(b["team"])
        start = self.ball
        options = []
        for mate, pos in self.positions[team].items():
            if mate == pid:
                continue
            mu, mv = self.frame(team, *pos)
            gain = (mu - b["u"]) * PITCH_L / 100
            dist = self.dist_m(start, pos)
            if dist < 4:
                continue
            space = self.nearest(opp, pos)[1]
            w = math.exp(-((dist - 18) / 16) ** 2) * (1 + max(-0.6, gain / 20)) * (0.4 + min(space, 8) / 8)
            if self.slots[team][mate][0] == "GK":
                w *= 0.15
            if team == focus_team and mate == focus_player:
                w *= 1 + focus_bias * 4
            options.append((max(w, 0.01), mate, pos, gain, dist, space))
        _, rec, target, _, _, space = self.rng.choices(options, weights=[o[0] for o in options])[0]
        tu, tv = self.frame(team, *target)
        if self.slots[team][rec][0] in ("ST", "LW", "RW", "CAM") and tu >= 62 and self.rng.random() < 0.5:
            # through ball: played into space for the runner to attack, behind the line
            tu, tv = min(94, tu + self.rng.uniform(8, 20)), tv + (50 - tv) * self.rng.uniform(0.3, 0.6)
            space = max(space, self.rng.uniform(2, 6))
        end = self.absolute(team, clamp(tu + self.rng.uniform(-1.5, 1.5)), clamp(tv + self.rng.uniform(-2, 2)))
        su, sv = self.frame(team, *start)
        eu, ev_ = self.frame(team, *end)
        gain = (eu - su) * PITCH_L / 100
        length = self.dist_m(start, end)
        angle = math.atan2((ev_ - sv) * PITCH_W / 100, (eu - su) * PITCH_L / 100)
        diff = pass_difficulty(length, angle, b["p_idx"], space)
        bypassed = sum(1 for opos in self.positions[opp].values() if su < self.frame(team, *opos)[0] < eu)
        speed = round(clamp(38 + length * 1.3 + self.rng.uniform(-6, 8), 25, 110), 1)
        ok = self.rng.random() > (diff / 100) ** 2.2 * 0.7
        metrics = self._metrics(b, pass_difficulty=diff, ball_speed_kmh=speed,
                                forward_gain_m=round(gain, 1), players_bypassed=bypassed)
        if ok:
            self.ball, self.carrier = end, rec
            return self._event(b, "PASS", "COMPLETE", start, end, length, metrics, receiver=rec)
        # intercepted somewhere along the line by the defender closest to it
        f = self.rng.uniform(0.45, 0.95)
        cut = (start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f)
        thief, _ = self.nearest(opp, cut)
        self.ball, self.possession, self.carrier = cut, opp, thief
        return self._event(b, "PASS", "INTERCEPTED", start, cut, self.dist_m(start, cut), metrics, opponent=thief)

    def _dribble(self, b, presser):
        team, pid, opp = b["team"], b["player"], self.other(b["team"])
        role = self.slots[team][pid][0]
        start = self.ball
        p_win = 0.86 - b["p_idx"] / 100 * 0.45 + (0.08 if role in ("LW", "RW") else 0)
        speed = round(self.rng.uniform(24.0, 34.0), 1)
        if self.rng.random() < p_win:
            du = self.rng.uniform(3, 13)
            dv = self.rng.uniform(-7, 7) + (50 - b["v"]) * (0.25 if b["u"] > 65 else 0.08)  # cut inside near goal
            end = self.absolute(team, clamp(b["u"] + du, 2, 97), clamp(b["v"] + dv, 3, 97))
            self.ball = end
            m = self._metrics(b, sprint_speed_kmh=speed, ball_speed_kmh=speed)
            return self._event(b, "DRIBBLE", "SUCCESS", start, end, self.dist_m(start, end), m)
        # the nearest defender steps in: the event belongs to the tackler
        foul = self.rng.random() < 0.32
        end = (clamp(start[0] + self.rng.uniform(-2, 2)), clamp(start[1] + self.rng.uniform(-2, 2)))
        card = None
        if foul and self.slots[opp][presser][0] != "GK" and self.rng.random() < 0.5:
            self.yellows[(opp, presser)] = self.yellows.get((opp, presser), 0) + 1
            card = "RED" if self.yellows[(opp, presser)] >= 2 or self.rng.random() < 0.04 else "YELLOW"
        m = self._metrics(b)
        tackler = dict(b, team=opp, player=presser)
        if foul:
            self.ball = start  # free kick, same team keeps it
            ev = self._event(tackler, "TACKLE", "FOUL", start, start, 0.0, m, opponent=pid, card=card)
            if card == "RED":
                del self.slots[opp][presser]
                self.positions[opp].pop(presser, None)
            return ev
        self.ball, self.possession, self.carrier = end, opp, presser
        return self._event(tackler, "TACKLE", "WON", start, end, self.dist_m(start, end), m, opponent=pid)

    def _shot(self, b):
        team, opp = b["team"], self.other(b["team"])
        start = self.ball
        xg, dist = xg_model(b["u"], b["v"], b["p_idx"])
        keeper = self.gk(opp)
        goal_x = 100.0 if team == HOME else 0.0
        mouth = 3.66 / PITCH_W * 100
        if self.rng.random() < xg:
            outcome = "GOAL"
        else:
            p_block = 0.1 + b["p_idx"] / 100 * 0.3
            r = self.rng.random()
            outcome = "BLOCKED" if r < p_block else "SAVED" if r < p_block + (1 - p_block) * 0.45 else "MISS"
        opponent = None
        if outcome in ("GOAL", "SAVED"):
            end = (goal_x, 50 + self.rng.uniform(-mouth, mouth) * 0.95)
            opponent = keeper if outcome == "SAVED" else None
        elif outcome == "MISS":
            end = (goal_x, 50 + self.rng.choice([-1, 1]) * self.rng.uniform(mouth + 1, mouth + 9))
        else:
            f = self.rng.uniform(0.15, 0.35)
            end = (start[0] + (goal_x - start[0]) * f, start[1] + (50 - start[1]) * f)
            opponent = self.nearest(opp, end, exclude=[keeper])[0]
        speed = round(clamp(self.rng.uniform(78, 118) - dist * 0.4, 50, 125), 1)
        m = self._metrics(b, xg=xg, ball_speed_kmh=speed)
        ev = self._event(b, "SHOT", outcome, start, end, dist, m, opponent=opponent)
        if outcome == "GOAL":
            self.score[team] += 1
            ev["score"] = {"home": self.score[HOME], "away": self.score[AWAY]}
            ev["_kickoff"] = opp
        elif outcome in ("SAVED", "MISS"):
            self.possession, self.carrier = opp, keeper
            self.ball = self.absolute(opp, 5 if outcome == "SAVED" else 6, 50)
        else:
            winner = opp if self.rng.random() < 0.55 else team
            self.possession = winner
            self.carrier = opponent if winner == opp else self.nearest(team, end)[0]
            self.ball = end
        return ev

    def _event(self, b, etype, outcome, start, end, length, metrics, **extra):
        e = {
            "seq": self.seq, "minute": round(self.minute, 2), "clock": f"{int(self.minute)}'",
            "team": b["team"], "player": b["player"], "event_type": etype, "outcome": outcome,
            "opponent": None, "receiver": None, "player_off": None, "card": None,
            "length_m": round(length, 1),
            "location": {"start_x": round(start[0], 1), "start_y": round(start[1], 1),
                         "end_x": round(end[0], 1), "end_y": round(end[1], 1)},
            "metrics": metrics,
            "score": {"home": self.score[HOME], "away": self.score[AWAY]},
        }
        e.update(extra)
        return e

    def _finish(self, ev):
        kick = ev.pop("_kickoff", None)
        if kick:
            self.positions = self._kickoff_positions(kick)
        else:
            self._reposition(receiver=ev["receiver"])
        ev["is_impact_moment"], ev["impact_reasons"] = impact_moment(ev)
        ev["generated_at"] = time.time() * 1000
        return ev

    def _status_event(self, etype, minute):
        self.seq += 1
        e = {
            "seq": self.seq, "minute": minute, "clock": "HT" if etype == "HALF_TIME" else "FT",
            "team": None, "player": None, "event_type": etype, "outcome": None,
            "opponent": None, "receiver": None, "player_off": None, "card": None, "length_m": None,
            "location": {"start_x": 50.0, "start_y": 50.0, "end_x": 50.0, "end_y": 50.0},
            "metrics": {k: None for k in ("xg", "pass_difficulty", "pressure", "pressure_index",
                                           "nearest_defender_m", "sprint_speed_kmh", "ball_speed_kmh",
                                           "forward_gain_m", "players_bypassed")},
            "score": {"home": self.score[HOME], "away": self.score[AWAY]},
            "is_impact_moment": False, "impact_reasons": [], "generated_at": time.time() * 1000,
        }
        return e

    def _substitution(self, team, on_id, off_id):
        self.slots[team][on_id] = self.slots[team].pop(off_id)
        self.positions[team][on_id] = self.positions[team].pop(off_id)
        e = self._status_event("SUBSTITUTION", round(self.minute, 2))
        bx, by = round(self.ball[0], 1), round(self.ball[1], 1)
        e.update(team=team, player=on_id, player_off=off_id, clock=f"{int(self.minute)}'",
                 location={"start_x": bx, "start_y": by, "end_x": bx, "end_y": by})
        return e
