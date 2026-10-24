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
    return with_agent_messages(ws.sent)


def _pipeline(status):
    steps = [{"agent": "Analyst", "ms": 2100, "status": "ok", "detail": "1 tool call: get_team_comparison"},
             {"agent": "Commentator", "ms": 1500, "status": "ok", "detail": ""}]
    if status == "revised":
        steps += [{"agent": "Fact-checker", "ms": 1, "status": "revise", "detail": "'987' does not match any number in the data"},
                  {"agent": "Commentator", "ms": 1300, "status": "revised", "detail": ""}]
    if status == "error":
        steps = [{"agent": "Orchestrator", "ms": 14000, "status": "timeout", "detail": "took too long: templates kept"}]
    else:
        steps.append({"agent": "Fact-checker", "ms": 1, "status": "rejected" if status == "rejected" else "passed",
                      "detail": "every number matches the data"})
    return {"steps": steps, "status": status, "ms": 3700, "tools": ["get_team_comparison"]}


def with_agent_messages(msgs):
    """What the agent desk sends when Foundry keys are set, after a few events of the recorded match:
    AI commentary and stories with their traces, and agent runs of every outcome."""
    out = []
    for m in msgs:
        out.append(m)
        if m["type"] != "event" or not m["event"]["is_impact_moment"]:
            continue
        ev, n = m["event"], sum(1 for x in out if x["type"] == "agent_run")
        status = ("passed", "revised", "rejected", "error")[n % 4]
        out.append({"type": "agent_run", "match_id": m["match_id"], "seq": ev["seq"], "clock": ev["clock"],
                    "kind": ("commentary", "story", "report", "answer")[n % 4], "pipeline": _pipeline(status)})
        if status in ("passed", "revised"):
            out.append({"type": "commentary", "match_id": m["match_id"], "seq": ev["seq"], "pipeline": _pipeline(status),
                        "commentary": {"analyst": "AI analyst line.", "casual": "AI casual line!", "player_cam": "AI cam line.",
                                       "source": "AZURE OPENAI", "lang": "en"}})
            out.append({"type": "story", "match_id": m["match_id"], "seq": ev["seq"], "story": "An AI story.",
                        "source": "AZURE OPENAI", "pipeline": _pipeline(status)})
    out.insert(1, {"type": "answer", "id": 1, "text": "An AI answer.", "source": "AZURE OPENAI", "pipeline": _pipeline("passed")})
    last = max(i for i, m in enumerate(out) if m["type"] == "event" and m["event"]["minute"] < 70)
    out.insert(last + 1, {"type": "catchup", "id": 0, "match_id": out[last]["match_id"], "start": "40'", "end": "69'",
                          "text": "While you were away...", "source": "AZURE OPENAI", "pipeline": _pipeline("passed")})
    for m in out:
        if m["type"] == "hello":
            m.update(ai_configured=True, deployment="gpt-4.1-mini")
    return out


def test_recorded_match_has_every_message_type():
    msgs = record_match()
    types = {m["type"] for m in msgs}
    assert {"hello", "match_start", "event"} <= types
    assert msgs[-1]["event"]["event_type"] == "FULL_TIME"
    assert all("fitness" in m and "stance" in m for m in msgs if m["type"] == "event")
    recaps = [m["clock"] for m in msgs if m["type"] == "recap"]
    assert len(recaps) == 4 and [int(c.split("'")[0].split("+")[0]) // 15 for c in recaps] == [1, 2, 4, 5]
    runs = [m["pipeline"]["status"] for m in msgs if m["type"] == "agent_run"]
    assert {"passed", "revised", "rejected", "error"} <= set(runs)


@pytest.mark.skipif(not NODE, reason="Node.js is not installed")
def test_frontend_renders_a_whole_match_without_errors(tmp_path):
    path = tmp_path / "messages.json"
    path.write_text(json.dumps(record_match()), encoding="utf-8")
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
    out = subprocess.run([NODE, str(ROOT / "tests" / "frontend_smoke.js"), str(ROOT / "frontend" / "app.js"), str(path)],
                         capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
