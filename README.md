# SecondTouch

A second-touch intelligence layer for your live matchday experience.

SecondTouch streams a synthetic football match, turns every action into tactical statistics, flags the moments that matter and explains *why* they matter. The same intelligence reaches a data-hungry analyst, a casual fan and a fan following one player, in English, Spanish or Japanese, and every graphic it shows is also emitted as a timed, machine-readable overlay cue. Impact moments, key-event stories and match reports are written by Azure OpenAI; the local template engine renders everything instantly and takes over whenever the model is unavailable, and the screen always says which one wrote the text.

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

## How it meets the brief

| Requirement | Where it is |
|---|---|
| Ingest synthetic events: passes, shots, tackles, possession changes, pressure, metadata | `generator.py` streams passes, dribbles, shots, tackles, fouls, cards, substitutions, half-time and full-time, each with pressure, a `possession_change` flag and all 22 positions; every match carries metadata (competition, venue, referee, weather, lineups, coaches) |
| Interpret into statistics, patterns and context | `analytics.py`: team and player stats, ratings, tactics from positions, momentum, control vs chaos, pressure shifts, tempo |
| Explain why a moment matters | Every impact moment carries a "why it matters" line citing a metric; Azure OpenAI rewrites it with full context |
| Render alongside the match | 2D pitch, broadcast card, badges and toasts, report card, and timed overlay cues for a graphics engine |
| Personalize | Analyst, Casual Fan and Player Cam modes with different panels; favourite club; favourite player; one pinned metric; three languages |
| Player identification with speed and distance thresholds | Name tags on the players involved; ⚡ badge when a player sprints at 32 km/h or more, 🏃 badge at 5 km and 10 km covered |
| Pass quality, ball and shot speed | Pass length, difficulty and accuracy; ball speed on every pass and shot |
| Narratives, milestones, recaps | Story behind every key event, live milestones, half-time and full-time reports |
| Explainability: control vs chaos, pressure changes, rhythm | Game-flow state, pressure-shift alerts and tempo, on the pitch and in the analysis tab |
| Synthetic dataset | `export_dataset.py` writes any number of matches as JSONL/CSV; a 3-match sample is in `data/sample/` |
| Multi-language storytelling | Commentary, alerts, stories and reports in English, Spanish and Japanese |
| Auto-eventing from video | Out of scope: there is no video in a synthetic-only project. The generator already produces the pass and speed metrics automatically; running a vision model over a real feed is future work. |

## What you see

