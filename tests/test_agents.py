"""The agent desk without calling Azure: the fact-checker's rules, the live-stats tools, and every
path through the workflows (verified first time, fixed on revision, rejected, an agent failing)."""
import asyncio
from types import SimpleNamespace

import pytest

import agents
from analytics import MatchStats
from generator import AWAY, FORMATIONS, HOME, SQUADS, MatchSim
from persona_router import Context


@pytest.fixture(scope="module")
def match():
    sim = MatchSim(seed=7)
    stats = MatchStats(SQUADS, FORMATIONS, HOME, AWAY)
    recent, impact = [], None
    while (ev := sim.next_event()) is not None:
        stats.update(ev, sim.positions, sim.possession)
        recent.append(ev)
        if impact is None and ev["is_impact_moment"] and ev["event_type"] == "SHOT":
            teams = {t: stats.team_stats(t) for t in (HOME, AWAY)}
            impact = (ev, Context(HOME, AWAY, stats.summary(), dict(sim.positions), HOME, "Thornquist",
                                  stats.player_line(HOME, "Thornquist"),
                                  {t: (teams[t]["xg"], teams[t]["shots"]) for t in teams}, right_team=sim.right_team))
        if ev["minute"] > 40:
            break
    return sim, stats, recent, impact


# ---- fact-checker rules ----------------------------------------------------------------------
def test_fact_checker_accepts_real_numbers_and_their_renderings():
    allowed = set()
    agents._collect_numbers({"xg": 0.13, "length_m": 17.6, "possession": [54, 46], "clock": "34'"}, allowed)
    assert agents.fact_check("A 0.13 xG chance (13%) from 17.6m, with 54% of the ball at 34'.", allowed, False, "en") == []
    assert agents.fact_check("Un disparo de 17,6 m.", allowed, False, "es") == []      # decimal comma
    assert agents.fact_check("２回のタッチ、45分、90分", allowed, False, "ja") == []        # small counts and match time


def test_fact_checker_rejects_invented_numbers_and_false_leads():
    allowed = set()
    agents._collect_numbers({"xg": 0.13, "shots": 9}, allowed)
    assert agents.fact_check("Brackenford have 14 shots.", allowed, False, "en")
    assert agents.fact_check("Brackenford take the lead.", allowed, True, "en")
    assert agents.fact_check("Brackenford amplía la ventaja.", allowed, True, "es")
    assert agents.fact_check("ブラッケンフォードがリード。", allowed, True, "ja")
    assert not agents.fact_check("ブラッケンフォードがポゼッションでリード。", allowed, True, "ja")
    assert not agents.fact_check("This could lead to a chance.", allowed, True, "en")  # "lead to" is not a lead
    assert not agents.fact_check("Brackenford take the lead.", allowed, False, "en")   # fine when not level
    for claim in ("Brackenford go ahead!", "Thornquist puts Brackenford ahead.", "They lead by 2 now."):
        assert agents.fact_check(claim, allowed, True, "en"), claim
    for stat in ("Brackenford are ahead on xG.", "Kestermouth lead in possession.", "Leading the shot count, Brackenford."):
        assert not agents.fact_check(stat, allowed, True, "en"), stat


def test_fact_checker_catches_misspelled_names_but_not_real_ones():
    assert agents.fact_check("Adeo-wlu-Hart tries to thread it.", set(), False, "en")
    assert agents.fact_check("Thornqvist curls it in!", set(), False, "en")
    assert not agents.fact_check("Adewolu-Hart threads it to Thornquist. Kestermouth press.", set(), False, "en")
    assert not agents.fact_check("Brilliant from Felcetti! What a save from Crewdson!", set(), False, "en")
    assert not agents.fact_check("Whitlaker's shot is blocked. Crewdson’s gloves are safe.", set(), False, "en")


def test_fact_checker_keeps_japanese_names_in_latin_letters():
    assert agents.fact_check("アデウォル・ハートがヘディングで狙う。", set(), False, "ja")
    assert not agents.fact_check("Adewolu-Hartがヘディングで狙う。ブラッケンフォードのコーナーキック。", set(), False, "ja")


