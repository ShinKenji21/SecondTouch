"""Stage 2 - AI reasoning with Azure OpenAI.

Impact moments are sent to the configured deployment, which returns all three
personas in one JSON object. The reply is validated with Pydantic; anything
malformed, slow or failing returns None and the template text stays on screen.
"""
import json
import logging
import os

from pydantic import ValidationError

from models import PersonaCommentary
from persona_router import LANG_NAMES

log = logging.getLogger("secondtouch.ai")
_client = None
TIMEOUT_S = float(os.getenv("AZURE_OPENAI_TIMEOUT_S", "4"))

SYSTEM = (
    "You are SecondTouch, a live football commentary engine. You get the facts of one "
    "match event as JSON. Explain why the moment matters tactically (e.g. bypassing a press, "
    "a defensive line breaking, the shot's xG). Use only the facts given, never invent players, "
    "scores or numbers. Reply with a JSON object with exactly these keys:\n"
    '  "analyst": one or two sentences, tactical and numeric, citing at least one metric and the pitch zone;\n'
    '  "casual": one short, high-energy sentence for a casual fan, mention momentum if it is strong; if a '
    "favourite_club is given, speak as one of its supporters (celebrate its moments, groan at the opponent's);\n"
    '  "player_cam": one sentence from the point of view of the focus player, using their touches/sprints and '
    "distance to the ball.\n"
    "Write every value in {language}. Keep player names as given."
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


def _azure():
    global _client
    if _client is None:
        from openai import AsyncAzureOpenAI
        _client = AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            timeout=TIMEOUT_S,
            max_retries=0,
        )
    return _client


def _deployment():
    return os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")


def event_facts(ev, ctx):
    """The compact, fact-only view of an event that the model sees."""
    m = {k: v for k, v in ev["metrics"].items() if v is not None}
    facts = {
        "minute": ev["clock"], "team": ev["team"], "player": ev["player"],
        "event": ev["event_type"], "outcome": ev["outcome"],
        "receiver": ev["receiver"], "opponent": ev["opponent"], "card": ev["card"],
        "length_m": ev["length_m"], "metrics": m, "why_flagged": ev["impact_reasons"],
        "start_xy_pct": [ev["location"]["start_x"], ev["location"]["start_y"]],
        "score": f"{ctx.home} {ev['score']['home']}-{ev['score']['away']} {ctx.away}",
        "team_xg": dict(zip((ctx.home, ctx.away), ctx.summary["xg"])),
        "momentum": f"{ctx.summary['momentum']} (-100 = {ctx.away} dominant, +100 = {ctx.home} dominant)",
        "home_attacks": "towards x=100",
        "focus_player": ctx.focus_player, "focus_player_stats": ctx.focus_line,
        "favourite_club": ctx.fav_team,
        "game_flow": {k: ctx.summary["flow"][k] for k in ("state", "state_team", "press", "tempo")},
    }
    return {k: v for k, v in facts.items() if v not in (None, [], {})}


async def persona_commentary(ev, ctx, lang):
    """Return {"analyst", "casual", "player_cam"} from Azure OpenAI, or None."""
    if not configured():
        return None
    try:
        r = await _azure().chat.completions.create(
            model=_deployment(),
            messages=[
                {"role": "system", "content": SYSTEM.format(language=LANG_NAMES[lang])},
                {"role": "user", "content": json.dumps(event_facts(ev, ctx), ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=260,
        )
        out = PersonaCommentary.model_validate_json(r.choices[0].message.content or "")
        return out.model_dump()
    except ValidationError as e:
        log.warning("Azure reply failed validation, keeping templates: %s", e.errors()[:1])
    except Exception as e:  # network, auth, timeout, content filter
        log.warning("Azure call failed, keeping templates: %s", type(e).__name__)
    return None


async def narrative(kind, facts, lang):
    """A story behind a key event ("story") or a half/full-time report ("report"), or None."""
    if not configured():
        return None
    when = "half-time" if facts.get("kind") == "HALF_TIME" else "full-time"
    try:
        r = await _azure().chat.completions.create(
            model=_deployment(),
            messages=[
                {"role": "system", "content": NARRATIVE_SYSTEM[kind].format(language=LANG_NAMES[lang], when=when)},
                {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
            ],
            max_completion_tokens=320,
        )
        text = (r.choices[0].message.content or "").strip()
        return text if 20 <= len(text) <= 1500 else None
    except Exception as e:
        log.warning("Azure %s failed, keeping templates: %s", kind, type(e).__name__)
        return None


async def answer_question(question, match_context, lang):
    """Free-text answer for the Talk to AI tab, or None."""
    if not configured():
        return None
    try:
        r = await _azure().chat.completions.create(
            model=_deployment(),
            messages=[
                {"role": "system", "content": ASK_SYSTEM.format(language=LANG_NAMES[lang])},
                {"role": "user", "content": "Match data:\n" + json.dumps(match_context, ensure_ascii=False)
                 + "\n\nQuestion: " + question[:500]},
            ],
            max_completion_tokens=300,
        )
        text = (r.choices[0].message.content or "").strip()
        return text or None
    except Exception as e:
        log.warning("Azure ask failed: %s", type(e).__name__)
        return None