| Area | What it shows |
|---|---|
| **Pitch** | All 22 players moving continuously: teams shift with the ball, defenders press the carrier, attackers hold the offside line, runners sprint onto through balls, substitutes jog on. Teams change ends at half-time. Pass lines are coloured by difficulty, dribbles are dotted, shots carry an xG bubble. Speed and distance badges, milestone toasts and the half-time / full-time report appear over the pitch. Click any player to follow them. |
| **Replay bar** | Step back/forward, pause/play, a scrubber with goal and card markers, speed (1x/4x/10x) and **GO LIVE · +N**. Pausing during live play keeps the match running (time-shift). Clicking a goal marker replays its build-up. Keys: Space, ←, →, L, Esc. |
| **Live AI card** | The current moment in the chosen persona and language, its source (`LOCAL ENGINE` or `AZURE OPENAI`) and an **IMPACT** badge. |
| **Mode panel** | *Analyst*: one telemetry card per team with its last action and running totals. *Casual*: the match at a glance in simple charts, a "who's on top" meter and the goals. *Player Cam*: the followed player's card, stats against the team average, and a heat map. |
| **Header** | Mode, language, favourite club (highlights its moments; Casual commentary cheers for it), pinned metric (xG, possession, shots on target, pass accuracy, pressure, distance or top speed, always visible). Preferences are remembered in this browser. |
| **Live Event Log** | Every event as it happens, with ⇄ for possession changes and ⚡ for impact moments. |
| **Match Stats** | Head-to-head team comparison, then a sortable player table including distance covered and top speed. |
| **Tactics** | Line height, width and length in and out of possession, attack channels, directness, press wins and PPDA, a written read, and average positions. |
| **Key Events & Stories** | Goals, cards, substitutions, big chances, saves and the reports, each with the story behind it: build-up, the moment, and context. "My club only" filter. |
| **In-Depth Analysis** | xG race, momentum, game flow (control/balanced/chaos band with each team's pressure), shot map, impact moments, reports. |
| **Talk to AI** | Questions about the live match, answered by Azure OpenAI with the full match context or by the local engine. |
| **Data & Overlays** | Download the match (events with positions, events CSV, player stats, overlay cues), match metadata, and the live overlay cue feed. |

## Architecture

```
backend/generator.py        Stage 1a  Possession-based 11 v 11 simulation: one event per call plus all 22 positions
backend/analytics.py        Stage 1b  Metrics, impact filter, stats, game flow, milestones, spells, reports
backend/agent_reasoner.py   Stage 2   Azure OpenAI: personas as validated JSON, stories, reports, Talk to AI
backend/persona_router.py   Stage 3   Templates in en/es/ja: personas, alerts, stories, reports
backend/overlays.py                   Timed, machine-readable overlay cues for each event
backend/app.py              Stage 4   FastAPI WebSocket server, one match per connection
backend/models.py                     Pydantic models for viewer settings, model output and events
backend/export_dataset.py             Bulk synthetic dataset export (JSONL/CSV)
frontend/                   Stage 5   Canvas pitch, broadcast cards, mode panels, replay, tabs
tests/                                pytest suite
```

Each event is sent the moment it is generated with template text for every persona, so switching mode is instant. If Azure OpenAI is configured, the server then asks the model, in the background, for all three personas of an impact moment in one call (JSON mode, validated with Pydantic, 4 s timeout), for the story of a key event, and for the half-time and full-time reports; each arrives as an upgrade message and replaces the template text. A slow or failed call never delays the stream. At 4x and 10x only the reports go to the model.

### Data contract

Client to server (send any subset; each change takes effect at once):

```json
{ "type": "config", "mode": "PLAYER_CAM", "team": "Arsenal", "player": "Saka", "speed": 1, "lang": "es", "fav_team": "Arsenal" }
{ "type": "ask", "id": 3, "question": "Who is pressing better?" }
```

Server to client:

```jsonc
{ "type": "match_start", "match_id": 1, "metadata": { "competition": "...", "venue": "...", "referee": "...", "weather": "...",
  "lineups": {}, "bench": {}, "coaches": {}, "formations": {}, "kickoff_utc": "...", "synthetic": true } }

{ "type": "event", "match_id": 1, "sent_at": 1760000000000,
  "event": {
    "seq": 42, "minute": 31.6, "clock": "31'", "team": "Arsenal", "player": "Saka",
    "event_type": "SHOT", "outcome": "SAVED", "opponent": "Ederson", "receiver": null, "card": null,
    "length_m": 17.4,
    "location": { "start_x": 84.2, "start_y": 41.0, "end_x": 100.0, "end_y": 52.3 },
    "metrics": { "xg": 0.14, "pass_difficulty": null, "pressure": "HIGH", "pressure_index": 72,
                 "nearest_defender_m": 2.6, "sprint_speed_kmh": null, "ball_speed_kmh": 96.2,
                 "forward_gain_m": null, "players_bypassed": null },
    "score": { "home": 1, "away": 0 }, "possession_change": true, "right_team": "Arsenal",
    "is_impact_moment": true, "impact_reasons": ["shot"], "generated_at": 1760000000000 },
  "positions": { "Arsenal": { "Saka": [84.2, 41.0] }, "ManCity": {} },
  "commentary": { "analyst": "...", "casual": "...", "player_cam": "...", "source": "LOCAL ENGINE", "lang": "en" },
  "alerts": [ { "kind": "speed", "key": "speed", "team": "Arsenal", "player": "Saka", "value": 33.1, "text": "Saka hits 33.1 km/h!" } ],
  "story": "Build-up: ... Ederson saved Saka's 0.14 xG shot from 17.4m. ...",
  "report": null,
  "overlays": [ { "id": "42-1", "type": "player_tag", "start_ms": 0, "duration_ms": 1500, "at_ms": 1760000000000, "priority": 2 } ],
  "summary": { "xg": [1.21, 0.64], "shots": [9, 5], "on_target": [4, 2], "momentum": 38, "possession": [54, 46],
               "flow": { "state": "CONTROL", "state_team": "Arsenal", "turnover_rate": 12, "press": {}, "tempo": "STEADY" } },
  "stats": { "teams": {}, "players": {}, "tactics": {} } }

{ "type": "commentary", "match_id": 1, "seq": 42, "commentary": {} }       // AI upgrade, or re-render for a new language/focus/club
{ "type": "story", "match_id": 1, "seq": 42, "story": "...", "source": "AZURE OPENAI" }
{ "type": "report", "match_id": 1, "seq": 88, "narrative": "...", "source": "AZURE OPENAI" }
{ "type": "answer", "id": 3, "text": "...", "source": "AZURE OPENAI" }
```

`event_type` is `PASS`, `DRIBBLE`, `SHOT`, `TACKLE`, `SUBSTITUTION`, `HALF_TIME` or `FULL_TIME`. Outcomes: passes `COMPLETE`/`INTERCEPTED`, dribbles `SUCCESS`, tackles `WON`/`FOUL` (the actor is the tackler, `opponent` the player tackled), shots `GOAL`/`SAVED`/`MISS`/`BLOCKED`. Fields that don't apply are `null`, never a made-up default. Coordinates are percentages of the pitch; `right_team` is the team attacking towards x = 100 (Arsenal in the first half, Man City in the second).

### Overlay cues

Every event carries `overlays`: graphics instructions with `start_ms` and `duration_ms` relative to the event, an absolute `at_ms`, a priority, and either a pitch anchor or a screen layout. Types: `player_tag`, `action`, `speed_badge`, `distance_badge`, `lower_third`, `stat_card`, `banner`, `report_card`. The schema is served at `/api/overlay-schema`, the pitch's own badges are drawn from this feed, and the Data & Overlays tab shows it live.

## How the metrics work

Distances are converted to metres (105 × 68 m) before any maths.

- **Expected goals (xG)**, shots only: a logistic model of distance *d* (m), the angle *θ* the goal mouth subtends (radians) and the pressure index *p*: `xG = 1 / (1 + e^-(-1.2 - 0.09d + 1.5θ - 0.005p))`. An unpressured penalty-spot shot is about 0.23, a 25 m effort about 0.05. The goal is rolled against the xG.
- **Defensive pressure** is measured from the simulated positions: the distance to the nearest opponent. Index = 100 − 11 × metres (0–100). HIGH ≥ 66, MEDIUM ≥ 33, otherwise LOW.
- **Pass difficulty** (5–99): `5 + 1.2 × length + 0.3 × pressure + 18 × forwardness + 3 × max(0, 5 − receiver space)`, where forwardness is the cosine of the pass direction towards goal. Harder passes are more likely to be intercepted.
- **Impact moment**: every shot; a completed line-breaking pass (forward gain ≥ 25 m with difficulty ≥ 70, or 6+ opponents bypassed); a high-pressure turnover; any card.
- **Control vs chaos**: over the last 16 actions, a turnover rate of 38% or more is *chaos*; 20% or less with one team holding 60% of the ball is *control* by that team; otherwise *balanced*.
- **Pressure applied**: the average pressure index a team puts on the opponent's player on the ball over their last 12 actions. A rise of 15 points or more triggers a pressure-shift alert.
- **Tempo**: actions per minute over the last 6 minutes against the match average: 1.2× or more is high, 0.8× or less is slow.
- **Momentum** (−100 to +100): a rolling window of weighted final-third actions, line breaks, shots, goals and ball wins.
- **Distance covered**: movement between position snapshots plus running between them (about 92 m per minute outfield, 40 m for goalkeepers); about 10 km per full match. **Top speed**: the fastest dribble or run onto a through ball.
- **Player rating**: starts at 6.0 and moves with goals, assists, key passes, passing, dribbles, tackles, interceptions, shots on target, xG, saves, fouls and cards, clamped to 3–10.
- **Milestones**: first goal, brace, hat-trick, 25/50 touches, 20/40 completed passes, team pass totals, 3/5 tackles won, 3/5 saves, the longest possession spell, the fastest sprint of the match.

A simulated match averages about 170 events, 15 shots, 1.9 goals and 78% pass accuracy.

## Synthetic dataset

```bash
cd backend
python export_dataset.py --matches 50 --seed 1 --out ../data/synthetic
```

Writes `events.jsonl` (with all 22 positions per event), `events.csv`, `players.csv`, `matches.csv` and a field guide. A 3-match sample is in [`data/sample/`](data/sample/). The Data & Overlays tab also downloads the match you are watching.

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

Every event carries `generated_at`; the browser records the time to render it and shows the 95th percentile of the last 100 events in the header badge (amber above 2 s) and logs it to the console. Template text is ready at send time, so this latency does not include the model call; AI upgrades typically arrive about a second later.

## Known limitations

- The match is random but internally consistent; it is a simulation, not a model of real players. Only notable actions are generated (about 170 per match, not every touch), so totals such as passes are lower than in a real match.
- When you change language, Player Cam focus or favourite club, only the latest event is re-rendered; earlier events in the replay keep the text they were created with.
- Talk to AI answers from the local engine are in English only and cover common questions (a player, xG, momentum, game flow, pressing/tactics, reports, the score). Buttons and labels are in English; commentary, alerts, stories and reports are localized.
- Real club crests and player names are used as labels for a fictional simulation. Confirm the hackathon allows this, or switch `STARTERS`/`BENCH` in `generator.py` and the crest images to generic ones.
