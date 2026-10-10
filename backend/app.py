import asyncio
import json
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from generator import generate_match_event
from agent_reasoner import generate_ai_commentary

app = FastAPI(title="SecondTouch")

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
async def get_dashboard():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    current_mode = "PLAYER_CAM"
    focus_player = "Saka"

    try:
        while True:
            # Receive active mode configuration from frontend
            try:
                data_str = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                config = json.loads(data_str)
                current_mode = config.get("mode", current_mode)
                focus_player = config.get("player", focus_player)
            except asyncio.TimeoutError:
                pass

            event = generate_match_event()
            commentary = generate_ai_commentary(event, mode=current_mode, focus_player=focus_player)

            payload = {
                "event": event,
                "mode": current_mode,
                "focus_player": focus_player,
                "ai_commentary": commentary,
                "source": f"AZURE OPENAI · LIVE {current_mode} ANALYSIS"
            }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2.5)

    except WebSocketDisconnect:
        pass

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)