import math
import random
from datetime import datetime

MATCH_METADATA = {
    "match_id": "ARS_MCI_2026",
    "home_team": "Arsenal",
    "away_team": "Manchester City"
}

PLAYERS = {
    "Arsenal": ["Saka", "Ødegaard", "Rice", "Saliba", "Martinelli"],
    "Manchester City": ["Haaland", "De Bruyne", "Foden", "Rodri", "Bernardo"]
}

def generate_match_event():
    team = random.choice([MATCH_METADATA["home_team"], MATCH_METADATA["away_team"]])
    player = random.choice(PLAYERS[team])
    event_type = random.choices(["PASS", "SHOT", "DRIBBLE"], weights=[60, 15, 25])[0]

    start_x = round(random.uniform(20.0, 80.0), 1)
    start_y = round(random.uniform(10.0, 90.0), 1)
    end_x = round(min(100.0, max(0.0, start_x + random.uniform(-15.0, 20.0))), 1)
    end_y = round(min(100.0, max(0.0, start_y + random.uniform(-10.0, 10.0))), 1)

    distance = round(math.sqrt((end_x - start_x)**2 + (end_y - start_y)**2), 1)
    pressure_level = random.choice(["LOW", "MEDIUM", "HIGH"])
    pass_difficulty = min(100, round(distance * (1.4 if pressure_level == "HIGH" else 1.0)))

    return {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "team": team,
        "player": player,
        "event_type": event_type,
        "location": {"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
        "metrics": {
            "xg": round(random.uniform(0.05, 0.45), 2) if event_type == "SHOT" else 0.34,
            "pass_difficulty": pass_difficulty,
            "pressure": pressure_level,
            "sprint_speed_kmh": round(random.uniform(24.0, 33.5), 1)
        }
    }