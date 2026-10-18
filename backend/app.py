"""Stage 4 - FastAPI WebSocket server.

Each connection runs its own match. The sender loop generates an event,
updates the statistics, renders the three personas from templates and sends
it at once; impact moments are then upgraded with Azure OpenAI text in the
background, so the AI never holds up the stream.
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
from analytics import MatchStats
from generator import AWAY, FORMATIONS, HOME, SQUADS, MatchSim
from models import ClientConfig, Event
from persona_router import TEAM_NAMES, Context, render

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("secondtouch")

HERE = Path(__file__).resolve().parent
FRONTEND_DIR = HERE.parent / "frontend"
DEFAULT_INTERVAL = min(2.0, max(1.0, float(os.getenv("EVENT_INTERVAL_S", "1.5"))))
VALIDATE = os.getenv("VALIDATE_EVENTS") == "1"

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


class Session:
    def __init__(self, ws):
        self.ws = ws
        self.cfg = {"mode": "PLAYER_CAM", "team": HOME, "player": "Saka", "speed": 1,
                    "lang": "en", "interval": DEFAULT_INTERVAL}
        self.lock = asyncio.Lock()
        self.wake = asyncio.Event()
        self.match_id = 0
        self.last = None  # (event, context) of the latest event, for re-rendering
        self.recent = []  # last few events for the Talk to AI context
        self.new_match()

    def new_match(self):
        self.match_id += 1
        self.sim = MatchSim()
        self.stats = MatchStats(SQUADS, FORMATIONS, HOME, AWAY)
        self.last, self.recent = None, []

    async def send(self, obj):
        async with self.lock:
            await self.ws.send_text(json.dumps(obj, ensure_ascii=False))

    def context(self, ev):
        team, player = self.cfg["team"], self.cfg["player"]
        teams = {t: self.stats.team_stats(t) for t in (HOME, AWAY)}
        return Context(
            HOME, AWAY, self.stats.summary(), self.sim.positions, team, player,
            self.stats.player_line(team, player),
            {t: (teams[t]["xg"], teams[t]["shots"]) for t in (HOME, AWAY)},
        )

    # ---- sender ------------------------------------------------------------
    async def run(self):
        await self.send({"type": "hello", "ai_configured": agent_reasoner.configured(),
                         "deployment": agent_reasoner._deployment() if agent_reasoner.configured() else None,
                         "interval": self.cfg["interval"], "squads": SQUADS, "formations": FORMATIONS,
                         "home": HOME, "away": AWAY})
        while True:
            speed = self.cfg["speed"]
            focus = self.cfg["mode"] == "PLAYER_CAM"
            ev = self.sim.next_event(self.cfg["team"], self.cfg["player"], 0.5 if focus else 0.0)
            if ev is None:  # full time was sent last tick: leave time to read the stats, then a new match
                await self.sleep(max(8, 20 / speed))
                self.new_match()
                continue
            if VALIDATE:
                Event.model_validate(ev)
            self.stats.update(ev, self.sim.positions, self.sim.possession)
            ctx = self.context(ev)
            lang = self.cfg["lang"]
            commentary = render(ev, ctx, lang)
            self.last = (ev, ctx)
            self.recent = (self.recent + [ev])[-8:]
            await self.send({
                "type": "event", "match_id": self.match_id, "event": ev,
                "positions": self.sim.positions, "possession": self.sim.possession,
                "commentary": {**commentary, "source": "LOCAL ENGINE", "lang": lang},
                "summary": ctx.summary, "stats": self.stats.snapshot(),
                "sent_at": time.time() * 1000,
            })
            if ev["is_impact_moment"] and speed == 1 and agent_reasoner.configured():
                asyncio.create_task(self.upgrade(ev, ctx, lang, self.match_id))
            await self.sleep(self.cfg["interval"] / speed)

    async def sleep(self, seconds):
        """Sleep, but wake early when the viewer changes speed."""
        self.wake.clear()
        try:
            await asyncio.wait_for(self.wake.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def upgrade(self, ev, ctx, lang, match_id):
        started = time.time()
        ai = await agent_reasoner.persona_commentary(ev, ctx, lang)
        if not ai or match_id != self.match_id or lang != self.cfg["lang"]:
            return
        await self.send({"type": "commentary", "match_id": match_id, "seq": ev["seq"],
                         "commentary": {**ai, "source": "AZURE OPENAI", "lang": lang},
                         "ai_ms": round((time.time() - started) * 1000)})

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
            try:
                cfg = ClientConfig.model_validate(msg)
            except ValidationError:
                continue
            changed = {k: v for k, v in cfg.model_dump().items() if v is not None and v != self.cfg.get(k)}
            self.cfg.update(changed)
            if "speed" in changed:
                self.wake.set()
            if self.last and changed.keys() & {"lang", "team", "player"}:
                await self.rerender()

    async def rerender(self):
        """Re-send the latest event's commentary for a new language or focus player, instantly."""
        ev, ctx = self.last
        ctx.focus_team, ctx.focus_player = self.cfg["team"], self.cfg["player"]
        ctx.focus_line = self.stats.player_line(ctx.focus_team, ctx.focus_player)
        ctx.positions = self.sim.positions
        commentary = render(ev, ctx, self.cfg["lang"])
        await self.send({"type": "commentary", "match_id": self.match_id, "seq": ev["seq"],
                         "commentary": {**commentary, "source": "LOCAL ENGINE", "lang": self.cfg["lang"]}})

    async def answer(self, msg):
        question = str(msg.get("question", ""))[:500].strip()
        if not question:
            return
        lang = self.cfg["lang"]
        text = await agent_reasoner.answer_question(question, self.match_context(), lang)
        source = "AZURE OPENAI"
        if text is None:
            text, source = self.local_answer(question), "LOCAL ENGINE"
        await self.send({"type": "answer", "id": msg.get("id"), "text": text, "source": source})

    # ---- Talk to AI ------------------------------------------------------------
    def match_context(self):
        snap = self.stats.snapshot()
        players = {
            t: [{k: p[k] for k in ("name", "pos", "minutes", "rating", "goals", "assists", "shots", "xg",
                                   "passes_completed", "passes", "tackles_won", "touches", "sprints")}
                for p in snap["players"][t] if p["minutes"]]
            for t in (HOME, AWAY)
        }
        tactics = {t: {k: v for k, v in snap["tactics"][t].items() if k != "avg_positions"} for t in (HOME, AWAY)}
        return {
            "minute": self.stats.minute, "home": HOME, "away": AWAY,
            "score": self.last[0]["score"] if self.last else {"home": 0, "away": 0},
            "summary": self.stats.summary(), "teams": snap["teams"], "tactics": tactics,
            "players": players,
            "recent_events": [{k: e[k] for k in ("clock", "team", "player", "event_type", "outcome", "impact_reasons")}
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
                    if not p["minutes"]:
                        return f"{p['name']} hasn't played yet."
                    return (f"{p['name']} ({names[team]}, {p['pos']}): {p['minutes']} min, rating {p['rating']}, "
                            f"{p['goals']} goals, {p['shots']} shots ({p['on_target']} on target, {p['xg']:.2f} xG), "
                            f"{p['passes_completed']}/{p['passes']} passes, {p['tackles_won']} tackles won, "
                            f"{p['touches']} touches, {p['sprints']} sprints.")
        s = self.stats.summary()
        t = snap["teams"]
        mom = s["momentum"]
        lead = names[HOME] if mom > 0 else names[AWAY]
        mom_text = (f"{lead} have the momentum ({abs(mom)}/100)." if abs(mom) >= 20
                    else "Momentum is fairly even right now.")
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
        if any(w in q for w in ("xg", "chance", "shot")):
            return (f"xG {names[HOME]} {s['xg'][0]:.2f} from {t[HOME]['shots']} shots, "
                    f"{names[AWAY]} {s['xg'][1]:.2f} from {t[AWAY]['shots']} shots. {mom_text}")
        if any(w in q for w in ("momentum", "on top", "dominat", "control")):
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
