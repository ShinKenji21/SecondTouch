"""Synthetic match telemetry for SecondTouch.

Coordinates are percentages of the pitch (0-100). Arsenal (home) attacks
towards x=100, Man City towards x=0. Real-world metres are used for distance,
xG and pressure so the numbers mean something.
"""
import math
import random

HOME, AWAY = "Arsenal", "ManCity"
PITCH_L, PITCH_W = 105.0, 68.0
GOAL_W = 7.32

# id -> (display name, role). Ids match the frontend rosters.
PLAYERS = {
    HOME: {
        "Saka": ("Bukayo Saka", "RW"), "Ødegaard": ("Martin Ødegaard", "CAM"),
        "Rice": ("Declan Rice", "CDM"), "Saliba": ("William Saliba", "CB"),
        "Raya": ("David Raya", "GK"),
    },
    AWAY: {
        "Haaland": ("Erling Haaland", "ST"), "De Bruyne": ("Kevin De Bruyne", "CM"),
        "Foden": ("Phil Foden", "CAM"), "Rodri": ("Rodri", "CDM"),
        "Ederson": ("Ederson", "GK"),
    },
}
ROLE_U = {"GK": 8, "CB": 28, "CDM": 42, "CM": 52, "CAM": 64, "RW": 74, "ST": 82}
ROLE_Y = {"RW": 22, "CB": 45}


def metres(du, dy):
    return math.hypot(du * PITCH_L / 100, dy * PITCH_W / 100)


def xg_model(u, y):
    """Logistic xG from distance and goal-mouth angle (u,y in attack frame)."""
    dx = (100 - u) * PITCH_L / 100
    dy = (y - 50) * PITCH_W / 100
    dist = math.hypot(dx, dy)
    angle = math.atan2(GOAL_W * dx, dx * dx + dy * dy - (GOAL_W / 2) ** 2)
    if angle < 0:
        angle += math.pi
    logit = -1.2 - 0.09 * dist + 1.5 * angle
    return round(1 / (1 + math.exp(-logit)), 2), round(dist, 1)


def clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


class MatchSim:
    def __init__(self):
        self.minute = 0.0
        self.seq = 0
        self.score = {HOME: 0, AWAY: 0}

    @property
    def finished(self):
        return self.minute >= 90

    def next_event(self, focus_team=None, focus_player=None, focus_bias=0.5):
        if focus_team in PLAYERS and focus_player in PLAYERS[focus_team] and random.random() < focus_bias:
            team, pid = focus_team, focus_player
        else:
            team = random.choice([HOME, AWAY])
            pid = random.choice(list(PLAYERS[team]))
        name, role = PLAYERS[team][pid]

        self.minute += random.uniform(0.4, 1.4)
        self.seq += 1

        u = clamp(random.gauss(ROLE_U[role], 10), 3, 97)
        y = clamp(random.gauss(ROLE_Y.get(role, 50), 18), 5, 95)
        shot_w = 0 if role == "GK" else (14 if u > 62 else 2)
        etype = random.choices(["PASS", "DRIBBLE", "SHOT"], weights=[60, 25, shot_w])[0]

        xg = diff = outcome = dist_m = None
        speed = None
        if etype == "SHOT":
            u = clamp(random.uniform(72, 94))
            y = clamp(random.gauss(50, 16), 18, 82)
            xg, dist_m = xg_model(u, y)
            r = random.random()
            if r < xg:
                outcome = "GOAL"
                self.score[team] += 1
            else:
                outcome = random.choices(["SAVED", "MISS", "BLOCKED"], weights=[40, 40, 20])[0]
            eu = 100
            ey = 50 + random.uniform(-5.4, 5.4)
            if outcome == "MISS":
                ey = 50 + random.choice([-1, 1]) * random.uniform(8, 14)
            elif outcome == "BLOCKED":
                f = random.uniform(0.3, 0.6)
                eu, ey = u + (100 - u) * f, y + (50 - y) * f
            length = dist_m
        elif etype == "DRIBBLE":
            eu = clamp(u + random.uniform(2, 14))
            ey = clamp(y + random.uniform(-8, 8))
            length = metres(eu - u, ey - y)
            speed = round(random.uniform(24.0, 33.5), 1)
        else:
            eu = clamp(u + random.uniform(-12, 24))
            ey = clamp(y + random.uniform(-25, 25))
            length = metres(eu - u, ey - y)

        nearest = random.expovariate(1 / max(2.5, 8 - u / 15))  # nearest defender, metres
        p_idx = round(clamp(100 - nearest * 11))
        pressure = "HIGH" if p_idx >= 66 else "MEDIUM" if p_idx >= 33 else "LOW"
        if etype == "PASS":
            diff = round(clamp(length * 2 + p_idx * 0.4 + max(0, eu - u) * 0.5, 5, 99))

        def to_pitch(a, b):  # attack frame -> absolute pitch
            return (round(a, 1), round(b, 1)) if team == HOME else (round(100 - a, 1), round(100 - b, 1))

        sx, sy = to_pitch(u, y)
        ex, ey2 = to_pitch(eu, ey)
        m = int(self.minute)
        return {
            "seq": self.seq,
            "minute": round(self.minute, 2),
            "clock": f"{m}'",
            "team": team,
            "player": pid,
            "player_name": name,
            "role": role,
            "event_type": etype,
            "outcome": outcome,
            "length_m": round(length, 1),
            "location": {"start_x": sx, "start_y": sy, "end_x": ex, "end_y": ey2},
            "metrics": {
                "xg": xg,
                "pass_difficulty": diff,
                "pressure": pressure,
                "pressure_index": p_idx,
                "nearest_defender_m": round(nearest, 1),
                "sprint_speed_kmh": speed,
            },
            "score": {"home": self.score[HOME], "away": self.score[AWAY]},
        }
