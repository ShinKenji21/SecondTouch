# SecondTouch

A second-touch intelligence layer for your live matchday experience.

SecondTouch streams a synthetic football match, computes tactical metrics for every action, flags the moments that matter, and explains *why* they matter in three viewer styles (Tactical Analyst, Casual Fan, Player Cam) and three languages (English, Spanish, Japanese). Impact moments are explained by Azure OpenAI; everything else, and every fallback, comes from a local template engine, and the card always says which.

All match data is generated. No licensed feeds, tracking data or video are used.

## Run it

Requires Python 3.11 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
cd backend
python app.py
```

Open http://127.0.0.1:8000 (not the HTML file directly) and press **START MATCH**. The header badge turns green and shows the event-to-render latency; an event arrives every 1.5 s at 1x.

To use Azure OpenAI, copy `.env.example` to `.env` and fill in the three `AZURE_OPENAI_*` values (see [Azure OpenAI](#azure-openai)). Without them the app runs fully on the local engine and the header shows **AI: local templates**.

Run the tests from the project root with `python -m pytest`.

## What you see

| Area | What it shows |
|---|---|
| **Pitch** | All 22 players, moving every event: teams shift with the ball, defenders press the carrier, attackers hold the offside line, receivers run onto through balls, substitutes run on. Pass lines are coloured by difficulty, dribbles are dotted, shots carry an xG bubble, interceptions and tackles are marked. Click any player to follow them. |
| **Replay bar** | Step back/forward, pause/play, a scrubber with goal and card markers, speed (1x/4x/10x) and a **GO LIVE · +N** button that shows how far behind live you are. Pausing during live play keeps the match running in the background (time-shift). A new match starts 20 s after full-time. Clicking a goal marker replays the three actions before it. Keys: Space, ←, →, L. |
| **Live AI card** | The current moment in the chosen persona and language, with its source (`LOCAL ENGINE` or `AZURE OPENAI`) and an **IMPACT** badge when the moment was flagged. |
| **Live Telemetry** | The metrics of the action on screen: xG, pass difficulty, pressure index and nearest defender, ball speed, forward gain, players bypassed. |
| **Live Event Log** | Every event as it happens; click to jump the pitch to it. "Impact only" filters to flagged moments. |
| **Match Stats** | Team ratings and a head-to-head comparison, then a sortable per-player table: minutes, rating, goals, assists, shots, xG, passes, key passes, dribbles, tackles, interceptions, saves, fouls, cards, touches, sprints. |
| **Tactics** | Per team, measured from the player positions: back-line height, width and length in and out of possession, attack channels, press wins and PPDA, a written tactical read, and an average-positions map. |
| **Key Events** | The match summary: goals, cards, substitutions, big chances, saves, half-time and full-time. Click to replay the build-up. |
| **In-Depth Analysis** | xG race chart, momentum chart, shot map, and every impact moment with its explanation. |
| **Talk to AI** | Questions about the live match. Answered by Azure OpenAI with the full match context, or by the local engine. |

## Architecture

```
backend/generator.py       Stage 1a  Possession-based 11 v 11 simulation; one event per call plus all 22 positions
backend/analytics.py       Stage 1b  xG, pass difficulty, pressure, is_impact_moment, match/player/tactics stats
backend/agent_reasoner.py  Stage 2   Azure OpenAI: three personas as validated JSON for impact moments; Talk to AI
backend/persona_router.py  Stage 3   Template personas in en/es/ja: instant first render and fallback
backend/app.py             Stage 4   FastAPI WebSocket server, one match per connection
backend/models.py                    Pydantic models for viewer settings, model output and events
frontend/                  Stage 5   Canvas pitch, broadcast cards, replay, stats/tactics/analysis tabs
tests/                               pytest suite
```

Each event is sent the moment it is generated, with template commentary for all three personas, so switching persona is instant. If the event is an impact moment and Azure OpenAI is configured, the server asks the model for all three personas in one call (4 s timeout, JSON mode, validated with Pydantic) and pushes an upgrade message about a second later; the card updates and its label changes to `AZURE OPENAI`. A slow or failed model call never delays the stream. At 4x and 10x the model is skipped.

### Data contract

Client to server (send any subset of fields; each change takes effect at once):

```json
{ "type": "config", "mode": "PLAYER_CAM", "team": "Arsenal", "player": "Saka", "speed": 1, "lang": "es" }
{ "type": "ask", "id": 3, "question": "Who is pressing better?" }
```

Server to client:

```jsonc
{ "type": "event", "match_id": 1, "sent_at": 1760000000000,
  "event": {
    "seq": 42, "minute": 31.6, "clock": "31'", "team": "Arsenal", "player": "Saka",
    "event_type": "SHOT", "outcome": "SAVED", "opponent": "Ederson", "receiver": null, "card": null,
    "length_m": 17.4,
    "location": { "start_x": 84.2, "start_y": 41.0, "end_x": 100.0, "end_y": 52.3 },
    "metrics": { "xg": 0.14, "pass_difficulty": null, "pressure": "HIGH", "pressure_index": 72,
                 "nearest_defender_m": 2.6, "sprint_speed_kmh": null, "ball_speed_kmh": 96.2,
                 "forward_gain_m": null, "players_bypassed": null },
    "score": { "home": 1, "away": 0 },
    "is_impact_moment": true, "impact_reasons": ["shot"], "generated_at": 1760000000000 },
  "positions": { "Arsenal": { "Saka": [84.2, 41.0], "...": [0, 0] }, "ManCity": { "...": [0, 0] } },
  "commentary": { "analyst": "...", "casual": "...", "player_cam": "...", "source": "LOCAL ENGINE", "lang": "en" },
  "summary": { "xg": [1.21, 0.64], "shots": [9, 5], "momentum": 38, "possession": [54, 46] },
  "stats": { "teams": {}, "players": {}, "tactics": {} } }

