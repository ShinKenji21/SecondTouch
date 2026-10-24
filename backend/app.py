"""Stage 4 - FastAPI WebSocket server.

Each connection runs its own match. The sender loop generates an event,
updates the statistics, renders the three personas, alerts, key-event story
and any half-time/full-time report from templates, builds the overlay cues and
sends it all at once. The agent desk (agents.py: Microsoft Agent Framework on
Microsoft Foundry) then upgrades impact moments, stories and reports in the
background, so the AI never holds up the stream; each run's trace is sent too.
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

try:  # optional: load AZURE_OPENAI_* from .env
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import agent_reasoner
import agents
import overlays
import telemetry
from analytics import MatchStats, is_key_event
from generator import AWAY, FORMATIONS, HOME, SQUADS, MatchSim
from models import ClientConfig, Event
from persona_router import LANG_NAMES, TEAM_NAMES, Context, alert_text, recap_text, render, report_text, story

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("secondtouch")
# Agent Framework and httpx log every workflow step, tool call and request at INFO; keep the terminal readable
for noisy in ("agent_framework", "httpx", "httpx2", "azure"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
TRACING = telemetry.setup()

HERE = Path(__file__).resolve().parent
FRONTEND_DIR = HERE.parent / "frontend"
DEFAULT_INTERVAL = min(2.0, max(1.0, float(os.getenv("EVENT_INTERVAL_S", "1.5"))))
VALIDATE = os.getenv("VALIDATE_EVENTS") == "1"
# Credit guard: the stream plays match after match for as long as a tab is open, so the model only
# writes for the first few matches of each visit and never while the tab is hidden. Talk to AI is
# always answered, since someone asked.
AI_MATCHES_PER_VIEWER = int(os.getenv("AI_MATCHES_PER_VIEWER", "2"))
# a recap every quarter of an hour (half-time and full-time have their own reports): (half, minute)
RECAP_AT = ((1, 15), (1, 30), (2, 60), (2, 75))
MODE_NAME = {"ANALYST": "Analyst", "CASUAL": "Casual", "PLAYER_CAM": "Player Cam"}

app = FastAPI(title="SecondTouch")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.middleware("http")
async def no_stale_frontend(request, call_next):
    """Make the browser revalidate the page and its scripts, so edits show up on a normal refresh."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
async def get_dashboard():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/squads")
async def get_squads():
    return {"squads": SQUADS, "formations": FORMATIONS, "home": HOME, "away": AWAY}


@app.get("/api/overlay-schema")
async def overlay_schema():
    return {"version": overlays.SCHEMA_VERSION, "doc": overlays.__doc__}


