"""Stage 1a - synthetic match telemetry for SecondTouch.

A possession-based 11-a-side simulation. Every call to next_event() advances
the match by one on-ball action and returns the event plus where all 22
players are standing when it finishes, so the pitch shows the same match the
numbers describe.

Coordinates are percentages of the pitch (0-100). The home side attacks
towards x=100 in the first half, the away side towards x=0. Distances are
converted to metres (105 x 68) before any maths.

Clubs, squads, formations, officials and match details come from the
fictional reference dataset in data/reference/match_reference_data.json.
"""
import json
import math
import random
import time
from pathlib import Path

from analytics import (PITCH_L, PITCH_W, attack_frame, impact_moment, metres,
                       pass_difficulty, pressure_from_distance, xg_model)

REFERENCE = Path(__file__).resolve().parent.parent / "data" / "reference" / "match_reference_data.json"
REF = json.loads(REFERENCE.read_text(encoding="utf-8"))
MATCH = REF["match"]
CLUBS = {c["club_id"]: c for c in REF["clubs"]}
HOME_CLUB, AWAY_CLUB = CLUBS[MATCH["home_club_id"]], CLUBS[MATCH["away_club_id"]]
HOME, AWAY = HOME_CLUB["short_name"], AWAY_CLUB["short_name"]
CLUB = {HOME: HOME_CLUB, AWAY: AWAY_CLUB}
LINEUPS = {HOME: MATCH["lineups"]["home"], AWAY: MATCH["lineups"]["away"]}

# Slot (u, v) for each position in a formation, in the team's attack frame:
# u=100 is the goal it attacks, v<50 is its left flank. Repeated positions fill right to left.
FORMATION_SLOTS = {
    "4-3-3": {"GK": [(5, 50)], "RB": [(26, 84)], "CB": [(20, 62), (20, 38)], "LB": [(26, 16)],
              "CDM": [(38, 50)], "CAM": [(55, 64)], "CM": [(52, 36)],
              "RW": [(72, 84)], "ST": [(77, 50)], "LW": [(72, 16)]},
    "4-2-3-1": {"GK": [(5, 50)], "RB": [(26, 84)], "CB": [(20, 62), (20, 38)], "LB": [(26, 16)],
                "CDM": [(40, 62), (40, 38)], "CAM": [(60, 50)],
                "RW": [(66, 84)], "ST": [(79, 50)], "LW": [(66, 16)]},
}
# Substitutions the simulation makes, by player id (display name): (on, off)
SUB_PLAN = {
    HOME: [("Morisaki", "Thornquist"), ("Krüllner", "Tolland"), ("Pryddercombe", "Adewolu-Hart")],
    AWAY: [("Farelhas", "Amponsah-Brent"), ("Tounkaré", "Villaruela"), ("Benhalima", "Strachley")],
}


def _squad(team):
    """Starters (id, name, number, role, u, v) in lineup order, and the bench (id, name, number, role)."""
    by_id = {p["player_id"]: p for p in REF["players"]}
    slots = {pos: list(s) for pos, s in FORMATION_SLOTS[LINEUPS[team]["formation"]].items()}
    starters = []
    for player_id in LINEUPS[team]["starting_xi"]:
        p = by_id[player_id]
        u, v = slots[p["detailed_position"]].pop(0)
        starters.append((p["display_name"], p["name"], p["shirt_number"], p["detailed_position"], u, v))
    bench = [(by_id[i]["display_name"], by_id[i]["name"], by_id[i]["shirt_number"], by_id[i]["detailed_position"])
             for i in LINEUPS[team]["substitutes"]]
    return starters, bench


STARTERS, BENCH = {}, {}
for _team in (HOME, AWAY):
    STARTERS[_team], BENCH[_team] = _squad(_team)
FORMATIONS = {t: LINEUPS[t]["formation"] for t in (HOME, AWAY)}
COACHES = {t: CLUB[t]["manager"]["name"] for t in (HOME, AWAY)}
# Full reference record per player: attributes (pace, passing, shooting, ...), height, top speed.
PLAYERS = {t: {p["display_name"]: p for p in REF["players"] if p["club_id"] == CLUB[t]["club_id"]}
           for t in (HOME, AWAY)}