{ "type": "commentary", "match_id": 1, "seq": 42, "commentary": { "...": "..." } }   // AI upgrade or re-render
{ "type": "answer", "id": 3, "text": "...", "source": "AZURE OPENAI" }
```

`event_type` is `PASS`, `DRIBBLE`, `SHOT`, `TACKLE`, `SUBSTITUTION`, `HALF_TIME` or `FULL_TIME`. Outcomes: passes `COMPLETE`/`INTERCEPTED`, dribbles `SUCCESS`, tackles `WON`/`FOUL` (the actor is the tackler, `opponent` the player tackled), shots `GOAL`/`SAVED`/`MISS`/`BLOCKED`. Fields that don't apply are `null`, never a made-up default. Coordinates are percentages of the pitch; Arsenal attack towards x = 100.

## How the metrics work

Distances are converted to metres (105 × 68 m) before any maths.

- **Expected goals (xG)**, shots only: a logistic model of distance *d* (m), the angle *θ* the goal mouth subtends (radians) and the pressure index *p*: `xG = 1 / (1 + e^-(-1.2 - 0.09d + 1.5θ - 0.005p))`. An unpressured penalty-spot shot is about 0.23, a 25 m effort about 0.05. The goal is rolled against the xG.
- **Defensive pressure** is measured from the simulated positions: the distance to the nearest opponent. Index = 100 − 11 × metres (0–100). HIGH ≥ 66, MEDIUM ≥ 33, otherwise LOW.
- **Pass difficulty** (5–99): `5 + 1.2 × length + 0.3 × pressure + 18 × forwardness + 3 × max(0, 5 − receiver space)`, where forwardness is the cosine of the pass direction towards goal (square and backward passes add nothing). Harder passes are more likely to be intercepted.
- **Impact moment**: every shot; a completed line-breaking pass (forward gain ≥ 25 m with difficulty ≥ 70, or 6+ opponents bypassed); a high-pressure turnover (tackle won or pass intercepted under HIGH pressure); any card. About a quarter of events qualify.
- **Momentum** (−100 to +100): a rolling window of the last 12 weighted actions: final-third actions, line breaks, shots (weighted by xG), goals and ball wins in the opponent half.
- **Player rating**: starts at 6.0 and moves with goals, assists, key passes, passing accuracy, dribbles, tackles, interceptions, shots on target, xG, saves, fouls and cards, clamped to 3–10.

A simulated match averages about 170 events, 15 shots, 1.9 goals, 78% pass accuracy and 1.2 yellow cards.

## Azure OpenAI

1. In the Azure portal, create an **Azure OpenAI** resource (or use the one your hackathon provides).
2. Open it in **Azure AI Foundry**, go to **Deployments** and deploy **gpt-4o-mini** (fastest) or **gpt-4o**. Note the deployment name.
3. Back on the resource in the portal, open **Keys and Endpoint** and copy **KEY 1** and the **Endpoint**.
4. Copy `.env.example` to `.env` and fill in `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT_NAME`.
5. Restart `python app.py`. The terminal logs "Azure OpenAI configured" and the header shows **AI: Azure · your-deployment**.

| Variable | Purpose |
|---|---|
| `AZURE_OPENAI_API_KEY` | Enables the AI path; blank means local templates |
| `AZURE_OPENAI_ENDPOINT` | Your resource URL, e.g. `https://my-resource.openai.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Deployment to call; defaults to `gpt-4o-mini` |
| `AZURE_OPENAI_API_VERSION` | Defaults to `2024-10-21` |
| `AZURE_OPENAI_TIMEOUT_S` | Per-call timeout; defaults to 4 |
| `EVENT_INTERVAL_S` | Seconds between events at 1x, 1–2; defaults to 1.5 |

`.env` is git-ignored and must never be committed.

## Performance

Every event carries `generated_at`; the browser records the time to render it and shows the 95th percentile of the last 100 events in the header badge (turning amber above 2 s), and logs it to the console. Template commentary is ready at send time, so this latency does not include the model call; the AI upgrade typically arrives about a second later.

## Known limitations

- The match is random but internally consistent; it is a simulation, not a model of real players. Only notable actions are generated (about 170 per match, not every touch), so totals such as passes are lower than in a real match.
- Teams do not swap ends at half-time.
- When you change language or Player Cam focus, only the latest event is re-rendered; events earlier in the replay keep the text they were created with.
- Talk to AI answers from the local engine are in English only and cover common questions (a player, xG, momentum, pressing/tactics, the score).
- Real club crests and player names are used as labels for a fictional simulation. Confirm the hackathon allows this, or switch `STARTERS`/`BENCH` in `generator.py` and the crest images to generic ones.
