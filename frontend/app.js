const ROSTERS = {
    Arsenal: [
        { name: "Bukayo Saka", pos: "RW" },
        { name: "Martin Ødegaard", pos: "CAM" },
        { name: "Declan Rice", pos: "CDM" },
        { name: "William Saliba", pos: "CB" },
        { name: "David Raya", pos: "GK" }
    ],
    ManCity: [
        { name: "Erling Haaland", pos: "ST" },
        { name: "Kevin De Bruyne", pos: "CM" },
        { name: "Phil Foden", pos: "CAM" },
        { name: "Rodri", pos: "CDM" },
        { name: "Ederson", pos: "GK" }
    ]
};

let currentMode = "PLAYER_CAM";
let selectedTeam = "Arsenal";
let focusPlayer = "Bukayo Saka";

// REPLAY & PLAYBACK STATE
let ws = null;
let isPaused = false;
let isReplayMode = false;
let matchHistory = [];
let currentPlaybackIndex = -1;

const canvas = document.getElementById("pitchCanvas");
const ctx = canvas.getContext("2d");

// HIGH-DPI ACCURATE GEOMETRY PITCH RENDERER
function drawPitch() {
    const container = canvas.parentElement;
    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);

    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    ctx.scale(dpr, dpr);

    const w = rect.width;
    const h = rect.height;

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";

    // 1. REALISTIC GRASS STRIPES
    const stripeCount = 12;
    const stripeWidth = w / stripeCount;
    for (let i = 0; i < stripeCount; i++) {
        ctx.fillStyle = (i % 2 === 0) ? "#1B4D2E" : "#164227";
        ctx.fillRect(i * stripeWidth, 0, stripeWidth, h);
    }

    // 2. CRISP WHITE PITCH MARKINGS
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 2.5;

    const m = 30;
    const pitchW = w - m * 2;
    const pitchH = h - m * 2;

    ctx.strokeRect(m, m, pitchW, pitchH);

    ctx.beginPath();
    ctx.moveTo(w / 2, m);
    ctx.lineTo(w / 2, h - m);
    ctx.stroke();

    const centerRadius = pitchH * 0.18;
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, centerRadius, 0, Math.PI * 2);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(w / 2, h / 2, 3, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
    ctx.fill();

    const boxH = pitchH * 0.54;
    const boxW = pitchW * 0.16;
    const boxY = (h - boxH) / 2;

    const leftBoxRightX = m + boxW;
    const rightBoxLeftX = w - m - boxW;

    ctx.strokeRect(m, boxY, boxW, boxH);
    ctx.strokeRect(rightBoxLeftX, boxY, boxW, boxH);

    const smallBoxH = pitchH * 0.26;
    const smallBoxW = pitchW * 0.055;
    const smallBoxY = (h - smallBoxH) / 2;

    ctx.strokeRect(m, smallBoxY, smallBoxW, smallBoxH);
    ctx.strokeRect(w - m - smallBoxW, smallBoxY, smallBoxW, smallBoxH);

    const spotDist = pitchW * 0.11;
    const leftSpotX = m + spotDist;
    const rightSpotX = w - m - spotDist;

    ctx.beginPath();
    ctx.arc(leftSpotX, h / 2, 2.5, 0, Math.PI * 2);
    ctx.arc(rightSpotX, h / 2, 2.5, 0, Math.PI * 2);
    ctx.fill();

    const arcRadius = centerRadius;
    const dx = leftBoxRightX - leftSpotX;
    if (arcRadius > dx) {
        const arcAngle = Math.acos(dx / arcRadius);

        ctx.beginPath();
        ctx.arc(leftSpotX, h / 2, arcRadius, -arcAngle, arcAngle);
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(rightSpotX, h / 2, arcRadius, Math.PI - arcAngle, Math.PI + arcAngle);
        ctx.stroke();
    }

    drawGoalNets(ctx, m, h, pitchH);
    renderPlayers(w, h, m, pitchW, pitchH);
}

function drawGoalNets(ctx, m, h, pitchH) {
    const goalH = pitchH * 0.22;
    const goalY = (h - goalH) / 2;
    const depth = 16;
    const renderW = canvas.width / (window.devicePixelRatio || 1);

    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 3;

    ctx.strokeRect(m - depth, goalY, depth, goalH);
    ctx.strokeRect(renderW - m, goalY, depth, goalH);

    ctx.lineWidth = 0.8;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
    for (let y = goalY; y <= goalY + goalH; y += 5) {
        ctx.beginPath();
        ctx.moveTo(m - depth, y);
        ctx.lineTo(m, y);
        ctx.moveTo(renderW - m, y);
        ctx.lineTo(renderW - m + depth, y);
        ctx.stroke();
    }
}

