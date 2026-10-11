import asyncio
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:  # optional: load AZURE_OPENAI_* from .env
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from agent_reasoner import generate_ai_commentary
from generator import MatchSim

HERE = Path(__file__).resolve().parent
FRONTEND_DIR = next(
    (d for d in (HERE.parent / "frontend", HERE / "frontend", HERE) if (d / "index.html").exists()),
    HERE.parent / "frontend",
)

app = FastAPI(title="SecondTouch")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def get_dashboard():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.websocket("/ws/telemetry")
async def telemetry(ws: WebSocket):
    await ws.accept()
    cfg = {"mode": "PLAYER_CAM", "team": "Arsenal", "player": "Saka", "speed": 1}
    sim = MatchSim()

    async def receiver():
        # Runs alongside the sender, so config messages are never dropped.
        while True:
            try:
                msg = json.loads(await ws.receive_text())
            except ValueError:
                continue
            if isinstance(msg, dict):
                for k in cfg:
                    if k in msg:
                        cfg[k] = msg[k]

    recv_task = asyncio.create_task(receiver())
    try:
        while not recv_task.done():
            if sim.finished:
                sim = MatchSim()
            speed = cfg["speed"] if cfg["speed"] in (1, 4, 10) else 1
            focus_on = cfg["mode"] == "PLAYER_CAM"
            event = sim.next_event(cfg["team"], cfg["player"], 0.5 if focus_on else 0.0)
            text, source = await asyncio.to_thread(
                generate_ai_commentary, event, cfg["mode"], cfg["player"], speed == 1
            )
            await ws.send_text(json.dumps({
                "event": event, "mode": cfg["mode"], "focus_player": cfg["player"],
                "ai_commentary": text, "source": source,
            }, ensure_ascii=False))
            await asyncio.sleep(2.5 / speed)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        recv_task.cancel()


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
