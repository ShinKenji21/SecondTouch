import json
import os

_client = None


def _azure_client():
    global _client
    if _client is None:
        from openai import AzureOpenAI
        _client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version="2024-02-01",
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        )
    return _client


def _facts(ev):
    m = ev["metrics"]
    return {
        "p": ev["player"], "t": ev["event_type"], "o": ev["outcome"], "len": ev["length_m"],
        "xg": m["xg"], "d": m["pass_difficulty"], "pr": (m["pressure"] or "").lower(),
        "pi": m["pressure_index"], "spd": m["sprint_speed_kmh"], "nd": m["nearest_defender_m"],
    }


def _analyst(f):
    if f["t"] == "SHOT":
        res = {"GOAL": "It's in.", "SAVED": "Keeper keeps it out.", "MISS": "It drifts wide.", "BLOCKED": "Blocked before it troubles the keeper."}[f["o"]]
        return f"{f['p']} shoots from {f['len']}m: {f['xg']:.2f} xG under {f['pr']} pressure. {res}"
    if f["t"] == "DRIBBLE":
        return f"{f['p']} carries {f['len']}m at {f['spd']} km/h with the nearest defender {f['nd']}m away (pressure index {f['pi']})."
    return f"{f['p']} plays a {f['len']}m pass rated {f['d']}/100 in difficulty, under {f['pr']} pressure."


def _casual(f):
    if f["t"] == "SHOT":
        return {"GOAL": f"GOAL! {f['p']} buries it!", "SAVED": f"Big save! {f['p']} thought that was in!",
                "MISS": f"{f['p']} fires wide, that one got away.", "BLOCKED": f"{f['p']}'s shot is thrown back by a brave block."}[f["o"]]
    if f["t"] == "DRIBBLE":
        return f"{f['p']} drives forward with the ball!" if f["pi"] < 66 else f"{f['p']} wriggles past a tight marker!"
    return f"{f['p']} finds a teammate." if f["d"] < 60 else f"WHAT A PASS from {f['p']}!"


def _player_cam(f, focus):
    prefix = "On the ball: " if f["p"] == focus else f"Away from {focus}: "
    return prefix + _analyst(f)


def _fallback(ev, mode, focus):
    f = _facts(ev)
    if mode == "CASUAL":
        return _casual(f)
    if mode == "PLAYER_CAM":
        return _player_cam(f, focus)
    return _analyst(f)


def generate_ai_commentary(ev: dict, mode: str = "ANALYST", focus_player: str = "Saka", use_llm: bool = True):
    """Return (text, source_label)."""
    if use_llm and os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
        try:
            r = _azure_client().chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
                messages=[
                    {"role": "system", "content": (
                        f"You are a football commentator. Mode: {mode} (ANALYST = tactical and numeric, CASUAL = excited fan, "
                        f"PLAYER_CAM = focus on {focus_player}). Explain why the moment matters using the supplied metrics. "
                        "One sentence, max 30 words, use only the facts given.")},
                    {"role": "user", "content": json.dumps(_facts(ev), ensure_ascii=False)},
                ],
                max_tokens=70,
            )
            return r.choices[0].message.content.strip(), f"AZURE OPENAI · {mode.replace('_', ' ')}"
        except Exception:
            pass
    return _fallback(ev, mode, focus_player), f"LOCAL ENGINE · {mode.replace('_', ' ')}"
