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
    for path in ("/static/app.js", "/static/styles.css", "/static/images/brackenford.svg", "/static/images/kestermouth.svg"):
        assert client.get(path).status_code == 200, path


def test_stream_settings_and_ask():
    client = TestClient(server.app)
    with client.websocket_connect("/ws/telemetry") as ws:
        hello = recv(ws, "hello")
        assert hello["ai_configured"] is False and "Thornquist" in hello["squads"]["Brackenford"]
        ws.send_text(json.dumps({"type": "config", "speed": 10}))
        first = recv(ws, "event")
        assert set(first["commentary"]) >= {"analyst", "casual", "player_cam", "source", "lang"}
        assert len(first["positions"]["Brackenford"]) == 11 and "players" in first["stats"]
        # every language comes along, so switching rewrites the match so far, not only what follows
        assert set(first["i18n"]) == {"en", "es", "ja"}
        assert first["i18n"]["en"]["commentary"] == first["commentary"]
        assert first["i18n"]["es"]["commentary"]["casual"] != first["i18n"]["en"]["commentary"]["casual"]

        # a language change re-renders the latest commentary straight away
        ws.send_text(json.dumps({"type": "config", "lang": "es"}))
        update = recv(ws, "commentary")
        assert update["commentary"]["lang"] == "es"

        ws.send_text(json.dumps({"type": "ask", "id": 1, "question": "How is Strachley playing?"}))
        answer = recv(ws, "answer")
        assert answer["id"] == 1 and "Strachley" in answer["text"] and answer["source"] == "LOCAL ENGINE"
        # the suggested questions all get a real answer, not the fallback
        for i, q in enumerate(("Who is the best player so far?", "What has happened so far?",
                               "Who is creating the better chances?"), start=2):
            ws.send_text(json.dumps({"type": "ask", "id": i, "question": q}))
            reply = recv(ws, "answer")
            assert reply["id"] == i and "Local engine" not in reply["text"], (q, reply["text"])

        # a viewer back after missing part of the match gets a catch-up
        for _ in range(6):
            recv(ws, "event")
        ws.send_text(json.dumps({"type": "catchup", "id": 7, "since_seq": first["event"]["seq"]}))
        catch = recv(ws, "catchup")
        assert catch["id"] == 7 and catch["source"] == "LOCAL ENGINE" and catch["text"].startswith("Mientras no estabas")

        # bad input is ignored, not fatal
        ws.send_text("not json")
        ws.send_text(json.dumps({"mode": "NOPE"}))
        assert recv(ws, "event")["event"]["seq"] > first["event"]["seq"]
