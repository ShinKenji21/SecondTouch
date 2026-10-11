const ROSTERS = {
    Arsenal: [
        { id: "Saka", name: "Bukayo Saka", pos: "RW", num: 7 },
        { id: "Ødegaard", name: "Martin Ødegaard", pos: "CAM", num: 8 },
        { id: "Rice", name: "Declan Rice", pos: "CDM", num: 41 },
        { id: "Saliba", name: "William Saliba", pos: "CB", num: 2 },
        { id: "Raya", name: "David Raya", pos: "GK", num: 22 }
    ],
    ManCity: [
        { id: "Haaland", name: "Erling Haaland", pos: "ST", num: 9 },
        { id: "De Bruyne", name: "Kevin De Bruyne", pos: "CM", num: 17 },
        { id: "Foden", name: "Phil Foden", pos: "CAM", num: 47 },
        { id: "Rodri", name: "Rodri", pos: "CDM", num: 16 },
        { id: "Ederson", name: "Ederson", pos: "GK", num: 31 }
    ]
};
const TEAM_COLOR = { Arsenal: "#EF4444", ManCity: "#38BDF8" };
const TEAM_INK = { Arsenal: "#FFFFFF", ManCity: "#06222F" };
const MAX_HISTORY = 400;
// 4-3-3 in attack frame (x toward opponent goal, % of pitch). Away team is mirrored.
const FORMATION = [[5,50],[22,85],[22,62],[22,38],[22,15],[45,70],[45,50],[45,30],[70,82],[74,50],[70,18]];

const $ = id => document.getElementById(id);
const canvas = $("pitchCanvas");
const ctx = canvas.getContext("2d");

let currentMode = "PLAYER_CAM";
let selectedTeam = "Arsenal";
let focusPlayer = "Saka";
let speed = 1;

let ws = null, reconnectTimer = null, started = false;
let isPaused = false, isReplayMode = false;
let matchHistory = [], currentIdx = -1, animStart = 0;

const crests = { Arsenal: new Image(), ManCity: new Image() };
crests.Arsenal.src = "/static/arsenal.png";
crests.ManCity.src = "/static/mancity.png";
Object.values(crests).forEach(i => i.onload = buildPitchLayer);

const nameOf = (team, id) => (ROSTERS[team].find(p => p.id === id) || {}).name || id;
const numOf = (team, id) => (ROSTERS[team].find(p => p.id === id) || {}).num || "";

/* ---------- PITCH GEOMETRY (metres, 105 x 68, 4m margin) ---------- */
let W = 0, H = 0, S = 1, OX = 0, OY = 0, dpr = 1;
const pitchLayer = document.createElement("canvas");
const X = m => OX + m * S;
const Y = m => OY + m * S;
const pctPx = (x, y) => [X(x * 1.05), Y(y * 0.68)];

function resize() {
    const r = canvas.parentElement.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    S = W / 113;
    OX = 4 * S;
    OY = (H - 68 * S) / 2;
    buildPitchLayer();
}

function buildPitchLayer() {
    if (!W) return;
    pitchLayer.width = Math.round(W * dpr);
    pitchLayer.height = Math.round(H * dpr);
    const c = pitchLayer.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.fillStyle = "#12331D";
    c.fillRect(0, 0, W, H);
    for (let i = 0; i < 14; i++) {
        c.fillStyle = i % 2 ? "#164227" : "#1B4D2E";
        c.fillRect(X(i * 7.5), Y(0), 7.5 * S, 68 * S);
    }
    ["Arsenal", "ManCity"].forEach((t, i) => {
        const img = crests[t];
        if (!img.complete || !img.naturalWidth) return;
        const sz = 13 * S, cx = X(52.5) + (i ? 1 : -1) * 0 ;
        c.globalAlpha = 0.14;
        if (i === 0) c.drawImage(img, X(52.5) - sz - 2 * S, Y(34) - sz / 2, sz, sz);
        else c.drawImage(img, X(52.5) + 2 * S, Y(34) - sz / 2, sz, sz);
        c.globalAlpha = 1;
    });
    c.strokeStyle = "rgba(255,255,255,0.9)";
    c.fillStyle = "rgba(255,255,255,0.95)";
    c.lineWidth = Math.max(1.5, S * 0.18);
    c.strokeRect(X(0), Y(0), 105 * S, 68 * S);
    c.beginPath(); c.moveTo(X(52.5), Y(0)); c.lineTo(X(52.5), Y(68)); c.stroke();
    c.beginPath(); c.arc(X(52.5), Y(34), 9.15 * S, 0, Math.PI * 2); c.stroke();
    c.beginPath(); c.arc(X(52.5), Y(34), 0.35 * S, 0, Math.PI * 2); c.fill();
    const arc = Math.acos(5.5 / 9.15);
    [[0, 1], [105, -1]].forEach(([gx, dir]) => {
        c.strokeRect(dir > 0 ? X(0) : X(105 - 16.5), Y(34 - 20.16), 16.5 * S, 40.32 * S);
        c.strokeRect(dir > 0 ? X(0) : X(105 - 5.5), Y(34 - 9.16), 5.5 * S, 18.32 * S);
        const sx = gx + dir * 11;
        c.beginPath(); c.arc(X(sx), Y(34), 0.35 * S, 0, Math.PI * 2); c.fill();
        c.beginPath();
        if (dir > 0) c.arc(X(sx), Y(34), 9.15 * S, -arc, arc);
        else c.arc(X(sx), Y(34), 9.15 * S, Math.PI - arc, Math.PI + arc);
        c.stroke();
        c.strokeRect(dir > 0 ? X(-2) : X(105), Y(34 - 3.66), 2 * S, 7.32 * S);
    });
}

