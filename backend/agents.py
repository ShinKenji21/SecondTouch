"""Stage 2 - the SecondTouch agent desk, built with Microsoft Agent Framework on Microsoft Foundry.

A broadcast crew of specialised agents works on every moment the engine flags, coordinated by
Agent Framework workflows and sharing one view of the live match (the MatchDesk):

  Analyst        reads the moment, calls live-stats tools for context, and decides what matters
  Commentator    turns the analyst's brief into analyst / casual-fan / player-cam lines in the
                 viewer's language
  Storyteller    writes the story behind a key event from its build-up
  Studio analyst writes the half-time and full-time reports
  Match desk     answers viewers' questions, fetching what it needs with the same tools
  Recap editor   writes the recap every quarter of an hour, and a personal "while you were away"
                 catch-up for a viewer coming back, shaped by their mode, club and player
  Fact-checker   (a deterministic executor) checks every number and score claim in a draft
                 against the match data and the tool results; a draft that fails goes back to its
                 writer with the problems listed, and a second failure falls back to the
                 template engine, so a made-up stat never reaches the screen

    commentary:  Analyst --> Commentator --> Fact-checker --(revise once)--> Commentator
    stories:     Storyteller --> Fact-checker --(revise once)--> Storyteller
    reports:     Studio analyst --> Fact-checker --(revise once)--> Studio analyst
    questions:   Match desk (tools) --> Fact-checker --(revise once)--> Match desk
    recaps:      Recap editor (tools) --> Fact-checker --(revise once)--> Recap editor

Every run returns a trace (which agent did what, how long it took, which tools it called, what
the checker found) that the dashboard shows next to the text. A timeout, an error or a failed
check returns the trace with no text, and the template text simply stays on screen.
"""
import asyncio
import difflib
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field

from agent_framework import Agent, Executor, WorkflowBuilder, WorkflowContext, handler, tool
from opentelemetry import trace
from pydantic import BaseModel, Field, ValidationError

import agent_reasoner as ar
from generator import SQUADS
from models import PersonaCommentary
from persona_router import LANG_NAMES, TEAM_NAMES

log = logging.getLogger("secondtouch.agents")

RUN_TIMEOUT_S = 14       # a whole pipeline, including one revision
MAX_REVISIONS = 1