# ---- tools ------------------------------------------------------------------------------------
def test_tools_read_the_live_match_and_record_what_they_return(match):
    sim, stats, recent, _ = match
    desk = agents.MatchDesk(stats, sim, recent, {}, HOME, AWAY)
    seen, calls = set(), []
    tools = {t.name: t for t in desk.tools(seen, calls)}
    comp = tools["get_team_comparison"](  )
    assert set(comp) >= {HOME, AWAY, "score", "minute"} and comp[HOME]["shots"] == stats.team_stats(HOME)["shots"]
    player = tools["get_player_stats"](player="Quintarelo")
    assert player["name"].endswith("Quintarelo") and "estimated_fitness" in player
    assert "error" in tools["get_player_stats"](player="Nobody")
    assert len(tools["get_recent_events"](count=3)) == 3
    assert tools["get_game_flow"]()["state"] in ("CONTROL", "BALANCED", "CHAOS")
    assert tools["get_tactics"](team="kester")["team"] == AWAY
    assert calls[:2] == ["get_team_comparison", "get_player_stats"] and float(comp[HOME]["shots"]) in seen


# ---- workflows, with stand-in agents instead of the model -----------------------------------------
class FakeAgent:
    """Replies from a script: a list of texts (or exceptions), one per call."""

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    async def run(self, prompt, tools=None, options=None):
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        model = (options or {}).get("response_format")
        if model is agents.Brief:
            return SimpleNamespace(value=agents.Brief(insight=reply), text=reply)
        if model is not None:
            return SimpleNamespace(value=model.model_validate_json(reply), text=reply)
        return SimpleNamespace(value=None, text=reply)


def persona(text):
    return '{"analyst": "%s", "casual": "What a moment!", "player_cam": "Thornquist watches from deep."}' % text


@pytest.fixture
def crew(monkeypatch):
    monkeypatch.setattr(agents.ar, "configured", lambda: True)
    crew = {}
    monkeypatch.setattr(agents, "_crew", lambda: crew)
    return crew


def run(coro):
    return asyncio.run(coro)


def test_commentary_verified_first_time(crew, match):
    sim, stats, recent, (ev, ctx) = match
    xg = f"{ev['metrics']['xg']:.2f}"
    crew["Analyst"] = FakeAgent(["The chance quality matters most."])
    crew["Commentator"] = FakeAgent([persona(f"A {xg} xG effort tests the keeper.")])
    out, trace = run(agents.commentary(ev, ctx, "en", agents.MatchDesk(stats, sim, recent, {}, HOME, AWAY)))
    assert out["analyst"].startswith("A ") and trace["status"] == "passed"
    assert [s["agent"] for s in trace["steps"]] == ["Analyst", "Commentator", "Fact-checker"]
    assert "The Analyst's brief" in crew["Commentator"].prompts[0]


def test_a_wrong_number_is_sent_back_and_fixed(crew, match):
    sim, stats, recent, (ev, ctx) = match
    crew["Analyst"] = FakeAgent(["Big moment."])
    crew["Commentator"] = FakeAgent([persona("They have 987 shots."), persona("A strong effort on goal.")])
    out, trace = run(agents.commentary(ev, ctx, "en", agents.MatchDesk(stats, sim, recent, {}, HOME, AWAY)))
    assert out["analyst"] == "A strong effort on goal." and trace["status"] == "revised"
    assert [s["status"] for s in trace["steps"]] == ["ok", "ok", "revise", "revised", "passed"]
    assert "987" in crew["Commentator"].prompts[1] and "rejected your previous draft" in crew["Commentator"].prompts[1]


def test_a_draft_that_fails_twice_keeps_the_templates(crew, match):
    sim, stats, recent, (ev, ctx) = match
    crew["Analyst"] = FakeAgent(["Big moment."])
    crew["Commentator"] = FakeAgent([persona("They have 987 shots."), persona("Still 987 shots.")])
    out, trace = run(agents.commentary(ev, ctx, "en", agents.MatchDesk(stats, sim, recent, {}, HOME, AWAY)))
    assert out is None and trace["status"] == "rejected" and trace["steps"][-1]["status"] == "rejected"