/* ---------- DRAWING ---------- */
function lerpColor(a, b, t) {
    const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const [r1, g1, b1] = p(a), [r2, g2, b2] = p(b);
    return `rgb(${Math.round(r1 + (r2 - r1) * t)},${Math.round(g1 + (g2 - g1) * t)},${Math.round(b1 + (b2 - b1) * t)})`;
}
const ease = t => 1 - Math.pow(1 - t, 3);

function drawPlayers(now) {
    ["Arsenal", "ManCity"].forEach(team => {
        FORMATION.forEach(([fx, fy], i) => {
            const mirror = team === "ManCity";
            const x = (mirror ? 100 - fx : fx) + Math.sin(now / 1400 + i * 1.7) * 0.5;
            const y = (mirror ? 100 - fy : fy) + Math.cos(now / 1700 + i * 2.3) * 0.8;
            const [px, py] = pctPx(x, y);
            ctx.beginPath();
            ctx.arc(px, py, Math.max(5, S * 0.75), 0, Math.PI * 2);
            ctx.fillStyle = TEAM_COLOR[team];
            ctx.globalAlpha = 0.55;
            ctx.fill();
            ctx.globalAlpha = 1;
        });
    });
}

function drawEvent(ev, progress, alpha, isCurrent) {
    const l = ev.location, m = ev.metrics;
    const [x0, y0] = pctPx(l.start_x, l.start_y);
    const [x1, y1] = pctPx(l.end_x, l.end_y);
    const t = ease(progress);
    const cx = x0 + (x1 - x0) * t, cy = y0 + (y1 - y0) * t;
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.lineCap = "round";
    ctx.shadowColor = "rgba(0,0,0,0.5)";
    ctx.shadowBlur = 4;
    if (ev.event_type === "SHOT") {
        ctx.strokeStyle = "#EAB308"; ctx.lineWidth = 4;
        ctx.fillStyle = "rgba(234,179,8,0.25)";
        ctx.beginPath(); ctx.arc(x0, y0, S * (0.8 + (m.xg || 0) * 5), 0, Math.PI * 2); ctx.fill();
    } else if (ev.event_type === "DRIBBLE") {
        ctx.strokeStyle = TEAM_COLOR[ev.team]; ctx.lineWidth = 3; ctx.setLineDash([2, 6]);
    } else {
        ctx.strokeStyle = lerpColor("#22C55E", "#EF4444", (m.pass_difficulty || 0) / 100);
        ctx.lineWidth = 3; ctx.setLineDash([9, 5]);
    }
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(cx, cy); ctx.stroke();
    ctx.setLineDash([]);
    if (progress >= 1) {
        const a = Math.atan2(y1 - y0, x1 - x0), s = Math.max(6, S * 0.9);
        ctx.fillStyle = ctx.strokeStyle;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x1 - s * Math.cos(a - 0.45), y1 - s * Math.sin(a - 0.45));
        ctx.lineTo(x1 - s * Math.cos(a + 0.45), y1 - s * Math.sin(a + 0.45));
        ctx.fill();
    }
    ctx.restore();
    if (!isCurrent) return;

    // actor marker + label
    const focus = currentMode === "PLAYER_CAM" && ev.player === focusPlayer;
    ctx.beginPath(); ctx.arc(x0, y0, Math.max(10, S * 1.3), 0, Math.PI * 2);
    ctx.fillStyle = TEAM_COLOR[ev.team]; ctx.fill();
    ctx.lineWidth = focus ? 3 : 1.5; ctx.strokeStyle = focus ? "#EAB308" : "#fff"; ctx.stroke();
    ctx.fillStyle = TEAM_INK[ev.team];
    ctx.font = "800 11px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(numOf(ev.team, ev.player), x0, y0 + 0.5);
    ctx.fillStyle = focus ? "#EAB308" : "#fff";
    ctx.font = "800 11px system-ui, sans-serif";
    ctx.shadowColor = "rgba(0,0,0,0.8)"; ctx.shadowBlur = 4;
    ctx.fillText(nameOf(ev.team, ev.player).toUpperCase(), x0, y0 - Math.max(18, S * 2));
    ctx.shadowBlur = 0;
    // ball
    ctx.font = "15px sans-serif";
    ctx.fillText("⚽", cx, cy);
    if (ev.outcome === "GOAL" && progress >= 1) {
        const k = Math.min(1, (performance.now() - animStart - 900 / speed) / 700);
        if (k > 0) {
            ctx.strokeStyle = `rgba(234,179,8,${1 - k})`; ctx.lineWidth = 4;
            ctx.beginPath(); ctx.arc(x1, y1, 10 + k * 50, 0, Math.PI * 2); ctx.stroke();
        }
        ctx.fillStyle = "#EAB308"; ctx.font = "900 20px system-ui, sans-serif";
        ctx.fillText("GOAL", X(52.5), Y(8));
    }
}