# ---- shared match state and the tools the agents use to read it -------------------------------
class MatchDesk:
    """The live match as the agents see it: stats, the simulation state and recent events."""

    def __init__(self, stats, sim, recent, reports, home, away):
        self.stats, self.sim, self.recent, self.reports = stats, sim, recent, reports
        self.home, self.away = home, away

    def team(self, name):
        """Accept 'Brackenford', 'brack', 'home' or 'away' and return the team key, or None."""
        n = (name or "").strip().lower()
        if n in ("home", "away"):
            return self.home if n == "home" else self.away
        return next((t for t in (self.home, self.away) if n and (n in t.lower() or t.lower() in n)), None)

    def tools(self, seen, calls):
        """Tools bound to this desk for one run. Every number they return is recorded in `seen`
        so the fact-checker accepts it, and every call is recorded in `calls` for the trace."""
        desk = self

        def record(name, result):
            calls.append(name)
            _collect_numbers(result, seen)
            return result

        @tool(description="Both teams compared: score, xG, shots, possession, passing, field tilt, pressing, set pieces and cards.")
        def get_team_comparison() -> dict:
            ts = {t: desk.stats.team_stats(t) for t in (desk.home, desk.away)}
            keys = ("xg", "shots", "on_target", "possession", "pass_pct", "field_tilt", "press_wins", "big_chances",
                    "corners", "fouls", "yellow", "red", "offsides", "distance_km")
            score = desk.recent[-1]["score"] if desk.recent else {"home": 0, "away": 0}
            return record("get_team_comparison", {
                "minute": round(desk.stats.minute, 1), "score": {desk.home: score["home"], desk.away: score["away"]},
                **{t: {k: ts[t][k] for k in keys} for t in ts}})

        @tool(description="One player's match so far: minutes, rating, goals, shots, xG, passing, duels, distance and estimated fitness.")
        def get_player_stats(player: str) -> dict:
            q = (player or "").strip().lower()
            fit = desk.sim.fitness()
            for t in (desk.home, desk.away):
                for p in desk.stats.player_rows(t):
                    if q and (q == p["id"].lower() or q in p["name"].lower()):
                        keys = ("name", "pos", "minutes", "rating", "goals", "assists", "shots", "on_target", "xg", "xa",
                                "passes_completed", "passes", "key_passes", "dribbles_won", "tackles_won", "interceptions",
                                "aerials_won", "touches", "sprints", "distance_km", "top_speed", "yellow", "red")
                        return record("get_player_stats", {**{k: p[k] for k in keys}, "team": t,
                                                           "estimated_fitness": fit[t].get(p["id"])})
            return record("get_player_stats", {"error": f"no player called {player}"})

        @tool(description="The most recent match events, newest last.")
        def get_recent_events(count: int = 6) -> list:
            evs = desk.recent[-max(1, min(int(count or 6), 8)):]
            return record("get_recent_events", [{k: e.get(k) for k in ("clock", "team", "player", "event_type", "outcome",
                                                                          "receiver", "opponent", "set_piece")} for e in evs])

        @tool(description="The flow of the game now: control or chaos, turnover rate, tempo, pressure each team applies, momentum.")
        def get_game_flow() -> dict:
            s = desk.stats.summary()
            f = s["flow"]
            return record("get_game_flow", {"state": f["state"], "team_in_control": f["state_team"],
                                            "turnover_rate_pct": f["turnover_rate"], "tempo": f["tempo"],
                                            "pressure_applied": f["press"], "momentum": s["momentum"],
                                            "momentum_scale": f"+100 = {desk.home} on top, -100 = {desk.away} on top"})

        @tool(description="One team's tactical shape: formation, line height and width in and out of possession, attack channels, PPDA.")
        def get_tactics(team: str) -> dict:
            t = desk.team(team) or desk.home
            tac = {k: v for k, v in desk.stats.tactics(t).items() if k != "avg_positions"}
            return record("get_tactics", {"team": t, **tac})

        return [get_team_comparison, get_player_stats, get_recent_events, get_game_flow, get_tactics]


# ---- the agents ---------------------------------------------------------------------------------
class Brief(BaseModel):
    insight: str = Field(description="The single most important thing about this moment, one sentence")
    evidence: list[str] = Field(default_factory=list, description="Up to three supporting facts, each with its number")


ANALYST = (
    "You are the Analyst on a live football broadcast desk. You get the facts of one match moment as JSON. "
    "Decide the single most important thing about it: why it matters for the match, not just what happened. "
    "You may call at most two tools to add context (team comparison, game flow, a player's stats, recent events, "
    "tactics). Use only numbers that appear in the facts or in tool results. "
    "'opponents_bypassed' counts players taken out by a pass, not lines. Read the score exactly as given."
)
STORYTELLER = ar.NARRATIVE_SYSTEM["story"] + (
    " Read the score exactly as given (if it is level, nobody leads). Never write numbers that are not in the facts.")
STUDIO = ar.NARRATIVE_SYSTEM["report"] + (
    " At full time the facts include 'story': the half-time score, who was on top in each half, and the turning "
    "points in order (goals with the score after them, red cards, missed penalties, goals ruled out by VAR, momentum "
    "swings). Then open with the story of the match: three or four sentences that tell how the game unfolded through "
    "those turning points, with their minutes, like a match report in a newspaper. Then a blank line, then the "
    "verdict as above. Never write numbers that are not in the facts.")