function renderPlayers(w, h, m, pitchW, pitchH) {
    const arsenalPlayers = [
        { id: "GK", x: 0.05, y: 0.50 },
        { id: "X",  x: 0.18, y: 0.50 },
        { id: "P",  x: 0.26, y: 0.78 },
        { id: "M",  x: 0.26, y: 0.22 },
        { id: "K",  x: 0.38, y: 0.68 },
        { id: "R",  x: 0.40, y: 0.48 },
        { id: "Ø",  x: 0.32, y: 0.34 },
        { id: "S",  x: 0.78, y: 0.22, focus: true, hasBall: true }
    ];

    const cityPlayers = [
        { id: "GK", x: 0.95, y: 0.50 },
        { id: "Y",  x: 0.45, y: 0.82 },
        { id: "W",  x: 0.54, y: 0.58 },
        { id: "T",  x: 0.70, y: 0.32 },
        { id: "V",  x: 0.84, y: 0.42 },
        { id: "U",  x: 0.84, y: 0.78 }
    ];

    // WHITE DASHED PASSING VECTOR
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(m + pitchW * 0.40, m + pitchH * 0.48);
    ctx.lineTo(m + pitchW * 0.32, m + pitchH * 0.34);
    ctx.lineTo(m + pitchW * 0.78, m + pitchH * 0.22);
    
    ctx.strokeStyle = "#FFFFFF";
    ctx.lineWidth = 3;
    ctx.setLineDash([8, 5]);
    ctx.shadowColor = "rgba(0, 0, 0, 0.5)";
    ctx.shadowBlur = 4;
    ctx.stroke();
    ctx.restore();

    // ARSENAL PLAYERS
    arsenalPlayers.forEach(p => {
        const px = m + pitchW * p.x;
        const py = m + pitchH * p.y;

        if (p.focus && currentMode === "PLAYER_CAM") {
            ctx.beginPath();
            ctx.arc(px, py, 22, 0, Math.PI * 2);
            ctx.fillStyle = "rgba(234, 179, 8, 0.25)";
            ctx.fill();
            ctx.strokeStyle = "#EAB308";
            ctx.lineWidth = 2.5;
            ctx.stroke();

            ctx.fillStyle = "#EAB308";
            ctx.font = "900 11px system-ui, sans-serif";
            ctx.textAlign = "center";
            ctx.fillText("BUKAYO SAKA · 7", px, py - 28);
        }

        ctx.save();
        ctx.shadowColor = "rgba(0, 0, 0, 0.4)";
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.arc(px, py, 12, 0, Math.PI * 2);
        ctx.fillStyle = "#EF4444";
        ctx.fill();
        ctx.restore();

        ctx.fillStyle = "#FFFFFF";
        ctx.font = "900 10px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(p.id, px, py);

        if (p.hasBall) {
            ctx.font = "15px sans-serif";
            ctx.textAlign = "center";
            ctx.textBaseline = "middle";
            ctx.fillText("⚽", px + 15, py - 12);
        }
    });

    // MAN CITY PLAYERS
    cityPlayers.forEach(p => {
        const px = m + pitchW * p.x;
        const py = m + pitchH * p.y;

        ctx.save();
        ctx.shadowColor = "rgba(0, 0, 0, 0.4)";
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.arc(px, py, 12, 0, Math.PI * 2);
        ctx.fillStyle = "#38BDF8";
        ctx.fill();
        ctx.restore();

        ctx.fillStyle = "#000000";
        ctx.font = "900 10px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(p.id, px, py);
    });
}

function updatePlayerDropdown(teamKey) {
    const playerSelect = document.getElementById("player-select");
    playerSelect.innerHTML = "";

    ROSTERS[teamKey].forEach(p => {
        const opt = document.createElement("option");
        opt.value = p.name;
        opt.innerText = `${p.name} (${p.pos})`;
        playerSelect.appendChild(opt);
    });

    focusPlayer = ROSTERS[teamKey][0].name;
    sendConfig();
}

window.addEventListener("resize", drawPitch);
document.addEventListener("DOMContentLoaded", drawPitch);

// MANUAL KICK OFF BUTTON CONTROLLER
document.getElementById("kickoff-btn").addEventListener("click", () => {
    if (ws) return;

    document.getElementById("kickoff-btn").style.display = "none";
    
    const livePill = document.getElementById("live-indicator");
    livePill.innerText = "LIVE";
    livePill.classList.add("active-live");

    const connBadge = document.getElementById("connection-badge");
    connBadge.classList.add("connected");
    document.getElementById("connection-text").innerText = "WS CONNECTED";

    // ESTABLISH WEBSOCKET STREAM ON CLICK
    ws = new WebSocket(`ws://${window.location.host}/ws/telemetry`);

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        matchHistory.push(data);

        const slider = document.getElementById("timeline-slider");
        slider.max = matchHistory.length - 1;

        if (!isReplayMode && !isPaused) {
            currentPlaybackIndex = matchHistory.length - 1;
            slider.value = currentPlaybackIndex;
            updateUIWithEvent(data);
        }
    };
});

