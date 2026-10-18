import json
import os

os.environ["AZURE_OPENAI_API_KEY"] = ""  # always test the local engine path
os.environ["EVENT_INTERVAL_S"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import app as server  # noqa: E402


def recv(ws, kind):
    while True:
        msg = json.loads(ws.receive_text())
        if msg["type"] == kind:
            return msg


def test_dashboard_and_assets_are_served():
    client = TestClient(server.app)
    assert "SecondTouch" in client.get("/").text
    for path in ("/static/app.js", "/static/styles.css", "/static/images/arsenal.png", "/static/images/mancity.png"):
        assert client.get(path).status_code == 200, path


def test_stream_settings_and_ask():
    client = TestClient(server.app)
    with client.websocket_connect("/ws/telemetry") as ws:
        hello = recv(ws, "hello")
        assert hello["ai_configured"] is False and "Saka" in hello["squads"]["Arsenal"]
        ws.send_text(json.dumps({"type": "config", "speed": 10}))
        first = recv(ws, "event")
        assert set(first["commentary"]) >= {"analyst", "casual", "player_cam", "source", "lang"}
        assert len(first["positions"]["Arsenal"]) == 11 and "players" in first["stats"]

        # a language change re-renders the latest commentary straight away
        ws.send_text(json.dumps({"type": "config", "lang": "es"}))
        update = recv(ws, "commentary")
        assert update["commentary"]["lang"] == "es"

        ws.send_text(json.dumps({"type": "ask", "id": 1, "question": "How is Haaland playing?"}))
        answer = recv(ws, "answer")
        assert answer["id"] == 1 and "Haaland" in answer["text"] and answer["source"] == "LOCAL ENGINE"

        # bad input is ignored, not fatal
        ws.send_text("not json")
        ws.send_text(json.dumps({"mode": "NOPE"}))
        assert recv(ws, "event")["event"]["seq"] > first["event"]["seq"]