RECAP = (
    "You are the Recap editor of a live football broadcast. You get a stretch of play as JSON (from 'start' to "
    "'end'), its key moments in order, the current numbers, and who is watching. Write the recap in {language}: two "
    "or three short sentences. Lead with the score; then the moments that mattered, in order; then who is on top and "
    "why, citing one or two numbers. For a CATCHUP, speak to the viewer ('While you were away...'): if they have a "
    "favourite club, say what it means for them; if they follow a player, mention that player in one clause. In "
    "Analyst mode be tactical; in Casual mode keep it simple and lively. You may call one tool for context. Use only "
    "numbers from the facts or tool results, read the score exactly as given, and keep names as given. Plain text only."
)
DESK = ar.ASK_SYSTEM + (
    " Use the tools to fetch the numbers you need instead of guessing; quote numbers exactly as the tools return them. "
    "Fitness values are estimates; say so if you mention them.")

_agents = None


def _crew():
    """Create the agents once: they are stateless, so concurrent runs share them."""
    global _agents
    if _agents is None:
        from agent_framework.openai import OpenAIChatCompletionClient
        client = OpenAIChatCompletionClient(model=ar._deployment(), async_client=ar._azure())
        _agents = {
            "Analyst": Agent(client, ANALYST, name="Analyst"),
            "Commentator": Agent(client, name="Commentator"),
            "Storyteller": Agent(client, name="Storyteller"),
            "Studio analyst": Agent(client, name="Studio analyst"),
            "Match desk": Agent(client, name="Match desk"),
            "Recap editor": Agent(client, name="Recap editor"),
        }
    return _agents


# ---- the fact-checker -----------------------------------------------------------------------------
_NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)")
# numbers football writing uses without them being statistics: halves, full time, the penalty spot
_COMMON = {11.0, 45.0, 90.0, 100.0}
# every name a draft may use: players (short and full names) and clubs
_NAMES = ({n for team in SQUADS.values() for pid, p in team.items() for n in [pid, *p["name"].split()] if len(n) > 3}
          | {n for names in TEAM_NAMES.values() for n in names.values()} | set(SQUADS))
_NAMES_LOWER = {n.lower(): n for n in _NAMES}
_WORD = re.compile(r"[A-ZÀ-Þ][\wÀ-ÿ'’-]{3,}")
# claims about the score ("go ahead", "take the lead"), not about a statistic ("ahead on xG", "leading the shot count")
_STAT = r"(?!\s+(?:in|on|for|at|with|the)\b)"
_LEAD = {
    "en": re.compile(r"\b(?:take|takes|took|taking|extend|extends|extended|regain|regains|their|a|the) lead\b(?!\s+(?:in|on|for)\b)"
                     r"|\b(?:go|goes|went|are|is|were|was|now|edge|edges|nudge|nudges|put|puts) ahead\b" + _STAT +
                     r"|\b(?:put|puts|putting|send|sends|fire|fires) [\w'-]+ ahead\b" + _STAT +
                     r"|\blead(?:s|ing)? by \d|\bin front\b" + _STAT, re.I),
    "es": re.compile(r"\bse adelanta\b|\bpor delante en el marcador\b|\bamplía la ventaja\b|\bva ganando\b|\bventaja de \d", re.I),
    "ja": re.compile(r"先制|勝ち越|(?<!で)リード"),  # "〜でリード" is a lead in a statistic
}


def _collect_numbers(obj, out):
    """Every number in a JSON-like value, plus its common renderings (rounded, as a percentage)."""
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        if isinstance(obj, float):
            out.update({round(obj, 1), round(obj, 2), float(round(obj))})
            if 0 <= obj <= 1:
                out.add(float(round(obj * 100)))      # 0.13 xG is a 13% chance
        return
    if isinstance(obj, str):
        for m in _NUM.findall(unicodedata.normalize("NFKC", obj)):
            out.add(float(m.replace(",", ".")))
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
        return
    if isinstance(obj, (list, tuple, set)):
        for v in obj:
            _collect_numbers(v, out)


# the language line of every prompt; in Japanese the model tends to spell names in katakana, which then
# match nothing else on screen (the pitch, the log and the headlines all use the names as given)
LANGUAGE = {**LANG_NAMES, "ja": "Japanese, leaving every player name in the Latin letters given, never in katakana "
                                "(Adewolu-Hart, not アデウォル・ハート; Crewdson, not クルードソン)"}
