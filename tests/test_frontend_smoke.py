"""Plays a full match through the real server session (without waiting between events), then
replays every message through frontend/app.js with tests/frontend_smoke.js. Needs Node.js;
skipped when it is not installed (set NODE to a node executable to use a specific one)."""
import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import app as appmod

ROOT = Path(__file__).resolve().parent.parent
NODE = os.getenv("NODE") or shutil.which("node")


class _Done(Exception):
    pass


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        msg = json.loads(text)
        self.sent.append(msg)
        if msg["type"] == "event" and msg["event"]["event_type"] == "FULL_TIME":
            raise _Done


def record_match():
    ws = FakeSocket()
    session = appmod.Session(ws)

    async def no_wait(seconds):
        return None

    session.sleep = no_wait
    session.cfg["mode"] = "ANALYST"
    try:
        asyncio.run(session.run())
    except _Done:
        pass
    return ws.sent


def test_recorded_match_has_every_message_type():
    msgs = record_match()
    types = {m["type"] for m in msgs}
    assert {"hello", "match_start", "event"} <= types
    assert msgs[-1]["event"]["event_type"] == "FULL_TIME"
    assert all("fitness" in m and "stance" in m for m in msgs if m["type"] == "event")


@pytest.mark.skipif(not NODE, reason="Node.js is not installed")
def test_frontend_renders_a_whole_match_without_errors(tmp_path):
    path = tmp_path / "messages.json"
    path.write_text(json.dumps(record_match()), encoding="utf-8")
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
    out = subprocess.run([NODE, str(ROOT / "tests" / "frontend_smoke.js"), str(ROOT / "frontend" / "app.js"), str(path)],
                         capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