# Each player's top speed from the reference data caps their sprints and carries.
TOP_SPEED = {t: {pid: p["physical"]["top_speed_kmh"] for pid, p in PLAYERS[t].items()} for t in (HOME, AWAY)}
_OFFICIALS = {o["official_id"]: o for o in REF["officials"]}
REFEREE = next(_OFFICIALS[i] for i in MATCH["officials"] if _OFFICIALS[i]["role"] == "referee")

# Set pieces. The referee's per-match card rates are spread over the bookable fouls the
# simulation typically produces (about 11 fouls a match; keepers and players already booked
# are rarely carded), so a stricter referee in the reference data books more players.
SET_PIECES = ("FREE_KICK", "CORNER", "THROW_IN", "PENALTY", "GOAL_KICK")
FOULS_PER_MATCH = 9.0
P_YELLOW = REFEREE["avg_yellows_per_match"] / FOULS_PER_MATCH
P_RED = REFEREE["avg_reds_per_match"] / FOULS_PER_MATCH / 3  # most reds come from a second yellow
PENALTY_XG = 0.76
PEN_SPOT_U = 100 - 11 / PITCH_L * 100       # 11 m from goal
BOX_U, BOX_HALF_V = 100 - 16.5 / PITCH_L * 100, 20.16 / PITCH_W * 100
SIX_U, SIX_HALF_V = 5.5 / PITCH_L * 100, 9.16 / PITCH_W * 100

