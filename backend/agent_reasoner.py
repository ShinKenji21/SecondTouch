"""Stage 2 - the connection to Microsoft Foundry (Azure OpenAI), the agents' instructions, and the
fact-only view of an event the agents read. The agents themselves and the workflows that coordinate
them are in agents.py.
"""
import os

from analytics import metres
from persona_router import T, TEAM_NAMES, _zone

_client = None
# The stream never waits for the model (template text is already on screen), so a few seconds is fine.
TIMEOUT_S = float(os.getenv("AZURE_OPENAI_TIMEOUT_S", "6"))

SYSTEM = (
    "You are the SecondTouch commentary team for one live football moment. You get its facts as JSON. "
    "Rules: use only the facts given and never invent players, scores, leads or numbers; read the score exactly as "
    "given (if it is level, nobody is leading); describe places with the zone words given, never coordinates or "
    "percentages of the pitch; write team and player names exactly as given, without translating or respelling them.\n"
    "Write like a real TV broadcast, where each voice has its own job:\n"
    '  "casual" is the lead commentator calling the action live: present tense, short bursts, led by the player\'s '
    "name and a precise action verb (threads, slides, whips in, drills, curls, nods, nicks, blocks, palms away), saying "
    "what actually happened, not generic hype. Match the energy to moment_size: 'notable' is appreciative and calm, "
    "'big' rises, 'huge' is full voice (a goal can be its own exclamation). One or two short phrases, under 120 "
    "characters. Speak like a person, not a data feed: no jargon or metrics (no xG, 'third', 'line-breaking', "
    "'pressure index') and no minutes or clock times. If favourite_club is given, speak as one of its supporters. "
    "Never use stock phrases such as "
    "'what a cracker', 'serious push', 'all over them', 'statement', 'game changer', 'what a moment'.\n"
    '  "analyst" is the co-commentator: explains why it matters (space, pressure, a line bypassed, the quality of a '
    "chance) in at most two short sentences under 230 characters, citing at least one metric and the zone. Measured, "
    "no exclamations.\n"
    '  "player_cam" follows the focus player, in the third person, one sentence under 200 characters: if they are '
    "involved, what they did; otherwise where they are relative to the ball, with their touches or sprints.\n"
    "Examples of the casual voice (style only; the [brackets] stand for the real names in the facts):\n"
    "  notable pass: '[passer] threads it between the lines, and [runner] is away.'\n"
    "  big save: '[shooter] gets the header in, and [keeper] palms it round the post!'\n"
    "  huge goal: '[scorer]... curls it in! [team] lead!' (only if the score says they lead)\n"
    "  Spanish: '¡[passer] la mete entre líneas y [runner] ya corre!' / '¡GOOOL de [scorer]!'\n"
    "  Japanese: '[passer]、ライン間へ通した！[runner]が抜け出す！' / 'ゴール！[scorer]が決めた！'\n"
    "Reply with a JSON object with exactly the keys analyst, casual and player_cam. Write every value in {language}."
)

NARRATIVE_SYSTEM = {
    "story": (
        "You are SecondTouch's match storyteller. You get one key moment of a synthetic football match as JSON: "
        "the build-up actions in order, the moment itself, and context about the players. Write the story behind "
        "it in {language}: two or three sentences, vivid but factual, covering how the move started, what happened, "
        "and why it matters for the match. Use only the facts given; keep player names as given. Plain text only."
    ),
    "report": (
        "You are SecondTouch's studio analyst. You get the statistics of a synthetic football match at {when} as "
        "JSON. Write a {when} report in {language}: four or five sentences covering the score versus the chances "
        "created (xG), who controlled the game or whether it was chaotic, the pressing battle, and the best player. "
        "Use only the facts given. Plain text only."
    ),
}

ASK_SYSTEM = (
    "You are SecondTouch's tactical assistant for a live (synthetic) football match. Answer the "
    "viewer's question in {language}, in at most four sentences, using only the match data provided. "
    "If the data cannot answer it, say so briefly."
)


