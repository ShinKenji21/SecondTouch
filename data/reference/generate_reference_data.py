"""
Synthetic football reference data generator.

Every club, person, stadium, town and competition below is FICTIONAL.
Towns are invented but styled after English places. Player attributes are
generated deterministically (fixed seed) so the dataset is reproducible.

Output: match_reference_data.json
"""
import json
import random
from datetime import date

SEED = 2026
rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Competition (fictional)
# ---------------------------------------------------------------------------
COMPETITION = {
    "competition_id": "NCD",
    "name": "Northern Crown Division",
    "country": "England (fictional league)",
    "season": "2026-27",
    "tier": 1,
    "teams_in_league": 20,
    "match_length_minutes": 90,
    "substitutions_allowed": 5,
    "var_in_use": True,
}

# ---------------------------------------------------------------------------
# Stadiums (fictional)
# ---------------------------------------------------------------------------
STADIUMS = [
    {
        "stadium_id": "STD-MRL",
        "name": "Millrace Lane",
        "town": "Brackenford",
        "region": "North West England (fictional town)",
        "capacity": 32400,
        "opened": 1924,
        "pitch_length_m": 105,
        "pitch_width_m": 68,
        "surface": "hybrid grass",
        "roof": "partial",
        "stands": [
            {"name": "Weir Stand", "side": "north", "capacity": 9800},
            {"name": "Tannery End", "side": "west", "capacity": 6200, "home_ultras": True},
            {"name": "Lockkeepers' Stand", "side": "south", "capacity": 10600},
            {"name": "Ferry Road End", "side": "east", "capacity": 5800, "away_section": True},
        ],
    },
    {
        "stadium_id": "STD-SWG",
        "name": "The Saltworks Ground",
        "town": "Kestermouth",
        "region": "Yorkshire coast (fictional town)",
        "capacity": 27150,
        "opened": 1931,
        "pitch_length_m": 104,
        "pitch_width_m": 67,
        "surface": "natural grass",
        "roof": "full",
        "stands": [
            {"name": "Lighthouse Stand", "side": "north", "capacity": 8400},
            {"name": "Quayside End", "side": "west", "capacity": 5900, "home_ultras": True},
            {"name": "Netmenders' Stand", "side": "south", "capacity": 8100},
            {"name": "Breakwater End", "side": "east", "capacity": 4750, "away_section": True},
        ],
    },
]

# ---------------------------------------------------------------------------
# Clubs (fictional)
# ---------------------------------------------------------------------------
CLUBS = [
    {
        "club_id": "BRA",
        "name": "Brackenford Athletic FC",
        "short_name": "Brackenford",
        "abbreviation": "BRA",
        "nickname": "The Ferrymen",
        "founded": 1891,
        "town": "Brackenford",
        "home_stadium_id": "STD-MRL",
        "colours": {"primary": "#0F7C7A", "secondary": "#F3EAD3", "away": "#1C1C1C"},
        "manager": {"staff_id": "MGR-BRA", "name": "Corwen Ashdale", "nationality": "WAL", "preferred_formation": "4-3-3"},
        "playing_style": {"possession_bias": 0.62, "press_intensity": 0.71, "directness": 0.38, "width": 0.66},
        "league_position_before_match": 4,
    },
    {
        "club_id": "KHB",
        "name": "Kestermouth Harbour FC",
        "short_name": "Kestermouth",
        "abbreviation": "KHB",
        "nickname": "The Lamplighters",
        "founded": 1903,
        "town": "Kestermouth",
        "home_stadium_id": "STD-SWG",
        "colours": {"primary": "#D2601A", "secondary": "#14213D", "away": "#FFFFFF"},
        "manager": {"staff_id": "MGR-KHB", "name": "Henrietta Vosloo-Marsh", "nationality": "RSA", "preferred_formation": "4-2-3-1"},
        "playing_style": {"possession_bias": 0.47, "press_intensity": 0.55, "directness": 0.64, "width": 0.52},
        "league_position_before_match": 7,
    },
]