_KATAKANA_NAME = re.compile(r"[ァ-ヺー]+・[ァ-ヺー]+")


def fact_check(text, allowed, level, lang):
    """Problems in a draft: numbers that appear in neither the facts nor the tool results, and a
    claim that someone leads when the score is level. An empty list means the draft passes."""
    text = unicodedata.normalize("NFKC", text)
    problems = []
    for raw in _NUM.findall(text):
        n = float(raw.replace(",", "."))
        if n <= 3 and n == int(n):
            continue                                  # one, two, three: counts and ordinals
        if n not in _COMMON and not any(abs(n - a) <= max(0.051, 0.015 * abs(a)) for a in allowed):
            problems.append(f"'{raw}' does not match any number in the data")
    if level and _LEAD.get(lang, _LEAD["en"]).search(text):
        problems.append("it says a team leads, but the score is level")
    for word in set(_WORD.findall(text)):
        w = re.sub(r"['’]s$", "", word).strip("'’-")   # Whitlaker's is Whitlaker
        if w.lower() in _NAMES_LOWER:
            continue
        close = difflib.get_close_matches(w.lower(), _NAMES_LOWER, n=1, cutoff=0.8)
        if close:  # nearly a squad name, but not quite: a misspelling
            problems.append(f"'{w}' looks like a misspelling of '{_NAMES_LOWER[close[0]]}'")
    if lang == "ja":
        for name in sorted(set(_KATAKANA_NAME.findall(text))):
            problems.append(f"'{name}' is a name spelled in katakana: write player names in the Latin letters given")
    return problems


# ---- one run through a workflow ---------------------------------------------------------------------
@dataclass
class Job:
    kind: str                       # commentary | story | report | answer
    lang: str
    facts: dict
    allowed: set
    level: bool
    writer: str                     # name of the agent that writes the text
    instructions: str
    structured: type | None = None  # pydantic model for structured output
    desk: MatchDesk | None = None
    tools_for: tuple = ()           # agents that may call the desk's tools
    question: str | None = None
    brief: Brief | None = None
    draft: object = None
    feedback: list = field(default_factory=list)
    attempts: int = 0
    status: str = "pending"         # passed | revised | rejected | error
    trace: list = field(default_factory=list)
    calls: list = field(default_factory=list)

    def step(self, agent, started, status, detail=""):
        self.trace.append({"agent": agent, "ms": round((time.time() - started) * 1000), "status": status, "detail": detail})


def _tools(job, agent):
    return job.desk.tools(job.allowed, job.calls) if job.desk and agent in job.tools_for else None