function updateUIWithEvent(data) {
    if (!data) return;
    
    document.getElementById("ai-commentary").innerText = `"${data.ai_commentary}"`;
    document.getElementById("ai-source").innerText = data.source;

    if (data.event) {
        if (data.event.timestamp) {
            document.getElementById("replay-time").innerText = data.event.timestamp;
        }

        if (data.event.metrics) {
            const m = data.event.metrics;
            document.getElementById("val-xg").innerText = m.xg;
            document.getElementById("bar-xg").style.width = `${m.xg * 100}%`;
            
            document.getElementById("val-pass-diff").innerText = `${m.pass_difficulty}/100`;
            document.getElementById("bar-pass-diff").style.width = `${m.pass_difficulty}%`;
            
            document.getElementById("val-pressure").innerText = m.pressure;
        }
    }

    drawPitch();
}

// TIMELINE SCRUBBER
const timelineSlider = document.getElementById("timeline-slider");
timelineSlider.addEventListener("input", (e) => {
    enterReplayMode();
    currentPlaybackIndex = parseInt(e.target.value, 10);
    if (matchHistory[currentPlaybackIndex]) {
        updateUIWithEvent(matchHistory[currentPlaybackIndex]);
    }
});

// PLAY / PAUSE BUTTON
const playPauseBtn = document.getElementById("play-pause-btn");
playPauseBtn.addEventListener("click", () => {
    isPaused = !isPaused;
    playPauseBtn.innerHTML = isPaused ? `<i class="fa-solid fa-play"></i>` : `<i class="fa-solid fa-pause"></i>`;
});

// EVENT LOG REPLAY
document.getElementById("event-log-container").addEventListener("click", (e) => {
    const item = e.target.closest(".event-item");
    if (!item) return;

    document.querySelectorAll(".event-item").forEach(el => el.classList.remove("active-replay"));
    item.classList.add("active-replay");

    enterReplayMode();
    
    if (matchHistory.length > 0) {
        currentPlaybackIndex = Math.floor(matchHistory.length / 2);
        timelineSlider.value = currentPlaybackIndex;
        updateUIWithEvent(matchHistory[currentPlaybackIndex]);
    }
});

function enterReplayMode() {
    isReplayMode = true;
    const livePill = document.getElementById("live-indicator");
    const returnBtn = document.getElementById("return-live-btn");

    livePill.innerText = "REPLAY";
    livePill.classList.remove("active-live");
    livePill.classList.add("replay-mode");
    returnBtn.style.display = "flex";
}

document.getElementById("return-live-btn").addEventListener("click", () => {
    isReplayMode = false;
    isPaused = false;

    playPauseBtn.innerHTML = `<i class="fa-solid fa-pause"></i>`;

    const livePill = document.getElementById("live-indicator");
    const returnBtn = document.getElementById("return-live-btn");

    livePill.innerText = "LIVE";
    livePill.classList.remove("replay-mode");
    livePill.classList.add("active-live");
    returnBtn.style.display = "none";

    document.querySelectorAll(".event-item").forEach(el => el.classList.remove("active-replay"));

    if (matchHistory.length > 0) {
        currentPlaybackIndex = matchHistory.length - 1;
        timelineSlider.value = currentPlaybackIndex;
        updateUIWithEvent(matchHistory[currentPlaybackIndex]);
    }
});

function sendConfig() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ mode: currentMode, team: selectedTeam, player: focusPlayer }));
    }
}

document.getElementById("team-select").addEventListener("change", (e) => {
    selectedTeam = e.target.value;
    updatePlayerDropdown(selectedTeam);
});

document.getElementById("player-select").addEventListener("change", (e) => {
    focusPlayer = e.target.value;
    sendConfig();
});

document.querySelectorAll(".mode-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        currentMode = btn.dataset.mode;
        
        const focusGroup = document.getElementById("player-focus-container");
        focusGroup.style.display = (currentMode === "PLAYER_CAM") ? "flex" : "none";
        drawPitch();
        sendConfig();
    });
});

// TAB SWITCHER CONTROLLER (5 TABS)
document.querySelectorAll(".drawer-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".drawer-tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(`panel-${btn.dataset.tab}`).classList.add("active");
    });
});

document.getElementById("ai-query-send-btn").addEventListener("click", () => {
    const input = document.getElementById("ai-query-input");
    const responseBox = document.getElementById("ai-query-response");
    
    if (!input.value.trim()) return;
    
    responseBox.innerHTML = `<p><i class="fa-solid fa-spinner fa-spin"></i> Analyzing match telemetry...</p>`;
    setTimeout(() => {
        responseBox.innerHTML = `<p><strong>Tactical Assistant:</strong> Arsenal's right-flank overload creates isolated 1v1 situations for Saka against City's backline.</p>`;
        input.value = "";
    }, 600);
});

updatePlayerDropdown("Arsenal");