# ---------------------------------------------------------------------------
# Squads: (shirt, name, position, detailed_position, nationality, birth_year, foot, starter)
# Names are deliberately unusual combinations to avoid matching real players.
# ---------------------------------------------------------------------------
SQUADS = {
    "BRA": [
        (1,  "Tobiah Wrenfield",      "GK", "GK",  "ENG", 1996, "right", True),
        (2,  "Callum Brisendine",     "DF", "RB",  "ENG", 2001, "right", True),
        (4,  "Kwabena Ostrander",     "DF", "CB",  "GHA", 1998, "right", True),
        (5,  "Henrik Valstrøm",       "DF", "CB",  "NOR", 1997, "left",  True),
        (3,  "Dario Felcetti",        "DF", "LB",  "ITA", 2000, "left",  True),
        (6,  "Ilias Corvaneau",       "MF", "CDM", "FRA", 1999, "right", True),
        (8,  "Ruairí Tolland",        "MF", "CM",  "IRL", 2002, "right", True),
        (10, "Mateus Quintarelo",     "MF", "CAM", "POR", 1998, "left",  True),
        (7,  "Jaden Thornquist",      "FW", "RW",  "ENG", 2003, "left",  True),
        (9,  "Femi Adewolu-Hart",     "FW", "ST",  "ENG", 1997, "right", True),
        (11, "Sebastián Ormaeche",    "FW", "LW",  "ARG", 2000, "right", True),
        (13, "Aurek Novotár",         "GK", "GK",  "CZE", 1994, "right", False),
        (14, "Lorcan Pettigrove",     "DF", "CB",  "SCO", 2002, "right", False),
        (15, "Marlon Okereke-Vance",  "DF", "RB",  "ENG", 2004, "right", False),
        (16, "Bastian Krüllner",      "MF", "CM",  "GER", 1996, "right", False),
        (17, "Yusuf Demirkanlı",      "MF", "CDM", "TUR", 2001, "right", False),
        (18, "Kaito Morisaki",        "FW", "RW",  "JPN", 2002, "left",  False),
        (19, "Gethin Pryddercombe",   "FW", "ST",  "WAL", 2005, "right", False),
        (20, "Sami Haddaoui-Lenz",    "DF", "LB",  "MAR", 1999, "left",  False),
        (22, "Ollie Brackwater",      "MF", "CAM", "ENG", 2006, "right", False),
    ],
    "KHB": [
        (1,  "Hallam Crewdson",        "GK", "GK",  "ENG", 1995, "right", True),
        (2,  "Theo Marchbanks",        "DF", "RB",  "ENG", 2000, "right", True),
        (4,  "Sverre Lindqvarn",       "DF", "CB",  "SWE", 1996, "right", True),
        (5,  "Bram Dekeyzer",          "DF", "CB",  "BEL", 1999, "left",  True),
        (3,  "Nnamdi Ekwuruke",        "DF", "LB",  "NGA", 2001, "left",  True),
        (6,  "Jonah Whitlaker",        "MF", "CDM", "ENG", 1998, "right", True),
        (8,  "Andrés Villaruela",      "MF", "CDM", "ESP", 1997, "right", True),
        (10, "Luka Pervanović",        "MF", "CAM", "CRO", 1999, "right", True),
        (7,  "Kofi Amponsah-Brent",    "FW", "RW",  "GHA", 2002, "left",  True),
        (11, "Rémi Fontagnac",         "FW", "LW",  "FRA", 2001, "right", True),
        (9,  "Ewan Strachley",         "FW", "ST",  "SCO", 1996, "right", True),
        (12, "Piet van Oosterveld",    "GK", "GK",  "NED", 1993, "right", False),
        (14, "Dominic Fairhurst-Lowe", "DF", "CB",  "ENG", 2003, "right", False),
        (15, "Mikkel Ravnsholt",       "DF", "LB",  "DEN", 2000, "left",  False),
        (16, "Ibrahima Tounkaré",      "MF", "CM",  "SEN", 2002, "right", False),
        (17, "Ciaran Hollowell",       "MF", "CAM", "NIR", 2004, "left",  False),
        (18, "Diego Farelhas",         "FW", "RW",  "POR", 2003, "right", False),
        (19, "Tariq Benhalima",        "FW", "ST",  "ALG", 1998, "right", False),
        (20, "Oskar Wielgoszewski",    "DF", "RB",  "POL", 2001, "right", False),
        (21, "Jarrah Quilliam",        "FW", "ST",  "AUS", 2005, "left",  False),
    ],
}