function frame(now) {
    if (W) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.drawImage(pitchLayer, 0, 0, W, H);
        drawPlayers(now);
        if (currentIdx >= 0) {
            for (let k = 5; k >= 1; k--) {
                const ev = matchHistory[currentIdx - k];
                if (ev) drawEvent(ev, 1, 0.5 - k * 0.08, false);
            }
            const dur = 900 / speed;
            drawEvent(matchHistory[currentIdx], Math.min(1, (performance.now() - animStart) / dur), 1, true);
        }
    }
    requestAnimationFrame(frame);
}

/* ---------- UI UPDATES ---------- */
function setMetric(valId, barId, value, pct, suffix = "") {
    $(valId).innerText = value == null ? "—" : value + suffix;
    $(barId).style.width = `${value == null ? 0 : pct}%`;
}

function updateUI(data) {
    if (!data) return;
    const ev = data.event;
    $("ai-commentary").innerText = `"${data.ai_commentary}"`;
    $("ai-source").innerText = data.source;
    $("match-clock").innerText = ev.clock;
    $("score-home").innerText = ev.score.home;
    $("score-away").innerText = ev.score.away;
    const mmss = min => `${Math.floor(min)}:${String(Math.floor((min % 1) * 60)).padStart(2, "0")}`;
    $("replay-time").innerText = mmss(ev.minute);
    $("replay-duration").innerText = mmss(matchHistory[matchHistory.length - 1].event.minute);
    const m = ev.metrics;
    setMetric("val-xg", "bar-xg", m.xg, (m.xg || 0) * 100);
    setMetric("val-pass-diff", "bar-pass-diff", m.pass_difficulty, m.pass_difficulty, "/100");
    $("val-pressure").innerText = m.pressure;
    $("bar-pressure").style.width = `${m.pressure_index}%`;
}

function goTo(i) {
    if (!matchHistory[i]) return;
    currentIdx = i;
    animStart = performance.now();
    $("timeline-slider").value = i;
    updateUI(matchHistory[i]);
    document.querySelectorAll(".event-item").forEach(el =>
        el.classList.toggle("active-replay", isReplayMode && +el.dataset.seq === matchHistory[i].event.seq));
}

const ICON = { GOAL: "⚽", SAVED: "🧤", MISS: "🎯", BLOCKED: "🧱", PASS: "➡️", DRIBBLE: "💨" };
function addLogItem(data) {
    const ev = data.event;
    const label = ev.outcome || ev.event_type;
    const item = document.createElement("div");
    item.className = "event-item clickable new";
    item.dataset.seq = ev.seq;
    item.setAttribute("role", "button");
    item.tabIndex = 0;
    item.innerHTML = `<span class="event-time">${ev.clock}</span><span>${ICON[label] || "•"} <strong>${label}</strong> · ${ev.player}</span>`;
    const list = $("event-log-container");
    list.prepend(item);
    while (list.children.length > 40) list.lastChild.remove();
    $("event-count").innerText = `${ev.seq} events`;
}

function onSocketMessage(event) {
    const data = JSON.parse(event.data);
    matchHistory.push(data);
    if (matchHistory.length > MAX_HISTORY) {
        matchHistory.shift();
        if (currentIdx > 0) currentIdx--;
    }
    $("timeline-slider").max = matchHistory.length - 1;
    addLogItem(data);
    if (!isReplayMode && !isPaused) goTo(matchHistory.length - 1);
}