class Session:
    def __init__(self, ws):
        self.ws = ws
        self.cfg = {"mode": "PLAYER_CAM", "team": HOME, "player": "Thornquist", "speed": 1,
                    "lang": "en", "interval": DEFAULT_INTERVAL, "fav_team": "NONE"}
        self.lock = asyncio.Lock()
        self.wake = asyncio.Event()
        self.match_id = 0
        self.last = None   # everything needed to re-render the latest event's text
        self.recent = []   # last few events for the Talk to AI context
        self.new_match()

    def new_match(self):
        self.match_id += 1
        self.sim = MatchSim()
        self.stats = MatchStats(SQUADS, FORMATIONS, HOME, AWAY)
        self.last, self.recent, self.reports = None, [], {}
        self.recaps = []      # (seq, clock) of each recap sent this match
        self.clock_at = {}    # seq -> clock, to say where a catch-up starts

    async def send(self, obj):
        async with self.lock:
            await self.ws.send_text(json.dumps(obj, ensure_ascii=False))

    def ai_allowed(self):
        """Whether the model may write for this viewer now (see AI_MATCHES_PER_VIEWER)."""
        return self.cfg.get("visible", True) and self.match_id <= AI_MATCHES_PER_VIEWER

    def fav(self):
        return None if self.cfg["fav_team"] == "NONE" else self.cfg["fav_team"]

    def context(self):
        team, player = self.cfg["team"], self.cfg["player"]
        teams = {t: self.stats.team_stats(t) for t in (HOME, AWAY)}
        return Context(
            HOME, AWAY, self.stats.summary(), self.sim.positions, team, player,
            self.stats.player_line(team, player),
            {t: (teams[t]["xg"], teams[t]["shots"]) for t in (HOME, AWAY)},
            right_team=self.sim.right_team, fav_team=self.fav(),
        )

    def lines(self):
        return {(t, pid): self.stats.player_line(t, pid) for t in (HOME, AWAY) for pid in SQUADS[t]}

    def texts(self, ev, ctx, alerts, buildup, report, lines, lang):
        """All language-dependent text for one event."""
        out = {
            "commentary": render(ev, ctx, lang),
            "alerts": [dict(a, text=alert_text(a, lang)) for a in alerts],
            "story": story(ev, buildup, ctx, lines, lang) if is_key_event(ev) else None,
            "report": dict(report, narrative=report_text(report, lang)) if report else None,
        }
        return out

    def local_i18n(self, ev, ctx, buildup, report, lines):
        """The template text of one event in every language, so the viewer can switch language and the
        whole match so far follows, not only what comes next."""
        out = {}
        for lang in LANG_NAMES:
            out[lang] = {"commentary": {**render(ev, ctx, lang), "source": "LOCAL ENGINE", "lang": lang},
                         "story": story(ev, buildup, ctx, lines, lang) if is_key_event(ev) else None,
                         "report_narrative": report_text(report, lang) if report else None}
        return out

    # ---- sender ------------------------------------------------------------
    async def run(self):
        await self.send({"type": "hello", "ai_configured": agent_reasoner.configured(),
                         "deployment": agent_reasoner._deployment() if agent_reasoner.configured() else None,
                         "interval": self.cfg["interval"], "squads": SQUADS, "formations": FORMATIONS,
                         "home": HOME, "away": AWAY})
        await self.send_match_start()
        while True:
            speed = self.cfg["speed"]
            focus = self.cfg["mode"] == "PLAYER_CAM"
            ev = self.sim.next_event(self.cfg["team"], self.cfg["player"], 0.5 if focus else 0.0)
            if ev is None:  # full time was sent last tick: leave time to read the report, then a new match
                await self.sleep(max(8, 20 / speed))
                self.new_match()
                await self.send_match_start()
                continue
            if VALIDATE:
                Event.model_validate(ev)
            self.stats.update(ev, self.sim.positions, self.sim.possession)
            ctx = self.context()
            lang = self.cfg["lang"]
            alerts, buildup = list(self.stats.alerts), list(self.stats.buildup)
            report = self.stats.report(ev) if ev["event_type"] in ("HALF_TIME", "FULL_TIME") else None
            lines = self.lines()
            texts = self.texts(ev, ctx, alerts, buildup, report, lines, lang)
            self.last = (ev, ctx, alerts, buildup, report, lines)
            self.recent = (self.recent + [ev])[-8:]
            self.clock_at[ev["seq"]] = ev["clock"]
            if report:
                self.reports[ev["event_type"]] = texts["report"]
            interval_ms = round(self.cfg["interval"] * 1000 / speed)
            await self.send({
                "type": "event", "match_id": self.match_id, "event": ev,
                "positions": self.sim.positions, "possession": self.sim.possession,
                "ball": [round(self.sim.ball[0], 1), round(self.sim.ball[1], 1)],  # where play continues from
                "commentary": {**texts["commentary"], "source": "LOCAL ENGINE", "lang": lang},
                "alerts": texts["alerts"], "story": texts["story"], "report": texts["report"],
                "i18n": self.local_i18n(ev, ctx, buildup, report, lines),
                "overlays": overlays.build(ev, self.sim.positions, texts["commentary"], texts["alerts"],
                                           texts["story"], texts["report"], interval_ms),
                "summary": ctx.summary, "stats": self.stats.snapshot(),
                "fitness": self.sim.fitness(), "stance": dict(self.sim.stance),
                "subs_used": dict(self.sim.subs_used),
                "sent_at": time.time() * 1000,
            })
            if self.recap_due(ev):
                await self.send_recap(ev)
            if agent_reasoner.configured() and self.ai_allowed():
                if ev["is_impact_moment"] and speed == 1:
                    asyncio.create_task(self.upgrade(ev, ctx, lang, self.match_id))
                if texts["story"] and speed == 1:
                    asyncio.create_task(self.upgrade_story(ev, buildup, lines, lang, self.match_id))
                if report:
                    asyncio.create_task(self.upgrade_report(ev, report, lang, self.match_id))
            pause = max(4, 12 / speed) if ev["event_type"] == "HALF_TIME" else self.cfg["interval"] / speed
            await self.sleep(pause)

    async def send_match_start(self):
        await self.send({"type": "match_start", "match_id": self.match_id, "metadata": self.sim.metadata})

    async def sleep(self, seconds):
        """Sleep, but wake early when the viewer changes speed."""
        self.wake.clear()
        try:
            await asyncio.wait_for(self.wake.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def _current(self, match_id, lang):
        """Still the same match. A result in a language the viewer has since left is still sent, tagged
        with its language: the page keeps it and shows it again if they switch back."""
        return match_id == self.match_id and lang in LANG_NAMES

    def desk(self):
        """The live match as the agents' tools see it."""
        return agents.MatchDesk(self.stats, self.sim, list(self.recent), self.reports, HOME, AWAY)

    async def report_run(self, kind, ev, match_id, pipeline):
        """Every agent run is reported, including the ones that fell back to templates."""
        if pipeline and match_id == self.match_id:
            await self.send({"type": "agent_run", "match_id": match_id, "seq": ev["seq"], "clock": ev["clock"],
                             "kind": kind, "pipeline": pipeline})

    async def upgrade(self, ev, ctx, lang, match_id):
        ai, pipeline = await agents.commentary(ev, ctx, lang, self.desk())
        await self.report_run("commentary", ev, match_id, pipeline)
        if ai and self._current(match_id, lang):
            await self.send({"type": "commentary", "match_id": match_id, "seq": ev["seq"],
                             "commentary": {**ai, "source": "AZURE OPENAI", "lang": lang},
                             "pipeline": pipeline, "ai_ms": pipeline["ms"]})

    async def upgrade_story(self, ev, buildup, lines, lang, match_id):
        facts = {"moment": {k: ev.get(k) for k in ("clock", "team", "player", "event_type", "outcome", "opponent",
                                                   "player_off", "card", "set_piece", "restart", "restart_team",
                                                   "body_part", "tags", "var", "reshuffle", "length_m", "score")},
                 "xg": ev["metrics"]["xg"], "build_up": buildup,
                 "players": {f"{t}:{p}": v for (t, p), v in lines.items()
                             if p in (ev["player"], ev["opponent"], ev["player_off"]) and v}}
        text, pipeline = await agents.story(facts, ev["score"], lang)
        await self.report_run("story", ev, match_id, pipeline)
        if text and self._current(match_id, lang):
            await self.send({"type": "story", "match_id": match_id, "seq": ev["seq"], "story": text,
                             "source": "AZURE OPENAI", "lang": lang, "pipeline": pipeline})

    # ---- recaps and catch-ups --------------------------------------------------------
    def recap_due(self, ev):
        if ev["event_type"] in ("HALF_TIME", "FULL_TIME"):
            return False
        done = len(self.recaps)
        return done < len(RECAP_AT) and ev["period"] == RECAP_AT[done][0] and ev["minute"] >= RECAP_AT[done][1]

    def recap_facts(self, kind, since_seq, start, ev):
        """The stretch of play since `since_seq`, the numbers now, and who is watching."""
        s = self.stats.summary()
        mode, fav = self.cfg["mode"], self.fav()
        return {"kind": kind, "start": start, "end": ev["clock"], "clock": ev["clock"], "score": ev["score"],
                "home": HOME, "away": AWAY, "xg": s["xg"], "shots": s["shots"], "possession": s["possession"],
                "momentum": s["momentum"], "fav_team": fav,
                "moments": [m for m in self.stats.key_moments if m["seq"] > since_seq][-8:],
                "viewer": {"mode": MODE_NAME[mode], "favourite_club": fav,
                           "followed_player": self.cfg["player"] if mode == "PLAYER_CAM" else None}}

    async def send_recap(self, ev):
        since, start = self.recaps[-1] if self.recaps else (0, "0'")
        self.recaps.append((ev["seq"], ev["clock"]))
        facts, lang = self.recap_facts("PERIODIC", since, start, ev), self.cfg["lang"]
        await self.send({"type": "recap", "match_id": self.match_id, "seq": ev["seq"], "clock": ev["clock"],
                         "kind": "periodic", "text": recap_text(facts, lang), "source": "LOCAL ENGINE", "lang": lang,
                         "i18n": {k: recap_text(facts, k) for k in LANG_NAMES}})
        if agent_reasoner.configured() and self.ai_allowed():
            asyncio.create_task(self.upgrade_recap(ev, facts, lang, self.match_id))

    async def upgrade_recap(self, ev, facts, lang, match_id):
        text, pipeline = await agents.recap(facts, self.desk(), lang)
        await self.report_run("recap", ev, match_id, pipeline)
        if text and self._current(match_id, lang):
            await self.send({"type": "recap", "match_id": match_id, "seq": ev["seq"], "clock": ev["clock"],
                             "kind": "periodic", "text": text, "source": "AZURE OPENAI", "lang": lang, "pipeline": pipeline})

    async def catchup(self, msg):
        """A viewer is back after missing part of the match: what happened while they were away, for them."""
        if not self.last:
            return
        ev = self.last[0]
        try:
            since = int(msg.get("since_seq") or 0)
        except (TypeError, ValueError):
            return
        if ev["seq"] - since < 4:
            return
        start = self.clock_at.get(since + 1) or self.clock_at.get(since) or "0'"
        facts, lang, match_id = self.recap_facts("CATCHUP", since, start, ev), self.cfg["lang"], self.match_id
        reply = {"type": "catchup", "id": msg.get("id"), "match_id": match_id, "start": start, "end": ev["clock"], "lang": lang}
        await self.send({**reply, "text": recap_text(facts, lang), "source": "LOCAL ENGINE"})
        if agent_reasoner.configured():  # someone is watching and asked, so the per-visit limit does not apply
            text, pipeline = await agents.recap(facts, self.desk(), lang)
            await self.report_run("catchup", ev, match_id, pipeline)
            if text and self._current(match_id, lang) and lang == self.cfg["lang"]:
                await self.send({**reply, "text": text, "source": "AZURE OPENAI", "pipeline": pipeline})

    async def upgrade_report(self, ev, report, lang, match_id):
        text, pipeline = await agents.report(report, lang)
        await self.report_run("report", ev, match_id, pipeline)
        if text and self._current(match_id, lang):
            if ev["event_type"] in self.reports and lang == self.cfg["lang"]:
                self.reports[ev["event_type"]]["narrative"] = text
            await self.send({"type": "report", "match_id": match_id, "seq": ev["seq"], "narrative": text,
                             "source": "AZURE OPENAI", "lang": lang, "pipeline": pipeline})

    # ---- receiver ------------------------------------------------------------
    async def receive(self):
        while True:
            try:
                msg = json.loads(await self.ws.receive_text())
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "ask":
                asyncio.create_task(self.answer(msg))
                continue
            if msg.get("type") == "catchup":
                asyncio.create_task(self.catchup(msg))
                continue
            try:
                cfg = ClientConfig.model_validate(msg)
            except ValidationError:
                continue
            changed = {k: v for k, v in cfg.model_dump().items() if v is not None and v != self.cfg.get(k)}
            self.cfg.update(changed)
            if "speed" in changed:
                self.wake.set()
            if self.last and changed.keys() & {"lang", "team", "player", "fav_team"}:
                await self.rerender()

    async def rerender(self):
        """Re-send the latest event's text for a new language, focus player or favourite club, instantly."""
        ev, ctx, alerts, buildup, report, lines = self.last
        ctx.focus_team, ctx.focus_player = self.cfg["team"], self.cfg["player"]
        ctx.focus_line = self.stats.player_line(ctx.focus_team, ctx.focus_player)
        ctx.positions, ctx.fav_team = self.sim.positions, self.fav()
        lang = self.cfg["lang"]
        texts = self.texts(ev, ctx, alerts, buildup, report, lines, lang)
        await self.send({"type": "commentary", "match_id": self.match_id, "seq": ev["seq"],
                         "commentary": {**texts["commentary"], "source": "LOCAL ENGINE", "lang": lang},
                         "alerts": texts["alerts"], "story": texts["story"],
                         "report_narrative": texts["report"]["narrative"] if texts["report"] else None})

    async def answer(self, msg):
        question = str(msg.get("question", ""))[:500].strip()
        if not question:
            return
        lang = self.cfg["lang"]
        text, pipeline = await agents.answer(question, self.desk(), self.match_context(), lang)
        source = "AZURE OPENAI"
        if text is None:  # a suggestion clicked in Spanish or Japanese carries its English question as a hint
            hint = str(msg.get("hint") or "")[:200]
            text, source = self.local_answer(hint or question), "LOCAL ENGINE"
        await self.send({"type": "answer", "id": msg.get("id"), "text": text, "source": source, "pipeline": pipeline})

    # ---- Talk to AI ------------------------------------------------------------
    def match_context(self):
        snap = self.stats.snapshot()
        players = {
            t: [{k: p[k] for k in ("name", "pos", "minutes", "rating", "goals", "assists", "shots", "xg",
                                   "passes_completed", "passes", "tackles_won", "touches", "sprints",
                                   "distance_km", "top_speed")}
                for p in snap["players"][t] if p["minutes"]]
            for t in (HOME, AWAY)
        }
        tactics = {t: {k: v for k, v in snap["tactics"][t].items() if k != "avg_positions"} for t in (HOME, AWAY)}
        fitness = self.sim.fitness()
        for t in (HOME, AWAY):
            for p in players[t]:
                p["fitness"] = fitness[t].get(p["name"].split()[-1]) if p["name"] else None
        return {
            "minute": self.stats.minute, "home": HOME, "away": AWAY, "metadata": self.sim.metadata,
            "score": self.last[0]["score"] if self.last else {"home": 0, "away": 0},
            "summary": self.stats.summary(), "teams": snap["teams"], "tactics": tactics,
            "players": players, "favourite_club": self.fav(),
            "estimated_fitness_on_pitch": fitness, "subs_used": self.sim.subs_used,
            "team_shape_now": {t: {"BALANCED": "balanced", "CHASING": "pushing forward",
                                   "PROTECTING": "sitting deep"}[st] for t, st in self.sim.stance.items()},
            "added_time": {f"half_{k}": v for k, v in self.sim.added.items() if v is not None},
            "reports": {k: v["narrative"] for k, v in self.reports.items()},
            "recent_events": [{k: e.get(k) for k in ("clock", "team", "player", "event_type", "outcome", "set_piece",
                                                     "restart", "card", "tags", "var", "impact_reasons")}
                              for e in self.recent],
        }

    def local_answer(self, question):
        q = question.lower()
        snap = self.stats.snapshot()
        names = TEAM_NAMES["en"]
        if not self.last:
            return "The match hasn't started yet. Press START MATCH first."
        for team in (HOME, AWAY):
            for p in snap["players"][team]:
                if p["id"].lower() in q or p["name"].lower() in q or p["name"].split()[-1].lower() in q:
                    if p["minutes"] and any(w in q for w in ("foul", "card", "booked", "offside")):
                        return (f"{p['name']} ({names[team]}): {p['fouls']} fouls committed, {p['fouls_won']} won, "
                                f"{p['yellow']} yellow, {p['red']} red, caught offside {p['offsides']} times.")
                    if not p["minutes"]:
                        return f"{p['name']} hasn't played yet."
                    return (f"{p['name']} ({names[team]}, {p['pos']}): {p['minutes']} min, rating {p['rating']}, "
                            f"{p['goals']} goals, {p['shots']} shots ({p['on_target']} on target, {p['xg']:.2f} xG), "
                            f"{p['passes_completed']}/{p['passes']} passes, {p['tackles_won']} tackles won, "
                            f"{p['touches']} touches, {p['sprints']} sprints, {p['distance_km']} km covered, "
                            f"top speed {p['top_speed']:.1f} km/h.")
        s = self.stats.summary()
        t = snap["teams"]
        mom = s["momentum"]
        lead = names[HOME] if mom > 0 else names[AWAY]
        mom_text = (f"{lead} have the momentum ({abs(mom)}/100)." if abs(mom) >= 20
                    else "Momentum is fairly even right now.")
        if any(w in q for w in ("report", "summary", "recap", "half")) and self.reports:
            latest = self.reports.get("FULL_TIME") or self.reports.get("HALF_TIME")
            return latest["narrative"]
        if any(w in q for w in ("so far", "happened", "summary", "recap", "catch me up")):
            return recap_text(self.recap_facts("PERIODIC", 0, "0'", self.last[0]), "en")
        if "best" in q or "player of the match" in q or "standing out" in q:
            on = [(p, team) for team in (HOME, AWAY) for p in snap["players"][team] if p["minutes"]]
            top = sorted(on, key=lambda pt: pt[0]["rating"], reverse=True)[:3]
            lead, team = top[0]
            return (f"{lead['name']} ({names[team]}, {lead['pos']}) has the best rating so far: {lead['rating']}, with "
                    f"{lead['goals']} goals, {lead['shots']} shots and {lead['passes_completed']}/{lead['passes']} passes. "
                    "Next: " + ", ".join(f"{p['name']} {p['rating']}" for p, _ in top[1:]) + ".")
        if any(w in q for w in ("chaos", "control", "tempo", "rhythm", "flow")):
            f = s["flow"]
            state = {"CONTROL": f"{names.get(f['state_team'], '')} are in control",
                     "CHAOS": "the game is chaotic", "BALANCED": "the game is balanced"}[f["state"]]
            return (f"Right now {state}: {f['turnover_rate']}% of recent actions changed possession. "
                    f"Tempo is {f['tempo'].lower()}. Pressure index applied: {names[HOME]} {f['press'][HOME]}, "
                    f"{names[AWAY]} {f['press'][AWAY]}.")
        if any(w in q for w in ("press", "tactic", "formation", "shape", "line", "width")):
            parts = []
            for team in (HOME, AWAY):
                tac = snap["tactics"][team]
                oop = tac["out_of_possession"] or {}
                ch = tac["channels"]
                fav = max(ch, key=ch.get)
                parts.append(f"{names[team]} ({tac['formation']}) defend with a line {oop.get('line_height_m', '-')}m "
                             f"from goal, PPDA {tac['ppda'] or '-'}, and attack mostly down the {fav} ({ch[fav]}%).")
            return " ".join(parts)
        if any(w in q for w in ("tired", "fitness", "fatigue", "energy", "legs")):
            fit = self.sim.fitness()
            parts = []
            for team in (HOME, AWAY):
                worst = sorted(fit[team].items(), key=lambda kv: kv[1])[:3]
                parts.append(f"{names[team]}: lowest estimated fitness " + ", ".join(f"{p} {v}%" for p, v in worst)
                             + f" ({self.sim.subs_used[team]} of {self.sim.metadata['max_subs']} subs used).")
            return " ".join(parts)
        if "var" in q.split() or "disallow" in q or "woodwork" in q or "post" in q.split():
            return (f"Goals ruled out by VAR: {names[HOME]} {t[HOME]['goals_disallowed']}, {names[AWAY]} {t[AWAY]['goals_disallowed']}. "
                    f"Woodwork: {names[HOME]} {t[HOME]['woodwork']}, {names[AWAY]} {t[AWAY]['woodwork']}.")
        shape = {"BALANCED": "balanced", "CHASING": "pushing forward", "PROTECTING": "sitting deep"}
        if any(w in q for w in ("sub", "change", "bench")):
            return (f"Substitutions: {names[HOME]} {self.sim.subs_used[HOME]}, {names[AWAY]} {self.sim.subs_used[AWAY]} "
                    f"(of {self.sim.metadata['max_subs']}). Shape now: {names[HOME]} {shape[self.sim.stance[HOME]]}, "
                    f"{names[AWAY]} {shape[self.sim.stance[AWAY]]}.")
        if any(w in q for w in ("corner", "set piece", "set-piece", "free kick", "throw", "penalt", "offside",
                                "foul", "card", "goal kick")):
            def n(count, word):
                return f"{count} {word}" if count == 1 else f"{count} {word}s"

            def line(team):
                x = t[team]
                return (f"{names[team]}: {n(x['corners'], 'corner')}, {n(x['free_kicks'], 'free kick')}, "
                        f"{n(x['throw_ins'], 'throw-in')}, {x['penalties']} {'penalty' if x['penalties'] == 1 else 'penalties'}, "
                        f"{n(x['goal_kicks'], 'goal kick')}, {n(x['offsides'], 'offside')}, {n(x['fouls'], 'foul')}, "
                        f"{x['yellow']} yellow and {x['red']} red {'card' if x['yellow'] + x['red'] == 1 else 'cards'}.")
            return f"{line(HOME)} {line(AWAY)}"
        if any(w in q for w in ("xg", "chance", "shot")):
            return (f"xG {names[HOME]} {s['xg'][0]:.2f} from {t[HOME]['shots']} shots, "
                    f"{names[AWAY]} {s['xg'][1]:.2f} from {t[AWAY]['shots']} shots. {mom_text}")
        if any(w in q for w in ("momentum", "on top", "dominat")):
            return f"{mom_text} Possession {s['possession'][0]}-{s['possession'][1]}."
        ev = self.last[0]
        return (f"{ev['clock']}: {names[HOME]} {ev['score']['home']}-{ev['score']['away']} {names[AWAY]}, "
                f"xG {s['xg'][0]:.2f}-{s['xg'][1]:.2f}, possession {s['possession'][0]}-{s['possession'][1]}. "
                f"{mom_text} (Local engine: add Azure OpenAI keys for free-form answers.)")


@app.websocket("/ws/telemetry")
async def telemetry(ws: WebSocket):
    await ws.accept()
    session = Session(ws)
    recv_task = asyncio.create_task(session.receive())
    send_task = asyncio.create_task(session.run())
    try:
        done, _ = await asyncio.wait({recv_task, send_task}, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            exc = t.exception()
            if exc and not isinstance(exc, (WebSocketDisconnect, RuntimeError)):
                log.exception("session ended with an error", exc_info=exc)
    finally:
        recv_task.cancel()
        send_task.cancel()


if __name__ == "__main__":
    log.info("Azure OpenAI %s", "configured" if agent_reasoner.configured() else "not configured, using local templates")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