# Attribute profiles per detailed position: (mean, spread) on a 1-99 scale
PROFILES = {
    "GK":  dict(pace=(45, 6), passing=(58, 8), shooting=(20, 5), dribbling=(30, 6), defending=(30, 6), physical=(70, 6), goalkeeping=(78, 5)),
    "CB":  dict(pace=(64, 6), passing=(62, 7), shooting=(38, 7), dribbling=(52, 7), defending=(79, 5), physical=(78, 5), goalkeeping=(10, 3)),
    "RB":  dict(pace=(78, 5), passing=(68, 6), shooting=(50, 7), dribbling=(68, 6), defending=(71, 5), physical=(68, 6), goalkeeping=(10, 3)),
    "LB":  dict(pace=(78, 5), passing=(68, 6), shooting=(50, 7), dribbling=(68, 6), defending=(71, 5), physical=(68, 6), goalkeeping=(10, 3)),
    "CDM": dict(pace=(66, 6), passing=(75, 5), shooting=(58, 7), dribbling=(68, 6), defending=(74, 5), physical=(76, 5), goalkeeping=(10, 3)),
    "CM":  dict(pace=(70, 6), passing=(77, 5), shooting=(65, 6), dribbling=(74, 5), defending=(62, 7), physical=(70, 6), goalkeeping=(10, 3)),
    "CAM": dict(pace=(73, 6), passing=(80, 5), shooting=(73, 6), dribbling=(81, 5), defending=(42, 7), physical=(60, 7), goalkeeping=(10, 3)),
    "RW":  dict(pace=(86, 4), passing=(72, 6), shooting=(72, 6), dribbling=(82, 5), defending=(38, 7), physical=(60, 7), goalkeeping=(10, 3)),
    "LW":  dict(pace=(86, 4), passing=(72, 6), shooting=(72, 6), dribbling=(82, 5), defending=(38, 7), physical=(60, 7), goalkeeping=(10, 3)),
    "ST":  dict(pace=(79, 6), passing=(66, 7), shooting=(81, 5), dribbling=(74, 6), defending=(35, 6), physical=(76, 6), goalkeeping=(10, 3)),
}
HEIGHT = {"GK": (191, 4), "CB": (188, 4), "RB": (178, 4), "LB": (177, 4), "CDM": (182, 4),
          "CM": (179, 5), "CAM": (175, 5), "RW": (174, 5), "LW": (175, 5), "ST": (184, 5)}


def clamp(v, lo=1, hi=99):
    return max(lo, min(hi, int(round(v))))


def make_player(club_id, row):
    shirt, name, pos, detail, nat, year, foot, starter = row
    attrs = {k: clamp(rng.gauss(m, s)) for k, (m, s) in PROFILES[detail].items()}
    attrs["stamina"] = clamp(rng.gauss(74 if detail != "GK" else 55, 7))
    # Physical tracking values the event generator can use for speed/distance overlays
    top_speed = round(26.0 + (attrs["pace"] - 40) * 0.17 + rng.uniform(-0.6, 0.6), 1)
    month, day = rng.randint(1, 12), rng.randint(1, 28)
    return {
        "player_id": f"{club_id}-{shirt:02d}",
        "club_id": club_id,
        "shirt_number": shirt,
        "name": name,
        "display_name": name.split(" ")[-1],
        "position": pos,
        "detailed_position": detail,
        "nationality": nat,
        "date_of_birth": date(year, month, day).isoformat(),
        "height_cm": clamp(rng.gauss(*HEIGHT[detail]), 160, 205),
        "preferred_foot": foot,
        "squad_role": "starter" if starter else "substitute",
        "attributes": attrs,
        "physical": {
            "top_speed_kmh": top_speed,
            "avg_distance_per_90_km": round(rng.uniform(4.8, 5.8), 1) if detail == "GK" else round(rng.uniform(9.4, 12.3), 1),
            "sprint_threshold_kmh": 25.2,
        },
        "season_to_date": {
            "appearances": rng.randint(4, 8) if starter else rng.randint(0, 6),
            "goals": 0 if detail == "GK" else rng.choice([0, 0, 0, 1, 1, 2, 3, 4, 5]) if detail in ("ST", "RW", "LW", "CAM") else rng.choice([0, 0, 0, 0, 1]),
            "assists": 0 if detail == "GK" else rng.choice([0, 0, 1, 1, 2, 3]),
            "yellow_cards": rng.choice([0, 0, 1, 1, 2]),
        },
    }