/* ---------- CONNECTION ---------- */
function setConnected(on) {
    $("connection-badge").classList.toggle("connected", on);
    $("connection-text").innerText = on ? "WS CONNECTED" : "RECONNECTING…";
    const pill = $("live-indicator");
    if (!isReplayMode) {
        pill.innerText = on ? "LIVE" : "OFFLINE";
        pill.classList.toggle("active-live", on);
    }
}

function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/telemetry`);
    ws.onopen = () => { setConnected(true); sendConfig(); };
    ws.onmessage = onSocketMessage;
    ws.onclose = () => {
        setConnected(false);
        if (started) reconnectTimer = setTimeout(connect, 2000);
    };
}

function sendConfig() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ mode: currentMode, team: selectedTeam, player: focusPlayer, speed }));
    }
}

/* ---------- CONTROLS ---------- */
$("kickoff-btn").addEventListener("click", () => {
    if (started) return;
    started = true;
    $("kickoff-btn").style.display = "none";
    connect();
});

function enterReplayMode() {
    isReplayMode = true;
    const pill = $("live-indicator");
    pill.innerText = "REPLAY";
    pill.classList.remove("active-live");
    pill.classList.add("replay-mode");
    $("return-live-btn").style.display = "flex";
}

$("timeline-slider").addEventListener("input", e => { enterReplayMode(); goTo(parseInt(e.target.value, 10)); });

const playPauseBtn = $("play-pause-btn");
playPauseBtn.addEventListener("click", () => {
    isPaused = !isPaused;
    playPauseBtn.innerHTML = `<i class="fa-solid fa-${isPaused ? "play" : "pause"}"></i>`;
    if (!isPaused && !isReplayMode) goTo(matchHistory.length - 1);
});

function replayFromLog(e) {
    const item = e.target.closest(".event-item");
    if (!item || (e.type === "keydown" && e.key !== "Enter" && e.key !== " ")) return;
    const idx = matchHistory.findIndex(d => d.event.seq === +item.dataset.seq);
    if (idx < 0) return;
    enterReplayMode();
    goTo(idx);
}
$("event-log-container").addEventListener("click", replayFromLog);
$("event-log-container").addEventListener("keydown", replayFromLog);

$("return-live-btn").addEventListener("click", () => {
    isReplayMode = false; isPaused = false;
    playPauseBtn.innerHTML = `<i class="fa-solid fa-pause"></i>`;
    const pill = $("live-indicator");
    pill.innerText = "LIVE";
    pill.classList.remove("replay-mode");
    pill.classList.add("active-live");
    $("return-live-btn").style.display = "none";
    goTo(matchHistory.length - 1);
});

$("speed-select").addEventListener("change", e => { speed = parseInt(e.target.value, 10); sendConfig(); });

function updatePlayerDropdown(teamKey) {
    const sel = $("player-select");
    sel.innerHTML = "";
    ROSTERS[teamKey].forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.id;
        opt.innerText = `${p.name} (${p.pos})`;
        sel.appendChild(opt);
    });
    focusPlayer = ROSTERS[teamKey][0].id;
    sendConfig();
}

$("team-select").addEventListener("change", e => { selectedTeam = e.target.value; updatePlayerDropdown(selectedTeam); });
$("player-select").addEventListener("change", e => { focusPlayer = e.target.value; sendConfig(); });

document.querySelectorAll(".mode-btn").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
    $("player-focus-container").style.display = currentMode === "PLAYER_CAM" ? "flex" : "none";
    sendConfig();
}));

document.querySelectorAll(".drawer-tab-btn").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll(".drawer-tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    $(`panel-${btn.dataset.tab}`).classList.add("active");
}));

// Talk to AI: answers from the latest telemetry event (local, no model call).
$("ai-query-send-btn").addEventListener("click", () => {
    const input = $("ai-query-input"), box = $("ai-query-response");
    if (!input.value.trim()) return;
    const last = matchHistory[matchHistory.length - 1];
    if (!last) { box.innerHTML = "<p>Start the match first so there is telemetry to analyse.</p>"; return; }
    const e = last.event, m = e.metrics;
    const bits = [`${e.clock}: ${nameOf(e.team, e.player)} (${e.event_type.toLowerCase()}) with ${m.pressure.toLowerCase()} pressure, nearest defender ${m.nearest_defender_m}m away.`];
    if (m.xg != null) bits.push(`Shot quality ${m.xg} xG.`);
    if (m.pass_difficulty != null) bits.push(`Pass difficulty ${m.pass_difficulty}/100.`);
    box.innerHTML = `<p><strong>Tactical Assistant:</strong> ${bits.join(" ")}</p>`;
    input.value = "";
});

window.addEventListener("resize", resize);
resize();
updatePlayerDropdown("Arsenal");
requestAnimationFrame(frame);