def test_a_failing_agent_is_recovered_from(crew, match):
    sim, stats, recent, (ev, ctx) = match
    crew["Analyst"] = FakeAgent([ConnectionError("network down")])
    out, trace = run(agents.commentary(ev, ctx, "en", agents.MatchDesk(stats, sim, recent, {}, HOME, AWAY)))
    assert out is None and trace["status"] == "error" and trace["steps"][-1]["agent"] == "Orchestrator"


def test_stories_reports_and_answers_go_through_the_fact_checker(crew, match):
    sim, stats, recent, _ = match
    level = {"home": 0, "away": 0}
    crew["Storyteller"] = FakeAgent(["Brackenford took the lead after a lovely move down the right flank.",
                                     "A lovely move down the right flank ended with a save."])
    text, trace = run(agents.story({"moment": {"score": level}}, level, "en"))
    assert text.startswith("A lovely move") and trace["status"] == "revised"   # false lead caught and fixed

    rep = stats.report(recent[-1]) | {"kind": "HALF_TIME", "score": level}
    crew["Studio analyst"] = FakeAgent(["An even half so far, with chances at both ends and no goals yet."])
    text, trace = run(agents.report(rep, "es"))
    assert text and trace["status"] == "passed"

    crew["Match desk"] = FakeAgent(["Both sides are pressing hard so far in this game."])
    desk = agents.MatchDesk(stats, sim, recent, {}, HOME, AWAY)
    text, trace = run(agents.answer("Who is pressing better?", desk, {"score": level, "home": HOME, "away": AWAY}, "en"))
    assert text and trace["status"] == "passed"


def test_nothing_runs_without_keys(monkeypatch, match):
    monkeypatch.setattr(agents.ar, "configured", lambda: False)
    sim, stats, recent, (ev, ctx) = match
    assert run(agents.commentary(ev, ctx, "en", None)) == (None, None)


def test_the_workflows_can_be_drawn():
    moment, narrative = agents.mermaid()
    assert "analyst" in moment and "fact_checker" in moment and "writer" in narrative


def test_recaps_go_through_the_recap_editor_and_the_fact_checker(crew, match):
    sim, stats, recent, _ = match
    level = {"home": 0, "away": 0}
    facts = {"kind": "CATCHUP", "start": "12'", "end": "30'", "clock": "30'", "score": level, "home": HOME, "away": AWAY,
             "xg": [0.4, 0.2], "shots": [4, 2], "possession": [55, 45], "momentum": 20, "moments": [],
             "viewer": {"mode": "Casual", "favourite_club": HOME, "followed_player": None}}
    crew["Recap editor"] = FakeAgent(["While you were away it stayed level, with 4 shots to 2."])
    text, trace = run(agents.recap(facts, agents.MatchDesk(stats, sim, recent, {}, HOME, AWAY), "en"))
    assert text.startswith("While you were away") and trace["status"] == "passed"
    assert "CATCHUP" in crew["Recap editor"].prompts[0] and "Casual" in crew["Recap editor"].prompts[0]


def test_every_pipeline_is_traced_with_its_outcome(crew, match):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter, provider = InMemorySpanExporter(), TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    old = agents._tracer
    agents._tracer = tracer
    try:
        sim, stats, recent, (ev, ctx) = match
        crew["Analyst"] = FakeAgent(["Big moment."])
        crew["Commentator"] = FakeAgent([persona("They have 987 shots."), persona("A strong effort on goal.")])
        run(agents.commentary(ev, ctx, "en", agents.MatchDesk(stats, sim, recent, {}, HOME, AWAY)))
    finally:
        agents._tracer = old
    span = next(s for s in exporter.get_finished_spans() if s.name == "secondtouch commentary")
    assert span.attributes["secondtouch.status"] == "revised" and span.attributes["secondtouch.revisions"] == 1
    assert list(span.attributes["secondtouch.agents"]) == ["Analyst", "Commentator", "Fact-checker", "Commentator", "Fact-checker"]


def test_tracing_is_off_without_a_connection_string(monkeypatch):
    import telemetry
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    assert telemetry.setup() is False