def configured():
    return bool(os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"))


def _endpoint():
    """The resource address. Foundry also shows it with /openai/v1 on the end; the SDK adds that path itself."""
    ep = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
    for suffix in ("/openai/v1", "/openai"):
        if ep.endswith(suffix):
            ep = ep[: -len(suffix)]
    return ep + "/"


def _azure():
    global _client
    if _client is None:
        from openai import AsyncAzureOpenAI
        _client = AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=_endpoint(),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            timeout=TIMEOUT_S,
            max_retries=0,
        )
    return _client


def _deployment():
    return os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")


def _moment_size(ev):
    """How loud the lead commentator should be: huge (goals, red cards, penalties, VAR), big (big chances,
    saves, the woodwork) or notable (a good pass, a press win, a booking)."""
    r = set(ev["impact_reasons"])
    if r & {"goal", "own_goal", "red_card", "penalty", "penalty_awarded", "var_no_goal"}:
        return "huge"
    if r & {"big_chance", "woodwork", "direct_free_kick"} or ev["outcome"] == "SAVED":
        return "big"
    return "notable"


def _score_line(ev, ctx, names):
    h, a = ev["score"]["home"], ev["score"]["away"]
    situation = "level" if h == a else f"{names[ctx.home] if h > a else names[ctx.away]} lead by {abs(h - a)}"
    return f"{names[ctx.home]} {h}-{a} {names[ctx.away]} ({situation})"


def event_facts(ev, ctx, lang="en"):
    """The compact, fact-only view of an event that the model sees: names as the viewer sees them,
    places as zones (not coordinates), the score with who leads, and where the focus player is."""
    names = TEAM_NAMES.get(lang, TEAM_NAMES["en"])
    m = {k: v for k, v in ev["metrics"].items() if v is not None}
    if "players_bypassed" in m:  # say what it counts, so it is not read as "lines broken"
        m["opponents_bypassed"] = m.pop("players_bypassed")
    loc = ev["location"]
    zone = _zone(T["en"], ev["team"], ctx.right_team, loc["start_x"], loc["start_y"]) if ev["team"] else None
    focus = ctx.positions.get(ctx.focus_team, {}).get(ctx.focus_player)
    involved = ctx.focus_player in (ev["player"], ev["receiver"], ev["opponent"], ev.get("player_off"))
    facts = {
        "minute": ev["clock"], "team": names.get(ev["team"], ev["team"]), "player": ev["player"],
        "event": ev["event_type"], "outcome": ev["outcome"],
        "receiver": ev["receiver"], "opponent": ev["opponent"], "card": ev["card"],
        "set_piece": ev.get("set_piece"), "body_part": ev.get("body_part") if ev.get("body_part") == "HEAD" else None,
        "play_restarts_with": f"{ev['restart']} to {ev['restart_team']}" if ev.get("restart") else None,
        "length_m": ev["length_m"], "metrics": m, "why_flagged": ev["impact_reasons"],
        "moment_size": _moment_size(ev),
        "zone": zone,
        "score": _score_line(ev, ctx, names),
        "team_xg": {names[t]: xg for t, xg in zip((ctx.home, ctx.away), ctx.summary["xg"])},
        "momentum": f"{ctx.summary['momentum']} (-100 = {names[ctx.away]} dominant, +100 = {names[ctx.home]} dominant)",
        "focus_player": {"name": ctx.focus_player, "team": names.get(ctx.focus_team, ctx.focus_team),
                         "involved_in_this_moment": involved, "stats": ctx.focus_line,
                         "metres_from_ball": round(metres(focus[0] - loc["end_x"], focus[1] - loc["end_y"]))
                         if focus else None},
        "favourite_club": names.get(ctx.fav_team) if ctx.fav_team else None,
        "game_flow": {k: ctx.summary["flow"][k] for k in ("state", "state_team", "press", "tempo")},
    }
    return {k: v for k, v in facts.items() if v not in (None, [], {})}