# ---------------------------------------------------------------------------
# Match officials (fictional)
# ---------------------------------------------------------------------------
OFFICIALS = [
    {"official_id": "REF-0412", "name": "Malcolm Threlkeld",  "role": "referee",           "nationality": "ENG", "years_experience": 14, "avg_yellows_per_match": 4.1, "avg_reds_per_match": 0.18, "penalties_awarded_per_match": 0.29},
    {"official_id": "REF-0588", "name": "Priya Vansittart",   "role": "assistant_referee_1", "nationality": "ENG", "years_experience": 9},
    {"official_id": "REF-0631", "name": "Owain Gethryn",      "role": "assistant_referee_2", "nationality": "WAL", "years_experience": 7},
    {"official_id": "REF-0702", "name": "Declan Moorcroft",   "role": "fourth_official",   "nationality": "ENG", "years_experience": 5},
    {"official_id": "REF-0377", "name": "Annabel Ruskwood",   "role": "var",               "nationality": "ENG", "years_experience": 16},
    {"official_id": "REF-0659", "name": "Simeon Kettleby",    "role": "avar",              "nationality": "ENG", "years_experience": 8},
]


def build():
    players = []
    for club_id, rows in SQUADS.items():
        players.extend(make_player(club_id, r) for r in rows)

    def lineup(club_id, formation):
        squad = [p for p in players if p["club_id"] == club_id]
        return {
            "club_id": club_id,
            "formation": formation,
            "starting_xi": [p["player_id"] for p in squad if p["squad_role"] == "starter"],
            "substitutes": [p["player_id"] for p in squad if p["squad_role"] == "substitute"],
            "captain": f"{club_id}-{'05' if club_id == 'BRA' else '06'}",
        }

    match = {
        "match_id": "NCD-2627-MD09-BRAKHB",
        "competition_id": COMPETITION["competition_id"],
        "season": COMPETITION["season"],
        "matchday": 9,
        "kickoff_local": "2026-10-24T15:00:00+01:00",
        "stadium_id": "STD-MRL",
        "home_club_id": "BRA",
        "away_club_id": "KHB",
        "attendance": 29815,
        "weather": {"condition": "light drizzle", "temperature_c": 11, "wind_kmh": 18, "wind_direction": "SW", "humidity_pct": 86},
        "pitch_condition": "damp, quick",
        "broadcast_languages": ["en", "es", "fr", "ar", "ja", "id"],
        "officials": [o["official_id"] for o in OFFICIALS],
        "lineups": {"home": lineup("BRA", "4-3-3"), "away": lineup("KHB", "4-2-3-1")},
        "head_to_head": {"meetings": 12, "home_wins": 5, "away_wins": 4, "draws": 3, "last_result": "KHB 2-1 BRA (2026-03-14)"},
        "storylines": [
            "Brackenford unbeaten in 6 at Millrace Lane",
            "Kestermouth's Ewan Strachley needs 1 goal for 50 for the club",
            "Ruairí Tolland's first start after a hamstring injury",
            "Managers Ashdale and Vosloo-Marsh were teammates at a (fictional) academy",
        ],
    }

    return {
        "meta": {
            "dataset": "Synthetic football reference data",
            "version": "1.0.0",
            "generator_seed": SEED,
            "disclaimer": "All clubs, people, stadiums, towns and competitions are fictional. Any resemblance to real persons or organisations is coincidental.",
        },
        "competition": COMPETITION,
        "stadiums": STADIUMS,
        "clubs": CLUBS,
        "players": players,
        "officials": OFFICIALS,
        "match": match,
    }


if __name__ == "__main__":
    data = build()
    with open("match_reference_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(data['players'])} players, {len(data['clubs'])} clubs, "
          f"{len(data['officials'])} officials, {len(data['stadiums'])} stadiums")