class AnalystStep(Executor):
    @handler
    async def run(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t, before = time.time(), len(job.calls)
        r = await _crew()["Analyst"].run(json.dumps(job.facts, ensure_ascii=False), tools=_tools(job, "Analyst"),
                                         options={"response_format": Brief, "max_tokens": 220})
        # the brief is passed on, but its numbers are not trusted: only facts and tool results are
        job.brief = r.value if isinstance(r.value, Brief) else Brief(insight=r.text or "")
        used = job.calls[before:]
        job.step("Analyst", t, "ok", f"{len(used)} tool call{'s' if len(used) != 1 else ''}" + (f": {', '.join(used)}" if used else ""))
        await ctx.send_message(job)


class WriterStep(Executor):
    @handler
    async def run(self, job: Job, ctx: WorkflowContext[Job]) -> None:
        t, before = time.time(), len(job.calls)
        job.attempts += 1
        parts = [job.instructions, "Facts (JSON):", json.dumps(job.facts, ensure_ascii=False)]
        if job.brief:
            parts += ["The Analyst's brief:", job.brief.model_dump_json()]
        if job.question:
            parts += ["Viewer's question:", job.question]
        if job.feedback:
            parts += ["The fact-checker rejected your previous draft:", "; ".join(job.feedback),
                      "Rewrite it so every number and claim matches the data exactly."]
        options = {"max_tokens": 520 if job.kind == "report" else 320}  # the full-time story is longer
        if job.structured:
            options["response_format"] = job.structured
        r = await _crew()[job.writer].run("\n".join(parts), tools=_tools(job, job.writer), options=options)
        if job.structured:
            job.draft = r.value if isinstance(r.value, job.structured) else job.structured.model_validate_json(r.text)
        else:
            job.draft = (r.text or "").strip()
        used = job.calls[before:]
        job.step(job.writer, t, "ok" if job.attempts == 1 else "revised",
                 f"{len(used)} tool calls: {', '.join(used)}" if used else "")
        await ctx.send_message(job)


class FactCheckStep(Executor):
    @handler
    async def run(self, job: Job, ctx: WorkflowContext[Job, Job]) -> None:
        t = time.time()
        text = " ".join(job.draft.model_dump().values()) if isinstance(job.draft, BaseModel) else str(job.draft or "")
        problems = fact_check(text, job.allowed, job.level, job.lang) if text else ["empty draft"]
        if not problems:
            job.status = "passed" if job.attempts == 1 else "revised"
            job.step("Fact-checker", t, "passed", "every number matches the data")
            await ctx.yield_output(job)
        elif job.attempts <= MAX_REVISIONS:
            job.feedback = problems
            job.step("Fact-checker", t, "revise", "; ".join(problems))
            await ctx.send_message(job)
        else:
            job.status = "rejected"
            job.step("Fact-checker", t, "rejected", "; ".join(problems))
            await ctx.yield_output(job)


def _workflow(with_analyst):
    writer, checker = WriterStep(id="writer"), FactCheckStep(id="fact_checker")
    if with_analyst:
        analyst = AnalystStep(id="analyst")
        return WorkflowBuilder(start_executor=analyst, name="moment").add_edge(analyst, writer) \
            .add_edge(writer, checker).add_edge(checker, writer).build()
    return WorkflowBuilder(start_executor=writer, name="narrative").add_edge(writer, checker) \
        .add_edge(checker, writer).build()


_tracer = trace.get_tracer("secondtouch.agents")


async def _run(job, with_analyst=False):
    """Run a job through its workflow, inside one span that records how it ended (see telemetry.py).
    Returns (text or None, {"steps", "status", "ms", "tools"})."""
    with _tracer.start_as_current_span(f"secondtouch {job.kind}") as span:
        text, run = await _run_workflow(job, with_analyst)
        span.set_attributes({"secondtouch.kind": job.kind, "secondtouch.language": job.lang,
                             "secondtouch.status": run["status"], "secondtouch.duration_ms": run["ms"],
                             "secondtouch.tool_calls": len(run["tools"]),
                             "secondtouch.revisions": sum(1 for s in run["steps"] if s["status"] == "revise"),
                             "secondtouch.agents": [s["agent"] for s in run["steps"]]})
        if run["status"] in ("rejected", "error"):
            span.set_attribute("secondtouch.problem", "; ".join(s.get("detail", "") for s in run["steps"][-1:]))
        return text, run


async def _run_workflow(job, with_analyst):
    started = time.time()
    try:
        result = await asyncio.wait_for(_workflow(with_analyst).run(job), timeout=RUN_TIMEOUT_S)
        job = result.get_outputs()[0]
    except asyncio.TimeoutError:
        job.status = "error"
        job.trace.append({"agent": "Orchestrator", "ms": round((time.time() - started) * 1000), "status": "timeout",
                          "detail": "took too long: templates kept"})
    except (ValidationError, ValueError) as e:
        job.status = "error"
        job.trace.append({"agent": "Orchestrator", "ms": 0, "status": "error", "detail": f"unusable reply ({type(e).__name__})"})
    except Exception as e:  # network, auth, content filter
        log.warning("agent pipeline failed: %s", type(e).__name__)
        job.status = "error"
        job.trace.append({"agent": "Orchestrator", "ms": 0, "status": "error", "detail": type(e).__name__})
    ok = job.status in ("passed", "revised")
    return (job.draft if ok else None), {"steps": job.trace, "status": job.status,
                                          "ms": round((time.time() - started) * 1000), "tools": job.calls}


def _level(score):
    return score["home"] == score["away"]


# ---- the four pipelines the server calls ---------------------------------------------------------------
async def commentary(ev, ctx, lang, desk):
    """Analyst -> Commentator -> Fact-checker for one impact moment.
    Returns ({"analyst", "casual", "player_cam"} or None, trace)."""
    if not ar.configured():
        return None, None
    facts = ar.event_facts(ev, ctx, lang)
    allowed = set()
    _collect_numbers(facts, allowed)
    job = Job("commentary", lang, facts, allowed, _level(ev["score"]), "Commentator",
              ar.SYSTEM.format(language=LANGUAGE[lang]), structured=PersonaCommentary, desk=desk,
              tools_for=("Analyst",))
    draft, trace = await _run(job, with_analyst=True)
    return (draft.model_dump() if draft else None), trace


async def story(facts, score, lang):
    """Storyteller -> Fact-checker for the story behind a key event."""
    if not ar.configured():
        return None, None
    allowed = set()
    _collect_numbers(facts, allowed)
    job = Job("story", lang, facts, allowed, _level(score), "Storyteller", STORYTELLER.format(language=LANGUAGE[lang]))
    text, trace = await _run(job)
    return (text if text and 20 <= len(text) <= 1500 else None), trace


async def report(rep, lang):
    """Studio analyst -> Fact-checker for the half-time or full-time report."""
    if not ar.configured():
        return None, None
    names = TEAM_NAMES.get(lang, TEAM_NAMES["en"])
    when = "half-time" if rep.get("kind") == "HALF_TIME" else "full-time"
    allowed = set()
    _collect_numbers(rep, allowed)
    facts = {**rep, "team_names": {t: names[t] for t in (rep["home"], rep["away"])}}
    # a level full-time score can follow a lead earlier on, and the story tells it: no lead check there
    level = _level(rep["score"]) and not rep.get("story")
    job = Job("report", lang, facts, allowed, level, "Studio analyst",
              STUDIO.format(language=LANGUAGE[lang], when=when))
    text, trace = await _run(job)
    return (text if text and 20 <= len(text) <= 2000 else None), trace


async def answer(question, desk, context, lang):
    """Match desk (with tools) -> Fact-checker for a viewer's question."""
    if not ar.configured():
        return None, None
    allowed = set()
    _collect_numbers(context, allowed)
    score = context.get("score", {"home": 0, "away": 0})
    job = Job("answer", lang, {"minute": context.get("minute"), "home": context.get("home"), "away": context.get("away"),
                               "score": score, "favourite_club": context.get("favourite_club")},
              allowed, _level(score), "Match desk", DESK.format(language=LANGUAGE[lang]),
              desk=desk, tools_for=("Match desk",), question=question[:500])
    text, trace = await _run(job)
    return (text or None), trace


async def recap(facts, desk, lang):
    """Recap editor (with tools) -> Fact-checker for a periodic recap or a viewer's catch-up."""
    if not ar.configured():
        return None, None
    names = TEAM_NAMES.get(lang, TEAM_NAMES["en"])
    allowed = set()
    _collect_numbers(facts, allowed)
    facts = {**facts, "team_names": {t: names[t] for t in (facts["home"], facts["away"])}}
    job = Job("recap", lang, facts, allowed, _level(facts["score"]), "Recap editor", RECAP.format(language=LANGUAGE[lang]),
              desk=desk, tools_for=("Recap editor",))
    text, trace = await _run(job)
    return (text if text and 20 <= len(text) <= 1200 else None), trace


def mermaid():
    """The two workflow shapes as Mermaid diagrams, for the README."""
    from agent_framework import WorkflowViz
    return WorkflowViz(_workflow(True)).to_mermaid(), WorkflowViz(_workflow(False)).to_mermaid()