SQUADS = {
    team: {
        **{pid: {"name": n, "num": num, "pos": role, "starter": True} for pid, n, num, role, _, _ in STARTERS[team]},
        **{pid: {"name": n, "num": num, "pos": role, "starter": False} for pid, n, num, role in BENCH[team]},
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
        self.seed = seed
        self.minute = 0.0
        self.right_team = HOME  # who attacks towards x=100; swaps at half-time
        self.seq = 0
        self.score = {HOME: 0, AWAY: 0}
        self.half_time_done = False
        self.full_time = False
        # pid -> (role, slot u, slot v); a substitute inherits the slot
        self.slots = {t: dict(SLOTS[t]) for t in (HOME, AWAY)}
        self.yellows = {}
        self.jitter = {}
        self.restart = None         # set piece awarded and waiting to be taken
        self.force_header = False   # a corner was won in the air: the next action is a header
        self.subs = self._plan_subs()
        self.positions = self._kickoff_positions(HOME)  # also sets ball, possession, carrier
        stadium = next(s for s in REF["stadiums"] if s["stadium_id"] == MATCH["stadium_id"])
        referee = REFEREE["name"]
        w = MATCH["weather"]
        self.metadata = {
            "competition": REF["competition"]["name"], "season": MATCH["season"], "matchday": MATCH["matchday"],
            "venue": f"{stadium['name']}, {stadium['town']}", "capacity": stadium["capacity"],
            "attendance": MATCH["attendance"], "referee": referee,
            "weather": w["condition"].capitalize(), "temperature_c": w["temperature_c"],
            "wind": f"{w['wind_kmh']} km/h {w['wind_direction']}", "pitch": MATCH["pitch_condition"],
            "kickoff_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "home": HOME, "away": AWAY,
            "club_names": {t: CLUB[t]["name"] for t in (HOME, AWAY)},
            "nicknames": {t: CLUB[t]["nickname"] for t in (HOME, AWAY)},
            "league_positions": {t: CLUB[t]["league_position_before_match"] for t in (HOME, AWAY)},
            "coaches": COACHES, "formations": FORMATIONS,
            "lineups": {t: [pid for pid, *_ in STARTERS[t]] for t in (HOME, AWAY)},
            "bench": {t: [pid for pid, *_ in BENCH[t]] for t in (HOME, AWAY)},
            "head_to_head": MATCH["head_to_head"], "storylines": MATCH["storylines"],
            "seed": seed, "synthetic": True,
        }

    # ---- geometry ------------------------------------------------------
    def frame(self, team, x, y):
        return attack_frame(team, self.right_team, x, y)

    def absolute(self, team, u, v):
        return attack_frame(team, self.right_team, u, v)  # the mirror is its own inverse

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

    # ---- player attributes (reference data) ----------------------------
    def skill(self, team, pid, key):
        """An attribute as an adjustment around an average player of 70: about -0.2 to +0.2."""
        return (PLAYERS[team][pid]["attributes"][key] - 70) / 100

    def aerial(self, team, pid):
        p = PLAYERS[team][pid]
        return p["attributes"]["physical"] + (p["height_cm"] - 178) * 1.5

    def outfield(self, team, exclude=()):
        return [pid for pid, s in self.slots[team].items() if s[0] != "GK" and pid not in exclude]

    def best(self, team, rate):
        """The outfield player on the pitch with the highest `rate(pid)`: the set-piece taker."""
        return max(self.outfield(team), key=rate)

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
        if self.restart:
            self._set_piece_shape(att, dfn)
        else:
            self._press(dfn)
        self.positions = {t: {pid: (round(clamp(x), 1), round(clamp(y), 1)) for pid, (x, y) in ps.items()}
                          for t, ps in self.positions.items()}

    def _set_piece_shape(self, att, dfn):
        """Line both teams up for the set piece about to be taken."""
        kind, taker, ball = self.restart, self.carrier, self.ball
        bu, bv = self.frame(att, *ball)
        P = self.positions
        wall = []
        if kind == "PENALTY":
            for team in (att, dfn):
                for pid, xy in P[team].items():
                    u, v = self.frame(att, *xy)
                    if pid != taker and u > BOX_U - 2:
                        P[team][pid] = self.absolute(att, self.rng.uniform(BOX_U - 6, BOX_U - 2), v)
            P[dfn][self.gk(dfn)] = self.absolute(att, 99.5, 50)
            return
        if kind == "CORNER" or (kind == "FREE_KICK" and bu >= 70):
            if self._direct_range(bu, bv):
                # a wall of three or four on the line from the ball to the middle of the goal
                gx, gy = (100 - bu) * PITCH_L / 100, (50 - bv) * PITCH_W / 100
                norm = math.hypot(gx, gy) or 1
                ux, uy = gx / norm, gy / norm
                wall = sorted(self.outfield(dfn), key=lambda q: self.dist_m(P[dfn][q], ball))[:self.rng.choice([3, 4])]
                for k, pid in enumerate(wall):
                    off = (k - (len(wall) - 1) / 2) * 0.8
                    wu = bu + (ux * 9.15 - uy * off) * 100 / PITCH_L
                    wv = bv + (uy * 9.15 + ux * off) * 100 / PITCH_W
                    P[dfn][pid] = self.absolute(att, wu, wv)
            else:
                # bodies in the box: the best in the air attack it, each picked up goal-side
                runners = sorted(self.outfield(att, exclude=[taker]), key=lambda q: -self.aerial(att, q))[:5]
                markers = self.outfield(dfn)
                for pid in runners:
                    u, v = self.rng.uniform(85, 96), self.rng.uniform(34, 66)
                    P[att][pid] = self.absolute(att, u, v)
                    if markers:
                        m = min(markers, key=lambda q: self.dist_m(P[dfn][q], P[att][pid]))
                        markers.remove(m)
                        P[dfn][m] = self.absolute(att, min(99, u + 1.5), v + self.rng.uniform(-2, 2))
                P[dfn][self.gk(dfn)] = self.absolute(att, 99, 50)
        if kind == "THROW_IN":
            return  # no distance rule: markers stay tight
        # everyone else stands 9.15 m from the ball
        for pid, (x, y) in P[dfn].items():
            d = self.dist_m((x, y), ball)
            if pid in wall or d >= 9.15 or self.slots[dfn][pid][0] == "GK":
                continue
            dx, dy = (x - ball[0]) * PITCH_L / 100, (y - ball[1]) * PITCH_W / 100
            if d < 0.5:
                dx, dy = self.rng.uniform(-1, 1), self.rng.uniform(-1, 1)
                d = math.hypot(dx, dy) or 1
            base = math.atan2(dy, dx)
            # straight back from the ball, or swung round it if that would leave the pitch
            for turn in (0, 0.4, -0.4, 0.8, -0.8, 1.2, -1.2, 1.6, -1.6, 2.0, -2.0, 2.6, -2.6, math.pi):
                a = base + turn
                nx = ball[0] + math.cos(a) * 9.5 * 100 / PITCH_L
                ny = ball[1] + math.sin(a) * 9.5 * 100 / PITCH_W
                if 0.5 <= nx <= 99.5 and 0.5 <= ny <= 99.5:
                    break
            P[dfn][pid] = (nx, ny)

    @staticmethod
    def _care(u, v):
        """Defenders risk far fewer fouls inside their own box, where a foul is a penalty."""
        return 0.3 if u >= BOX_U and abs(v - 50) <= BOX_HALF_V else 1.0

    @staticmethod
    def _direct_range(u, v):
        """Close and central enough to shoot at goal from a free kick."""
        return metres(100 - u, 50 - v) <= 30 and abs(v - 50) <= 26

    def _press(self, dfn):
        """Move the nearest one or two defenders onto the ball, between it and their goal."""
        bu = self.frame(self.possession, *self.ball)[0]
        mean = max(3.0, 10 - bu / 12)  # closer to goal, tighter marking
        goal = (0.0, 50.0) if dfn == self.right_team else (100.0, 50.0)
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
            for on_id, off_id in SUB_PLAN[team]:
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
            self.right_team = AWAY  # change ends, as in a real match
            self.restart, self.force_header = None, False
            self.positions = self._kickoff_positions(AWAY)
            return self._status_event("HALF_TIME", 45.0)
        sub = self._due_sub()
        if sub:
            return self._substitution(*sub[1:])

        self.minute += self.rng.uniform(0.3, 0.8)
        self.seq += 1
        self._poss_before = self.possession
        team, pid = self.possession, self.carrier
        role = self.slots[team][pid][0]
        u, v = self.frame(team, *self.ball)
        opp = self.other(team)
        presser, near_m = self.nearest(opp, self.ball)
        p_idx, pressure = pressure_from_distance(near_m)
        base = dict(team=team, player=pid, u=u, v=v, p_idx=p_idx, pressure=pressure, near_m=near_m)

        if self.restart:
            kind, self.restart = self.restart, None
            return self._finish(self._set_piece(kind, base, focus_team, focus_player, focus_bias))
        header, self.force_header = self.force_header, False
        # a player under pressure can be fouled before playing the ball
        if not header and role != "GK" and self.rng.random() < (0.02 + p_idx / 100 * 0.16) * self._care(u, v):
            return self._finish(self._foul(base, presser))

        goal_m = metres(100 - u, 50 - v)
        w_shot = SHOT_W.get(role, 0) * max(0.0, (30 - goal_m) / 6) ** 2.5
        w_drib = 0 if role == "GK" else DRIBBLE_W.get(role, 8)
        etype = "SHOT" if header else self.rng.choices(["PASS", "DRIBBLE", "SHOT"], weights=[60, w_drib, w_shot])[0]

        if etype == "SHOT":
            ev = self._shot(base, body_part="HEAD" if header else "FOOT")
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

    # ---- set pieces ----------------------------------------------------
    def _award(self, kind, team, spot):
        """Stop play: `team` will take a `kind` set piece from `spot`. Returns `kind`."""
        self.restart, self.possession, self.ball = kind, team, spot
        self.carrier = self._taker(kind, team, spot)
        return kind

    def _taker(self, kind, team, spot):
        """Who takes it, picked from the reference attributes of the players on the pitch."""
        u, v = self.frame(team, *spot)
        sk = lambda key: (lambda q: PLAYERS[team][q]["attributes"][key])
        if kind == "GOAL_KICK":
            return self.gk(team)
        if kind == "PENALTY":
            return self.best(team, sk("shooting"))
        if kind == "CORNER" or (kind == "FREE_KICK" and u >= 66):
            if kind == "FREE_KICK" and self._direct_range(u, v):
                a = PLAYERS[team]
                return self.best(team, lambda q: a[q]["attributes"]["shooting"] * 0.6 + a[q]["attributes"]["passing"] * 0.4)
            return self.best(team, sk("passing"))
        if kind == "THROW_IN":
            side = ("RB", "RW") if v > 50 else ("LB", "LW")
            wide = [q for q in self.outfield(team) if self.slots[team][q][0] in side]
            if wide:
                return min(wide, key=lambda q: self.dist_m(self.positions[team][q], spot))
        return self.nearest(team, spot, exclude=[self.gk(team)])[0]

    def _corner_spot(self, team, v):
        return self.absolute(team, 100, 0 if v < 50 else 100)

    def _set_piece(self, kind, b, focus_team, focus_player, focus_bias):
        u, v = b["u"], b["v"]
        if kind == "PENALTY":
            ev = self._shot(b, set_piece=kind)
        elif kind == "FREE_KICK" and self._direct_range(u, v) and self.rng.random() < 0.6:
            ev = self._shot(dict(b, p_idx=60, pressure="HIGH"), set_piece=kind)  # over or round the wall
        elif kind == "CORNER" or (kind == "FREE_KICK" and u >= 70):
            ev = self._delivery(b)
        else:
            ev = self._pass(b, focus_team, focus_player, focus_bias, set_piece=kind)
        ev["set_piece"] = kind
        return ev

    def _delivery(self, b):
        """A corner or wide free kick swung into the box: an attacker wins it in the air or it is cleared."""
        team, pid, opp = b["team"], b["player"], self.other(b["team"])
        start = self.ball
        targets = [q for q in self.outfield(team, exclude=[pid]) if self.frame(team, *self.positions[team][q])[0] >= 80] \
            or self.outfield(team, exclude=[pid])
        rec = self.rng.choices(targets, weights=[max(4.0, self.aerial(team, q) - 50) ** 2 for q in targets])[0]
        tx, ty = self.positions[team][rec]
        end = (clamp(tx + self.rng.uniform(-1, 1)), clamp(ty + self.rng.uniform(-1.5, 1.5)))
        marker, space = self.nearest(opp, end, exclude=[self.gk(opp)])
        su, sv = self.frame(team, *start)
        eu, ev_ = self.frame(team, *end)
        length = self.dist_m(start, end)
        angle = math.atan2((ev_ - sv) * PITCH_W / 100, (eu - su) * PITCH_L / 100)
        diff = pass_difficulty(length, angle, b["p_idx"], space)
        metrics = self._metrics(b, pass_difficulty=diff, ball_speed_kmh=round(self.rng.uniform(55, 85), 1),
                                forward_gain_m=round((eu - su) * PITCH_L / 100, 1), players_bypassed=0)
        win = 0.4 + self.skill(team, pid, "passing") * 0.8 + (self.aerial(team, rec) - self.aerial(opp, marker)) / 200
        if self.rng.random() < win:
            self.ball, self.carrier = end, rec
            self.force_header = self.rng.random() < 0.7
            return self._event(b, "PASS", "COMPLETE", start, end, length, metrics, receiver=rec)
        r = self.rng.random()
        keeper = self.gk(opp)
        if r < 0.3:  # headed behind for another corner
            kind = self._award("CORNER", team, self._corner_spot(team, ev_))
            return self._event(b, "PASS", "INTERCEPTED", start, end, length, metrics, opponent=marker,
                               restart=kind, restart_team=team)
        thief = keeper if r < 0.35 else marker
        self.ball, self.possession, self.carrier = end, opp, thief
        return self._event(b, "PASS", "INTERCEPTED", start, end, length, metrics, opponent=thief)

    def _foul(self, b, presser):
        """`presser` fouls the player on the ball: a free kick, or a penalty inside the box.
        Cards follow the referee's rates in the reference data."""
        team, pid, opp = b["team"], b["player"], self.other(b["team"])
        start = self.ball
        in_box = b["u"] >= BOX_U and abs(b["v"] - 50) <= BOX_HALF_V
        card = None
        if self.slots[opp][presser][0] != "GK":
            r = self.rng.random()
            boost = 1.5 if in_box else 1.0  # denying a chance is punished harder
            booked = self.yellows.get((opp, presser), 0)
            if r < P_RED * boost:
                card = "RED"
            elif r < P_RED * boost + P_YELLOW * boost * (0.2 if booked else 1):  # booked players hold back
                self.yellows[(opp, presser)] = self.yellows.get((opp, presser), 0) + 1
                card = "RED" if self.yellows[(opp, presser)] >= 2 else "YELLOW"
        spot = self.absolute(team, PEN_SPOT_U, 50) if in_box else start
        kind = self._award("PENALTY" if in_box else "FREE_KICK", team, spot)
        tackler = dict(b, team=opp, player=presser)
        ev = self._event(tackler, "TACKLE", "FOUL", start, start, 0.0, self._metrics(b), opponent=pid, card=card,
                         restart=kind, restart_team=team)
        if card == "RED":
            del self.slots[opp][presser]
            self.positions[opp].pop(presser, None)
        return ev

    # ---- open play -----------------------------------------------------
    def _pass(self, b, focus_team, focus_player, focus_bias, set_piece=None):
        team, pid, opp = b["team"], b["player"], self.other(b["team"])
        start = self.ball
        long_kick = set_piece == "GOAL_KICK" and self.rng.random() < 0.45
        options = []
        for mate, pos in self.positions[team].items():
            if mate == pid:
                continue
            mu, mv = self.frame(team, *pos)
            gain = (mu - b["u"]) * PITCH_L / 100
            dist = self.dist_m(start, pos)
            if dist < 4 or (set_piece == "THROW_IN" and (dist > 28 or self.slots[team][mate][0] == "GK")):
                continue
            space = self.nearest(opp, pos)[1]
            if long_kick:
                w = math.exp(-((dist - 50) / 12) ** 2) * (0.4 + min(space, 8) / 8)
            else:
                w = math.exp(-((dist - 18) / 16) ** 2) * (1 + max(-0.6, gain / 20)) * (0.4 + min(space, 8) / 8)
            if self.slots[team][mate][0] == "GK":
                w *= 0.15
            if team == focus_team and mate == focus_player:
                w *= 1 + focus_bias * 4
            options.append((max(w, 0.01), mate, pos, gain, dist, space))
        _, rec, target, _, _, space = self.rng.choices(options, weights=[o[0] for o in options])[0]
        tu, tv = self.frame(team, *target)
        run_kmh = None
        if not set_piece and self.slots[team][rec][0] in ("ST", "LW", "RW", "CAM") and tu >= 62 \
                and self.rng.random() < 0.5:
            run_kmh = round(TOP_SPEED[team][rec] * self.rng.uniform(0.86, 1.0), 1)  # the runner sprints onto it
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
        if set_piece == "THROW_IN":
            speed = round(self.rng.uniform(28, 45), 1)
        else:
            speed = round(clamp(38 + length * 1.3 + self.rng.uniform(-6, 8), 25, 110), 1)
        metrics = self._metrics(b, pass_difficulty=diff, ball_speed_kmh=speed, sprint_speed_kmh=run_kmh,
                                forward_gain_m=round(gain, 1), players_bypassed=bypassed)
        if run_kmh and self.rng.random() < 0.15:
            # the runner went too early: flag up, indirect free kick where the runner stood
            kind = self._award("FREE_KICK", opp, target)
            return self._event(b, "PASS", "OFFSIDE", start, target, self.dist_m(start, target), metrics,
                               receiver=rec, restart=kind, restart_team=opp)
        p_fail = (diff / 100) ** 2.2 * 0.7 * (1 - self.skill(team, pid, "passing") * 1.5)
        if self.rng.random() > p_fail:
            self.ball, self.carrier = end, rec
            return self._event(b, "PASS", "COMPLETE", start, end, length, metrics, receiver=rec)
        if self.rng.random() < 0.5:
            # overhit or miscontrolled: out over the byline or the touchline (throw-in)
            if eu >= 92:
                out = self.absolute(team, 100, clamp(ev_, 4, 96))
                if self.rng.random() < 0.4:  # off a defender's last touch: corner
                    kind = self._award("CORNER", team, self._corner_spot(team, ev_))
                    return self._event(b, "PASS", "OUT", start, out, self.dist_m(start, out), metrics,
                                       restart=kind, restart_team=team)
                spot = self.absolute(opp, SIX_U, 50 + self.rng.uniform(-SIX_HALF_V, SIX_HALF_V))
                kind = self._award("GOAL_KICK", opp, spot)
            else:
                out = self.absolute(team, clamp(eu, 2, 98), 0 if ev_ < 50 else 100)
                kind = self._award("THROW_IN", opp, out)
            return self._event(b, "PASS", "OUT", start, out, self.dist_m(start, out), metrics,
                               restart=kind, restart_team=opp)
        # intercepted somewhere along the line by the defender closest to it
        f = self.rng.uniform(0.45, 0.95)
        cut = (start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f)
        thief, _ = self.nearest(opp, cut)
        cu, cv = self.frame(team, *cut)
        if (cu >= 78 or (cu >= 66 and abs(cv - 50) > 25)) and self.rng.random() < 0.6:
            # cleared behind under pressure, or a cross blocked out: corner
            kind = self._award("CORNER", team, self._corner_spot(team, cv))
            return self._event(b, "PASS", "INTERCEPTED", start, cut, self.dist_m(start, cut), metrics,
                               opponent=thief, restart=kind, restart_team=team)
        self.ball, self.possession, self.carrier = cut, opp, thief
        return self._event(b, "PASS", "INTERCEPTED", start, cut, self.dist_m(start, cut), metrics, opponent=thief)

    def _dribble(self, b, presser):
        team, pid, opp = b["team"], b["player"], self.other(b["team"])
        role = self.slots[team][pid][0]
        start = self.ball
        p_win = (0.86 - b["p_idx"] / 100 * 0.45 + (0.08 if role in ("LW", "RW") else 0)
                 + self.skill(team, pid, "dribbling") * 0.5 - self.skill(opp, presser, "defending") * 0.4)
        speed = round(TOP_SPEED[team][pid] * self.rng.uniform(0.75, 0.97), 1)
        if self.rng.random() < p_win:
            du = self.rng.uniform(3, 13)
            dv = self.rng.uniform(-7, 7) + (50 - b["v"]) * (0.25 if b["u"] > 65 else 0.08)  # cut inside near goal
            end = self.absolute(team, clamp(b["u"] + du, 2, 97), clamp(b["v"] + dv, 3, 97))
            self.ball = end
            m = self._metrics(b, sprint_speed_kmh=speed, ball_speed_kmh=speed)
            return self._event(b, "DRIBBLE", "SUCCESS", start, end, self.dist_m(start, end), m)
        # the nearest defender steps in: the event belongs to the tackler
        if self.rng.random() < 0.32 * self._care(b["u"], b["v"]):
            return self._foul(b, presser)
        end = (clamp(start[0] + self.rng.uniform(-2, 2)), clamp(start[1] + self.rng.uniform(-2, 2)))
        m = self._metrics(b)
        tackler = dict(b, team=opp, player=presser)
        if (b["v"] < 20 or b["v"] > 80) and self.rng.random() < 0.5:
            # won near the touchline but it runs out: throw-in to the tackler's side
            out = self.absolute(team, b["u"], 0 if b["v"] < 50 else 100)
            kind = self._award("THROW_IN", opp, out)
            return self._event(tackler, "TACKLE", "WON", start, out, self.dist_m(start, out), m, opponent=pid,
                               restart=kind, restart_team=opp)
        self.ball, self.possession, self.carrier = end, opp, presser
        return self._event(tackler, "TACKLE", "WON", start, end, self.dist_m(start, end), m, opponent=pid)

    def _shot(self, b, body_part="FOOT", set_piece=None):
        team, opp = b["team"], self.other(b["team"])
        start = self.ball
        if set_piece == "PENALTY":
            xg, dist = PENALTY_XG, 11.0
        else:
            xg, dist = xg_model(b["u"], b["v"], b["p_idx"])
            if body_part == "HEAD":
                xg = round(xg * 0.55, 2)  # headers convert far less often than shots with the foot
        keeper = self.gk(opp)
        goal_x = 100.0 if team == self.right_team else 0.0
        mouth = 3.66 / PITCH_W * 100
        # xG describes the chance; whether it goes in also depends on the shooter and the keeper
        finish = 1 + self.skill(team, b["player"], "shooting") * 1.2 - (self.skill(opp, keeper, "goalkeeping") - 0.05) * 1.2
        if self.rng.random() < min(0.97, xg * finish):
            outcome = "GOAL"
        elif set_piece == "PENALTY":
            outcome = "SAVED" if self.rng.random() < 0.7 else "MISS"
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
        ev = self._event(b, "SHOT", outcome, start, end, dist, m, opponent=opponent, body_part=body_part)
        end_v = self.frame(team, *end)[1]
        if outcome == "GOAL":
            self.score[team] += 1
            ev["score"] = {"home": self.score[HOME], "away": self.score[AWAY]}
            ev["_kickoff"] = opp
        elif outcome == "SAVED" and self.rng.random() < 0.55:
            # parried behind
            ev["restart"], ev["restart_team"] = self._award("CORNER", team, self._corner_spot(team, end_v)), team
        elif outcome == "SAVED":
            self.possession, self.carrier = opp, keeper
            self.ball = self.absolute(opp, 5, 50)
        elif outcome == "MISS":
            spot = self.absolute(opp, SIX_U, 50 + self.rng.uniform(-SIX_HALF_V, SIX_HALF_V))
            ev["restart"], ev["restart_team"] = self._award("GOAL_KICK", opp, spot), opp
        elif self.rng.random() < 0.7:
            # deflected behind off the blocker
            ev["restart"], ev["restart_team"] = self._award("CORNER", team, self._corner_spot(team, end_v)), team
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
            "set_piece": None, "restart": None, "restart_team": None, "body_part": None,
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
            self._reposition(receiver=ev["receiver"] if ev["outcome"] == "COMPLETE" else None)
        ev["possession_change"] = self.possession != self._poss_before
        ev["right_team"] = self.right_team
        ev["is_impact_moment"], ev["impact_reasons"] = impact_moment(ev)
        ev["generated_at"] = round(time.time() * 1000)
        return ev

    def _status_event(self, etype, minute):
        self.seq += 1
        e = {
            "seq": self.seq, "minute": minute, "clock": "HT" if etype == "HALF_TIME" else "FT",
            "team": None, "player": None, "event_type": etype, "outcome": None,
            "opponent": None, "receiver": None, "player_off": None, "card": None, "length_m": None,
            "set_piece": None, "restart": None, "restart_team": None, "body_part": None,
            "location": {"start_x": 50.0, "start_y": 50.0, "end_x": 50.0, "end_y": 50.0},
            "metrics": {k: None for k in ("xg", "pass_difficulty", "pressure", "pressure_index",
                                           "nearest_defender_m", "sprint_speed_kmh", "ball_speed_kmh",
                                           "forward_gain_m", "players_bypassed")},
            "score": {"home": self.score[HOME], "away": self.score[AWAY]},
            "is_impact_moment": False, "impact_reasons": [], "generated_at": round(time.time() * 1000),
            "possession_change": False, "right_team": self.right_team,
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
