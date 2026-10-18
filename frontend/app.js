/* SecondTouch frontend: live pitch, replay, broadcast cards and analysis tabs.
 * The server sends one payload per event with all 22 player positions, the three
 * persona commentaries and the running statistics; this file only draws them. */

const HOME = "Arsenal", AWAY = "ManCity";
const TEAM_COLOR = { Arsenal: "#EF4444", ManCity: "#38BDF8" };
const TEAM_INK = { Arsenal: "#FFFFFF", ManCity: "#06222F" };
const TEAM_SHORT = { Arsenal: "ARS", ManCity: "MCI" };
const TEAM_LABEL = { Arsenal: "Arsenal", ManCity: "Man City" };
const MODE_KEY = { ANALYST: "analyst", CASUAL: "casual", PLAYER_CAM: "player_cam" };
const MODE_LABEL = { ANALYST: "ANALYST", CASUAL: "CASUAL FAN", PLAYER_CAM: "PLAYER CAM" };
const REASON_LABEL = {
    goal: "Goal", shot: "Shot", big_chance: "Big chance", line_breaking_pass: "Line-breaking pass",
    high_press_turnover: "High-press turnover", yellow_card: "Yellow card", red_card: "Red card",
};
const MAX_HISTORY = 2000;
const TRAIL = 4;

const $ = id => document.getElementById(id);
const canvas = $("pitchCanvas");
const ctx = canvas.getContext("2d");

/* ---------- STATE ---------- */
const settings = { mode: "PLAYER_CAM", team: HOME, player: "Saka", speed: 1, lang: "en" };
let squads = null;            // team -> pid -> {name, num, pos, starter}
let interval = 1.5;           // seconds between events at 1x (from the server)
let ws = null, started = false, connId = 0;
let history = [];             // [{key, event, positions, possession, commentary, summary}]
let matchKey = null;
let liveStats = null;
let idx = -1;                 // index of the event on screen
let live = true, replayPlaying = false, replayTimer = null, stopAt = null;
let anim = { start: 0, dur: 800, ballDur: 500, from: null, entry: null };
let drawn = null;             // positions as last drawn, so jumps glide instead of teleport
let hitTargets = [];
let activeTab = "stats", statsTeam = HOME, sortKey = null, sortDir = -1;
const latencies = [];
let askId = 0;

const crests = { Arsenal: new Image(), ManCity: new Image() };
crests.Arsenal.src = "/static/images/arsenal.png";
crests.ManCity.src = "/static/images/mancity.png";
Object.values(crests).forEach(i => i.onload = buildPitchLayer);

const player = (team, pid) => (squads && squads[team] && squads[team][pid]) || { name: pid, num: "", pos: "" };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

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
    renderActiveTab();
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
    [HOME, AWAY].forEach((t, i) => {
        const img = crests[t];
        if (!img.complete || !img.naturalWidth) return;
        const sz = 13 * S;
        c.globalAlpha = 0.12;
        c.drawImage(img, i === 0 ? X(52.5) - sz - 2 * S : X(52.5) + 2 * S, Y(34) - sz / 2, sz, sz);
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
const ease = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
const lerp = (a, b, t) => a + (b - a) * t;

const easeMove = t => -(Math.cos(Math.PI * t) - 1) / 2;

/* Players move for the whole gap between events, so the pitch never freezes. */
function animDuration() {
    return Math.max(250, interval * 1000 / settings.speed);
}

/* The ball travels at its own pace: real flight time from length and ball speed,
 * stretched a little so it can be followed, and done well before the next event. */
function ballDuration(ev, dur) {
    if (!ev.team || ev.event_type === "SUBSTITUTION") return dur * 0.3;
    if (ev.event_type === "DRIBBLE") return dur * 0.9;
    if (ev.event_type === "TACKLE") return dur * 0.35;
    const kmh = ev.metrics.ball_speed_kmh || 60;
    const flight = (ev.length_m || 0) / (kmh / 3.6) * 1000;
    return Math.max(220, Math.min(dur * 0.6, flight * 1.3 / settings.speed));
}

/* Small idle movement so players look like they are jogging, not frozen. */
function jog(pid, now) {
    let h = 0;
    for (const c of pid) h = (h * 31 + c.charCodeAt(0)) % 997;
    return [Math.sin(now / 950 + h) * 0.45, Math.cos(now / 1250 + h * 1.7) * 0.6];
}

function arrowHead(x0, y0, x1, y1, size) {
    const a = Math.atan2(y1 - y0, x1 - x0);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x1 - size * Math.cos(a - 0.45), y1 - size * Math.sin(a - 0.45));
    ctx.lineTo(x1 - size * Math.cos(a + 0.45), y1 - size * Math.sin(a + 0.45));
    ctx.fill();
}

/* The action line (pass, dribble, shot, tackle) drawn up to `t` (0-1). */
function drawAction(ev, t, alpha) {
    if (!ev.team || ev.event_type === "SUBSTITUTION") return;
    const l = ev.location, m = ev.metrics;
    const [x0, y0] = pctPx(l.start_x, l.start_y);
    const [x1, y1] = pctPx(l.end_x, l.end_y);
    const cx = lerp(x0, x1, t), cy = lerp(y0, y1, t);
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.lineCap = "round";
    if (ev.event_type === "SHOT") {
        ctx.fillStyle = "rgba(234,179,8,0.22)";
        ctx.beginPath(); ctx.arc(x0, y0, S * (0.9 + (m.xg || 0) * 6), 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = ctx.fillStyle = "#EAB308"; ctx.lineWidth = 3.5;
    } else if (ev.event_type === "DRIBBLE") {
        ctx.strokeStyle = ctx.fillStyle = TEAM_COLOR[ev.team]; ctx.lineWidth = 3; ctx.setLineDash([2, 6]);
    } else if (ev.event_type === "TACKLE") {
        ctx.strokeStyle = ctx.fillStyle = "#F97316"; ctx.lineWidth = 2;
    } else {
        ctx.strokeStyle = ctx.fillStyle = lerpColor("#22C55E", "#EF4444", (m.pass_difficulty || 0) / 100);
        ctx.lineWidth = 3; ctx.setLineDash([9, 5]);
    }
    if (ev.event_type !== "TACKLE") {
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(cx, cy); ctx.stroke();
        ctx.setLineDash([]);
        if (t >= 1 && ev.outcome !== "INTERCEPTED") arrowHead(x0, y0, x1, y1, Math.max(6, S * 0.9));
    }
    if (t >= 1 && (ev.outcome === "INTERCEPTED" || ev.event_type === "TACKLE")) {
        const s = Math.max(5, S * 0.7);
        ctx.strokeStyle = ev.outcome === "FOUL" ? "#EAB308" : "#F97316"; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(x1 - s, y1 - s); ctx.lineTo(x1 + s, y1 + s);
        ctx.moveTo(x1 + s, y1 - s); ctx.lineTo(x1 - s, y1 + s); ctx.stroke();
    }
    ctx.restore();
}

function interpPositions(from, to, t) {
    const out = {};
    for (const team of [HOME, AWAY]) {
        out[team] = {};
        const tp = to[team] || {}, fp = from ? (from[team] || {}) : tp;
        for (const pid in tp) {
            const a = fp[pid] || [tp[pid][0], team === HOME ? -3 : 103];  // a substitute runs on from the touchline
            out[team][pid] = [lerp(a[0], tp[pid][0], t), lerp(a[1], tp[pid][1], t)];
        }
    }
    return out;
}

function drawPlayers(pos, ev, now, t) {
    hitTargets = [];
    const r = Math.max(6, S * 1.05);
    const camFocus = settings.mode === "PLAYER_CAM";
    const involved = new Set([ev?.player, ev?.receiver, ev?.opponent].filter(Boolean));
    const labels = [];
    // players who left the pitch (sub or red card) fade out
    if (anim.from) {
        for (const team of [HOME, AWAY]) for (const pid in (anim.from[team] || {})) {
            if (pos[team][pid]) continue;
            const [x, y] = pctPx(...anim.from[team][pid]);
            ctx.globalAlpha = Math.max(0, 1 - t);
            ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = TEAM_COLOR[team]; ctx.fill();
            ctx.globalAlpha = 1;
        }
    }
    const screen = {};
    for (const team of [HOME, AWAY]) {
        for (const pid in pos[team]) {
            const [jx, jy] = jog(pid, now);
            const [x, y] = pctPx(pos[team][pid][0] + jx, pos[team][pid][1] + jy);
            screen[`${team}|${pid}`] = [x, y];
            const isFocus = camFocus && team === settings.team && pid === settings.player;
            const isInvolved = involved.has(pid);
            ctx.globalAlpha = camFocus && !isFocus && !isInvolved ? 0.62 : 1;
            ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fillStyle = TEAM_COLOR[team]; ctx.fill();
            ctx.lineWidth = isInvolved ? 2 : 1;
            ctx.strokeStyle = isInvolved ? "#FFFFFF" : "rgba(0,0,0,0.45)"; ctx.stroke();
            ctx.fillStyle = TEAM_INK[team];
            ctx.font = `800 ${Math.max(8, Math.round(r * 0.95))}px system-ui, sans-serif`;
            ctx.textAlign = "center"; ctx.textBaseline = "middle";
            ctx.fillText(player(team, pid).num, x, y + 0.5);
            ctx.globalAlpha = 1;
            if (isFocus) {
                const pulse = (Math.sin(now / 260) + 1) / 2;
                ctx.strokeStyle = `rgba(234,179,8,${0.55 + pulse * 0.45})`; ctx.lineWidth = 2.5;
                ctx.beginPath(); ctx.arc(x, y, r + 4 + pulse * 3, 0, Math.PI * 2); ctx.stroke();
            }
            if (isFocus || pid === ev?.player || (pid === ev?.receiver && t > 0.6)) {
                labels.push([pid.toUpperCase(), x, y - r - 9, isFocus]);
            }
            hitTargets.push({ team, pid, x, y, r: r + 5 });
        }
    }
    ctx.font = "800 11px system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (const [text, x, y, isFocus] of labels) {
        const w = ctx.measureText(text).width + 8;
        ctx.fillStyle = "rgba(8,12,20,0.72)";
        ctx.fillRect(x - w / 2, y - 8, w, 16);
        ctx.fillStyle = isFocus ? "#EAB308" : "#FFFFFF";
        ctx.fillText(text, x, y);
    }
    return screen;
}

/* Who has the ball when this event ends: the server puts the carrier exactly on the ball. */
function carrierAtEnd(entry) {
    const team = entry.possession, l = entry.event.location;
    let best = null, bestD = 1.5;
    for (const [pid, [x, y]] of Object.entries(entry.positions[team] || {})) {
        const d = Math.hypot(x - l.end_x, y - l.end_y);
        if (d < bestD) { best = pid; bestD = d; }
    }
    return best ? `${team}|${best}` : null;
}

/* The ball sits just in front of the carrier's feet (in their attacking direction)
 * so it is never hidden under a player; in flight it travels between them. */
function drawBall(entry, t, screen) {
    const ev = entry.event, l = ev.location;
    const r = Math.max(6, S * 1.05);
    const dir = team => (team === HOME ? 1 : -1) * r * 1.15;
    const startTeam = ev.event_type === "TACKLE" ? (ev.team === HOME ? AWAY : HOME) : (ev.team || entry.possession);
    let [x0, y0] = pctPx(l.start_x, l.start_y);
    x0 += dir(startTeam);
    let [x1, y1] = pctPx(l.end_x, l.end_y);
    const carrier = carrierAtEnd(entry);
    if (carrier && screen[carrier]) {
        [x1, y1] = screen[carrier];  // the receiver collects it on the run
        x1 += dir(entry.possession);
    }
    const x = lerp(x0, x1, t), y = lerp(y0, y1, t);
    const lofted = ev.event_type === "PASS" && (ev.length_m || 0) > 28;
    const lift = lofted ? Math.sin(Math.PI * t) * Math.min(1, ev.length_m / 45) * 3.5 * S : 0;
    const br = Math.max(5, S * 0.65) * (1 + lift / (14 * S));
    ctx.fillStyle = "rgba(0,0,0,0.4)";
    ctx.beginPath(); ctx.ellipse(x, y + br * 0.7, br * 0.95, br * 0.45, 0, 0, Math.PI * 2); ctx.fill();
    ctx.save();
    ctx.shadowColor = "rgba(255,255,255,0.9)"; ctx.shadowBlur = 8;
    ctx.fillStyle = "#FFFFFF";
    ctx.beginPath(); ctx.arc(x, y - lift, br, 0, Math.PI * 2); ctx.fill();
    ctx.restore();
    ctx.strokeStyle = "#111827"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.arc(x, y - lift, br, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = "#111827";
    ctx.beginPath(); ctx.arc(x, y - lift, br * 0.38, 0, Math.PI * 2); ctx.fill();
}

function banner(text, color, sub) {
    ctx.save();
    ctx.font = "900 22px system-ui, sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    const w = Math.max(ctx.measureText(text).width, sub ? ctx.measureText(sub).width * 0.6 : 0) + 36;
    const h = sub ? 56 : 38;
    ctx.fillStyle = "rgba(8,12,20,0.82)";
    ctx.fillRect(X(52.5) - w / 2, Y(10) - h / 2, w, h);
    ctx.fillStyle = color;
    ctx.fillText(text, X(52.5), Y(10) - (sub ? 9 : 0));
    if (sub) {
        ctx.font = "700 12px system-ui, sans-serif"; ctx.fillStyle = "#E5E7EB";
        ctx.fillText(sub, X(52.5), Y(10) + 14);
    }
    ctx.restore();
}

function chip(text, x, y, bg, fg, align = "left") {
    ctx.font = "800 11px system-ui, sans-serif";
    ctx.textBaseline = "middle"; ctx.textAlign = "left";
    const w = ctx.measureText(text).width + 14;
    const left = align === "right" ? x - w : x;
    ctx.fillStyle = bg; ctx.fillRect(left, y, w, 20);
    ctx.fillStyle = fg; ctx.fillText(text, left + 7, y + 10.5);
}

function drawOverlays(ev, t, now) {
    const done = t >= 1;
    if (ev.event_type === "SHOT" && ev.outcome === "GOAL" && done) {
        const k = Math.min(1, (now - anim.start - anim.ballDur) / 700);
        if (k > 0) {
            const [gx, gy] = pctPx(ev.location.end_x, ev.location.end_y);
            ctx.strokeStyle = `rgba(234,179,8,${1 - k})`; ctx.lineWidth = 4;
            ctx.beginPath(); ctx.arc(gx, gy, 10 + k * 50, 0, Math.PI * 2); ctx.stroke();
        }
        banner("GOAL!", "#EAB308", `${ev.player} · ${TEAM_LABEL[ev.team]} ${ev.score.home}-${ev.score.away}`);
    } else if (ev.card && done) {
        banner(ev.card === "RED" ? "RED CARD" : "YELLOW CARD", ev.card === "RED" ? "#EF4444" : "#EAB308",
            `${ev.player} (${TEAM_LABEL[ev.team]}) on ${ev.opponent}`);
    } else if (ev.event_type === "SUBSTITUTION") {
        banner("SUBSTITUTION", "#E5E7EB", `${TEAM_LABEL[ev.team]}: ${ev.player} on, ${ev.player_off} off`);
    } else if (ev.event_type === "HALF_TIME" || ev.event_type === "FULL_TIME") {
        banner(ev.event_type === "HALF_TIME" ? "HALF-TIME" : "FULL-TIME", "#FFFFFF",
            `Arsenal ${ev.score.home}-${ev.score.away} Man City`);
    }
    if (ev.is_impact_moment) {
        const why = ev.impact_reasons.map(r => REASON_LABEL[r] || r).join(" · ");
        chip(`⚡ IMPACT · ${why}`, 8, 8, "rgba(234,179,8,0.92)", "#000");
    }
    if (!live) chip(`REPLAY ${ev.clock}`, W - 8, 8, "rgba(8,12,20,0.85)", "#EAB308", "right");
}

function frame(now) {
    if (W) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.drawImage(pitchLayer, 0, 0, W, H);
        const entry = anim.entry;
        if (entry) {
            const tp = Math.min(1, (now - anim.start) / anim.dur);      // players
            const tb = Math.min(1, (now - anim.start) / anim.ballDur);  // ball
            for (let k = TRAIL; k >= 1; k--) {
                const prev = history[idx - k];
                if (prev && prev.key === entry.key) drawAction(prev.event, 1, 0.42 - k * 0.08);
            }
            drawAction(entry.event, ease(tb), 1);
            drawn = interpPositions(anim.from, entry.positions, easeMove(tp));
            const screen = drawPlayers(drawn, entry.event, now, tp);
            drawBall(entry, entry.event.event_type === "DRIBBLE" ? easeMove(tb) : ease(tb), screen);
            drawOverlays(entry.event, tb, now);
        } else {
            ctx.fillStyle = "rgba(255,255,255,0.75)";
            ctx.font = "700 14px system-ui, sans-serif"; ctx.textAlign = "center";
            ctx.fillText("Press START MATCH to kick off", X(52.5), Y(34) + 30 * S / 4);
        }
    }
    requestAnimationFrame(frame);
}

canvas.addEventListener("click", e => {
    const r = canvas.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const hit = hitTargets.find(h => Math.hypot(h.x - x, h.y - y) <= h.r);
    if (hit) setFocus(hit.team, hit.pid);
});
canvas.addEventListener("mousemove", e => {
    const r = canvas.getBoundingClientRect();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    canvas.style.cursor = hitTargets.some(h => Math.hypot(h.x - x, h.y - y) <= h.r) ? "pointer" : "default";
});

/* ---------- BROADCAST CARDS ---------- */
function setMetric(valId, barId, value, pct, suffix = "") {
    $(valId).innerText = value == null ? "—" : value + suffix;
    $(barId).style.width = `${value == null ? 0 : pct}%`;
}

function showCommentary(entry, flash = false) {
    const c = entry.commentary;
    const text = c[MODE_KEY[settings.mode]];
    $("ai-commentary").innerText = text;
    const lang = { en: "EN", es: "ES", ja: "JA" }[c.lang] || "";
    $("ai-source").innerText = `${c.source} · ${MODE_LABEL[settings.mode]} · ${lang}`;
    $("ai-source").classList.toggle("from-azure", c.source === "AZURE OPENAI");
    const ev = entry.event;
    const badge = $("impact-badge");
    badge.hidden = !ev.is_impact_moment;
    badge.innerText = ev.is_impact_moment ? `⚡ ${ev.impact_reasons.map(r => REASON_LABEL[r] || r)[0]}` : "";
    if (flash) {
        const card = $("ai-card");
        card.classList.remove("ai-flash"); void card.offsetWidth; card.classList.add("ai-flash");
    }
}

function updateUI(entry) {
    const ev = entry.event, m = ev.metrics;
    showCommentary(entry);
    $("match-clock").innerText = ev.clock;
    $("score-home").innerText = ev.score.home;
    $("score-away").innerText = ev.score.away;
    $("replay-time").innerText = ev.clock;
    const poss = entry.summary.possession;
    $("poss-home-label").innerText = `${poss[0]}%`;
    $("poss-away-label").innerText = `${poss[1]}%`;
    $("poss-home-bar").style.width = `${poss[0]}%`;

    const actor = $("telemetry-actor");
    if (ev.team) {
        actor.innerText = `#${player(ev.team, ev.player).num} ${ev.player} · ${TEAM_SHORT[ev.team]} · ${ev.event_type}`;
        actor.style.borderColor = TEAM_COLOR[ev.team];
    } else {
        actor.innerText = ev.event_type.replace("_", " ");
        actor.style.borderColor = "";
    }
    setMetric("val-xg", "bar-xg", m.xg, (m.xg || 0) * 100);
    setMetric("val-pass-diff", "bar-pass-diff", m.pass_difficulty, m.pass_difficulty, "/100");
    $("val-pressure").innerText = m.pressure ? `${m.pressure} · ${m.pressure_index}` : "—";
    $("val-defender").innerText = m.nearest_defender_m != null ? `nearest defender ${m.nearest_defender_m}m` : "";
    $("bar-pressure").style.width = `${m.pressure_index || 0}%`;
    $("val-ball-speed").innerText = m.ball_speed_kmh != null ? `${m.ball_speed_kmh} km/h` : "—";
    $("val-gain").innerText = m.forward_gain_m != null ? `${m.forward_gain_m} m` : "—";
    $("val-bypassed").innerText = m.players_bypassed != null ? m.players_bypassed : "—";
}

/* ---------- TIMELINE / REPLAY ---------- */
function show(i) {
    if (!history[i]) return;
    const prevEntry = anim.entry;
    idx = i;
    const sameMatch = prevEntry && prevEntry.key === history[i].key;
    const dur = animDuration();
    anim = { start: performance.now(), dur, ballDur: ballDuration(history[i].event, dur), from: sameMatch ? drawn : null, entry: history[i] };
    $("timeline-slider").value = i;
    updateUI(history[i]);
    document.querySelectorAll(".event-item.active-replay").forEach(el => el.classList.remove("active-replay"));
    if (!live) {
        const el = document.querySelector(`.event-item[data-seq="${history[i].event.seq}"]`);
        if (el) { el.classList.add("active-replay"); el.scrollIntoView({ block: "nearest" }); }
    }
    updateLiveButton();
}

function updateLiveButton() {
    const btn = $("return-live-btn");
    const behind = history.length - 1 - idx;
    btn.classList.toggle("is-live", live);
    $("return-live-text").innerText = live ? "LIVE" : `GO LIVE${behind > 0 ? ` · +${behind}` : ""}`;
    $("play-pause-btn").innerHTML = `<i class="fa-solid fa-${live || replayPlaying ? "pause" : "play"}"></i>`;
    const pill = $("live-indicator");
    if (!started) return;
    pill.innerText = live ? "LIVE" : (replayPlaying ? "REPLAY ▶" : "PAUSED");
    pill.classList.toggle("active-live", live);
    pill.classList.toggle("replay-mode", !live);
}

function enterReplay() {
    if (live) { live = false; }
    updateLiveButton();
}

function goLive() {
    live = true; replayPlaying = false; stopAt = null;
    clearTimeout(replayTimer);
    show(history.length - 1);
}

function stepReplay() {
    clearTimeout(replayTimer);
    if (!replayPlaying) return;
    if (idx >= history.length - 1) { goLive(); return; }
    show(idx + 1);
    if (stopAt != null && idx >= stopAt) { pauseReplay(); return; }
    replayTimer = setTimeout(stepReplay, interval * 1000 / settings.speed);
}

function playReplay() {
    enterReplay();
    replayPlaying = true;
    updateLiveButton();
    replayTimer = setTimeout(stepReplay, 150);
}

function pauseReplay() {
    replayPlaying = false; stopAt = null;
    clearTimeout(replayTimer);
    enterReplay();
}

/* Replay the build-up to an event: three actions before it, stopping just after. */
function replayBuildUp(seq) {
    const i = history.findIndex(h => h.key === matchKey && h.event.seq === seq);
    if (i < 0) return;
    pauseReplay();
    show(Math.max(0, i - 3));
    stopAt = Math.min(history.length - 1, i + 1);
    replayPlaying = true;
    updateLiveButton();
    replayTimer = setTimeout(stepReplay, interval * 1000 / settings.speed);
}

function jumpTo(seq) {
    const i = history.findIndex(h => h.key === matchKey && h.event.seq === seq);
    if (i < 0) return;
    pauseReplay();
    show(i);
}

$("play-pause-btn").addEventListener("click", togglePlay);
function togglePlay() {
    if (!history.length) return;
    if (live) pauseReplay();
    else if (replayPlaying) pauseReplay();
    else playReplay();
}
$("step-back-btn").addEventListener("click", () => { if (history.length) { pauseReplay(); show(Math.max(0, idx - 1)); } });
$("step-fwd-btn").addEventListener("click", () => {
    if (!history.length) return;
    if (idx >= history.length - 1) { goLive(); return; }
    pauseReplay(); show(idx + 1);
});
$("timeline-slider").addEventListener("input", e => {
    pauseReplay();
    const i = parseInt(e.target.value, 10);
    if (i >= history.length - 1) goLive(); else show(i);
});
$("return-live-btn").addEventListener("click", goLive);

document.addEventListener("keydown", e => {
    if (e.target.closest("input, select, textarea")) return;
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); $("step-back-btn").click(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); $("step-fwd-btn").click(); }
    else if (e.key.toLowerCase() === "l") goLive();
});

function renderMarkers() {
    const box = $("timeline-markers");
    const n = history.length;
    if (n < 2) { box.innerHTML = ""; return; }
    const marks = [];
    history.forEach((h, i) => {
        const ev = h.event;
        let cls = null, label = "";
        if (ev.outcome === "GOAL") { cls = "goal"; label = `⚽ ${ev.clock} ${ev.player}`; }
        else if (ev.card) { cls = ev.card === "RED" ? "red" : "yellow"; label = `${ev.card === "RED" ? "🟥" : "🟨"} ${ev.clock} ${ev.player}`; }
        else if (ev.event_type === "HALF_TIME") { cls = "ht"; label = "Half-time"; }
        if (cls) marks.push(`<button class="tl-mark ${cls}" style="left:${(100 * i / (n - 1)).toFixed(2)}%" data-seq="${ev.seq}" title="${esc(label)}" aria-label="${esc(label)}"></button>`);
    });
    box.innerHTML = marks.join("");
}
$("timeline-markers").addEventListener("click", e => {
    const b = e.target.closest(".tl-mark");
    if (b) replayBuildUp(+b.dataset.seq);
});

/* ---------- EVENT LOG & KEY EVENTS ---------- */
const ICON = { GOAL: "⚽", SAVED: "🧤", MISS: "🎯", BLOCKED: "🧱", COMPLETE: "➡️", INTERCEPTED: "✂️", SUCCESS: "💨",
               WON: "🛡️", FOUL: "🚩", SUBSTITUTION: "🔁", HALF_TIME: "⏸", FULL_TIME: "🏁" };

function logLabel(ev) {
    switch (ev.event_type) {
        case "PASS": return ev.outcome === "COMPLETE" ? `PASS → ${ev.receiver}` : `PASS INTERCEPTED by ${ev.opponent}`;
        case "DRIBBLE": return "DRIBBLE";
        case "SHOT": return `SHOT · ${ev.outcome}`;
        case "TACKLE": return ev.outcome === "WON" ? `TACKLE WON on ${ev.opponent}` : `FOUL on ${ev.opponent}${ev.card ? (ev.card === "RED" ? " 🟥" : " 🟨") : ""}`;
        case "SUBSTITUTION": return `SUB ${ev.player} ⇄ ${ev.player_off}`;
        default: return ev.event_type.replace("_", " ");
    }
}

function addLogItem(entry) {
    const ev = entry.event;
    const item = document.createElement("div");
    item.className = `event-item clickable new${ev.is_impact_moment ? " impact" : ""}`;
    item.dataset.seq = ev.seq;
    item.setAttribute("role", "button");
    item.tabIndex = 0;
    const who = ev.team && ev.event_type !== "SUBSTITUTION"
        ? `<span class="team-tag" style="--tc:${TEAM_COLOR[ev.team]}">${esc(ev.player)}</span> ` : "";
    item.innerHTML = `<span class="event-time">${esc(ev.clock)}</span><span>${ICON[ev.outcome || ev.event_type] || "•"} ${who}<strong>${esc(logLabel(ev))}</strong>${ev.is_impact_moment ? ' <span class="zap">⚡</span>' : ""}</span>`;
    const list = $("event-log-container");
    list.prepend(item);
    while (list.children.length > 150) list.lastChild.remove();
    $("event-count").innerText = `${ev.seq} events`;
}

function onLogActivate(e) {
    const item = e.target.closest(".event-item");
    if (!item || (e.type === "keydown" && e.key !== "Enter" && e.key !== " ")) return;
    e.preventDefault();
    jumpTo(+item.dataset.seq);
}
$("event-log-container").addEventListener("click", onLogActivate);
$("event-log-container").addEventListener("keydown", onLogActivate);
$("impact-only").addEventListener("change", e => $("event-log-container").classList.toggle("impact-only", e.target.checked));

function isKeyEvent(ev) {
    return ev.outcome === "GOAL" || ev.card || ev.event_type === "SUBSTITUTION" || ev.event_type === "HALF_TIME"
        || ev.event_type === "FULL_TIME" || (ev.event_type === "SHOT" && (ev.metrics.xg >= 0.3 || ev.outcome === "SAVED"));
}

function keyEventText(ev) {
    const xg = ev.metrics.xg != null ? ` (${ev.metrics.xg.toFixed(2)} xG)` : "";
    if (ev.outcome === "GOAL") return `⚽ <strong>GOAL</strong> ${esc(ev.player)}, ${TEAM_LABEL[ev.team]}${xg} · ${ev.score.home}-${ev.score.away}`;
    if (ev.card) return `${ev.card === "RED" ? "🟥 <strong>RED CARD</strong>" : "🟨 <strong>YELLOW CARD</strong>"} ${esc(ev.player)} (${TEAM_LABEL[ev.team]}) for a foul on ${esc(ev.opponent)}`;
    if (ev.event_type === "SUBSTITUTION") return `🔁 <strong>SUB</strong> ${TEAM_LABEL[ev.team]}: ${esc(ev.player)} on, ${esc(ev.player_off)} off`;
    if (ev.event_type === "HALF_TIME") return `⏸ <strong>HALF-TIME</strong> Arsenal ${ev.score.home}-${ev.score.away} Man City`;
    if (ev.event_type === "FULL_TIME") return `🏁 <strong>FULL-TIME</strong> Arsenal ${ev.score.home}-${ev.score.away} Man City`;
    if (ev.outcome === "SAVED") return `🧤 <strong>SAVE</strong> ${esc(ev.opponent)} denies ${esc(ev.player)}${xg}`;
    return `🎯 <strong>BIG CHANCE</strong> ${esc(ev.player)}, ${TEAM_LABEL[ev.team]}${xg}: ${ev.outcome.toLowerCase()}`;
}

function addKeyEvent(entry) {
    const ev = entry.event;
    if (!isKeyEvent(ev)) return;
    const li = document.createElement("li");
    li.dataset.seq = ev.seq;
    li.tabIndex = 0;
    li.className = `ke ${ev.team ? (ev.team === HOME ? "home" : "away") : "neutral"}`;
    li.innerHTML = `<span class="time-tag">${esc(ev.clock)}</span> ${keyEventText(ev)} <span class="replay-hint"><i class="fa-solid fa-rotate-left"></i> replay</span>`;
    $("key-events-list").prepend(li);
}
function onKeyEventActivate(e) {
    const li = e.target.closest("li[data-seq]");
    if (!li || (e.type === "keydown" && e.key !== "Enter")) return;
    replayBuildUp(+li.dataset.seq);
}
$("key-events-list").addEventListener("click", onKeyEventActivate);
$("key-events-list").addEventListener("keydown", onKeyEventActivate);

/* ---------- MATCH STATS TAB ---------- */
const H2H = [
    ["Possession", s => s.possession, v => `${v}%`],
    ["Shots", s => s.shots], ["Shots on target", s => s.on_target],
    ["Expected goals (xG)", s => s.xg, v => v.toFixed(2)], ["Big chances", s => s.big_chances],
    ["Passes", s => s.passes], ["Pass accuracy", s => s.pass_pct, v => `${v}%`],
    ["Tackles won", s => s.tackles_won], ["Interceptions", s => s.interceptions],
    ["Saves", s => s.saves], ["Fouls", s => s.fouls], ["Yellow cards", s => s.yellow], ["Red cards", s => s.red],
];

function renderStats() {
    if (!liveStats) return;
    const h = liveStats.teams[HOME], a = liveStats.teams[AWAY];
    $("rating-home").innerText = h.rating.toFixed(1);
    $("rating-away").innerText = a.rating.toFixed(1);
    $("h2h-list").innerHTML = H2H.map(([label, get, fmt = v => v]) => {
        const hv = get(h), av = get(a), tot = hv + av;
        const hp = tot ? 100 * hv / tot : 50;
        return `<div class="h2h-row">
            <span class="h2h-val ${hv > av ? "lead" : ""}">${fmt(hv)}</span>
            <div class="h2h-mid"><span class="h2h-label">${label}</span>
              <div class="h2h-bar"><div class="h2h-home" style="width:${hp}%"></div><div class="h2h-away" style="width:${100 - hp}%"></div></div></div>
            <span class="h2h-val ${av > hv ? "lead" : ""}">${fmt(av)}</span></div>`;
    }).join("");
    renderPlayerTable();
}

const COLS = [
    ["num", "#"], ["name", "Player"], ["pos", "Pos"], ["minutes", "Min"], ["rating", "Rating"],
    ["goals", "G"], ["assists", "A"], ["shots", "Shots (OT)"], ["xg", "xG"], ["passes", "Passes"],
    ["key_passes", "Key P."], ["dribbles_won", "Dribbles"], ["tackles_won", "Tackles"],
    ["interceptions", "Int."], ["saves", "Saves"], ["fouls", "Fouls"], ["cards", "Cards"],
    ["touches", "Touches"], ["sprints", "Sprints"],
];
const COL_TITLE = {
    minutes: "Minutes played", rating: "Match rating (starts at 6.0)", goals: "Goals", assists: "Assists",
    shots: "Shots (on target)", passes: "Completed / attempted passes", key_passes: "Passes that led to a shot",
    dribbles_won: "Successful / attempted dribbles", tackles_won: "Tackles won / attempted",
    interceptions: "Interceptions", touches: "Touches of the ball", sprints: "Sprints and runs in behind",
};

function renderPlayerTable() {
    if (!liveStats) return;
    let rows = liveStats.players[statsTeam].slice();
    if (sortKey) {
        const v = r => sortKey === "cards" ? r.red * 2 + r.yellow : sortKey === "name" || sortKey === "pos" ? r[sortKey] : (r[sortKey] ?? -1);
        rows.sort((a, b) => (v(a) > v(b) ? 1 : v(a) < v(b) ? -1 : 0) * sortDir);
    }
    const ratingCls = r => r == null ? "" : r >= 7.5 ? "r-high" : r >= 6.5 ? "r-good" : r >= 6.0 ? "r-mid" : "r-low";
    const head = `<thead><tr>${COLS.map(([k, l]) =>
        `<th data-key="${k}" title="${COL_TITLE[k] || ""}" class="${sortKey === k ? (sortDir > 0 ? "asc" : "desc") : ""}">${l}</th>`).join("")}</tr></thead>`;
    const body = rows.map(r => {
        const focus = settings.team === statsTeam && settings.player === r.id;
        const subTxt = r.sub_on != null ? ` <span class="sub-on">↑${r.sub_on}'</span>` : "";
        const offTxt = r.sub_off != null ? ` <span class="sub-off">${r.red ? "🟥" : "↓"}${r.sub_off}'</span>` : "";
        const cards = "🟨".repeat(r.yellow) + "🟥".repeat(r.red) || "–";
        return `<tr class="${r.minutes === 0 && r.sub_on == null && !r.starter ? "bench" : ""}${focus ? " focus" : ""}" data-pid="${esc(r.id)}">
            <td class="num">${r.num}</td><td class="pname">${esc(r.name)}${subTxt}${offTxt}</td><td>${r.pos}</td>
            <td>${r.minutes}</td><td><span class="rating ${ratingCls(r.rating)}">${r.rating ?? "–"}</span></td>
            <td>${r.goals || "–"}</td><td>${r.assists || "–"}</td><td>${r.shots} (${r.on_target})</td><td>${r.xg.toFixed(2)}</td>
            <td>${r.passes_completed}/${r.passes}</td><td>${r.key_passes}</td><td>${r.dribbles_won}/${r.dribbles}</td>
            <td>${r.tackles_won}/${r.tackles}</td><td>${r.interceptions}</td><td>${r.saves}</td><td>${r.fouls}</td>
            <td>${cards}</td><td>${r.touches}</td><td>${r.sprints}</td></tr>`;
    }).join("");
    $("player-table").innerHTML = head + `<tbody>${body}</tbody>`;
}

$("player-table").addEventListener("click", e => {
    const th = e.target.closest("th");
    if (th) {
        const k = th.dataset.key;
        sortDir = sortKey === k ? -sortDir : (k === "name" || k === "pos" || k === "num" ? 1 : -1);
        sortKey = k;
        renderPlayerTable();
        return;
    }
    const tr = e.target.closest("tr[data-pid]");
    if (tr) setFocus(statsTeam, tr.dataset.pid);
});
document.querySelectorAll(".seg-btn").forEach(b => b.addEventListener("click", () => {
    document.querySelectorAll(".seg-btn").forEach(x => x.classList.toggle("active", x === b));
    statsTeam = b.dataset.team;
    renderPlayerTable();
}));

/* ---------- TACTICS TAB ---------- */
function tacticalRead(team, tac, opp) {
    const parts = [];
    const oop = tac.out_of_possession, inp = tac.in_possession;
    if (oop) {
        const lh = oop.line_height_m;
        parts.push(lh >= 38 ? `Defending high: the back line holds ${lh}m from goal, squeezing the space behind the press.`
            : lh >= 30 ? `A mid-block: the back line sits ${lh}m out and the team stays ${oop.length_m}m from back to front.`
            : `A low block: the back line drops to ${lh}m and protects the box.`);
    }
    if (inp) parts.push(inp.width_m >= 48 ? `In possession they stretch the pitch to ${inp.width_m}m wide.` : `In possession they stay narrow (${inp.width_m}m), overloading the middle.`);
    const ch = tac.channels, fav = Object.keys(ch).reduce((a, b) => ch[a] >= ch[b] ? a : b);
    if (tac.final_third_actions >= 4) parts.push(fav === "central" ? `Attacks go mostly through the centre (${ch.central}%).` : `Attacks lean down the ${fav} (${ch[fav]}% of final-third actions).`);
    if (tac.press_wins + opp.press_wins >= 3) parts.push(tac.press_wins > opp.press_wins
        ? `Their press is winning the battle: ${tac.press_wins} ball wins in the opponent's half to ${opp.press_wins}.`
        : `They are being out-pressed: ${tac.press_wins} ball wins in the opponent's half to ${opp.press_wins}.`);
    return parts.join(" ") || "Not enough of the match yet to read the shape.";
}

function phaseRow(label, p) {
    if (!p) return `<tr><th>${label}</th><td colspan="3" class="text-muted">no data yet</td></tr>`;
    return `<tr><th>${label}</th><td>${p.line_height_m}m</td><td>${p.width_m}m</td><td>${p.length_m}m</td></tr>`;
}

function renderTactics() {
    if (!liveStats) return;
    const T = liveStats.tactics;
    $("tactics-cards").innerHTML = [HOME, AWAY].map(team => {
        const tac = T[team], opp = T[team === HOME ? AWAY : HOME], ch = tac.channels;
        return `<div class="tactical-card ${team === HOME ? "home-border" : "away-border"}">
            <h5>${TEAM_LABEL[team]} · ${tac.formation}</h5>
            <p class="tactical-read">${tacticalRead(team, tac, opp)}</p>
            <table class="shape-table"><thead><tr><th></th><th title="Average distance of the back line from its own goal">Line height</th><th title="Distance between the widest outfield players">Width</th><th title="Distance from the back line to the most advanced player">Length</th></tr></thead>
              <tbody>${phaseRow("In possession", tac.in_possession)}${phaseRow("Out of possession", tac.out_of_possession)}</tbody></table>
            <div class="channel-label">Attack channels (final-third actions: ${tac.final_third_actions})</div>
            <div class="channel-bar">
              <div style="width:${ch.left}%" title="Left ${ch.left}%">${ch.left >= 12 ? `L ${ch.left}%` : ""}</div>
              <div style="width:${ch.central}%" title="Centre ${ch.central}%">${ch.central >= 12 ? `C ${ch.central}%` : ""}</div>
              <div style="width:${ch.right}%" title="Right ${ch.right}%">${ch.right >= 12 ? `R ${ch.right}%` : ""}</div>
            </div>
            <div class="press-row"><span>Ball wins in opponent half <strong>${tac.press_wins}</strong></span>
              <span title="Opponent passes allowed per defensive action in their own 60%. Lower = more aggressive press.">PPDA <strong>${tac.ppda ?? "–"}</strong></span></div>
        </div>`;
    }).join("");
    renderAvgPitch(T);
}

function pitchSvg() {
    const box = 16.5, six = 5.5;
    return `<rect x="0" y="0" width="105" height="68" class="pl"/>
        <line x1="52.5" y1="0" x2="52.5" y2="68" class="pl"/><circle cx="52.5" cy="34" r="9.15" class="pl"/>
        <rect x="0" y="${34 - 20.16}" width="${box}" height="40.32" class="pl"/><rect x="${105 - box}" y="${34 - 20.16}" width="${box}" height="40.32" class="pl"/>
        <rect x="0" y="${34 - 9.16}" width="${six}" height="18.32" class="pl"/><rect x="${105 - six}" y="${34 - 9.16}" width="${six}" height="18.32" class="pl"/>`;
}

function renderAvgPitch(T) {
    let dots = "";
    for (const team of [HOME, AWAY]) {
        for (const [pid, [x, y]] of Object.entries(T[team].avg_positions)) {
            const p = player(team, pid);
            dots += `<g class="avg-dot" data-tip="${esc(p.name)} (${p.pos}) · ${TEAM_LABEL[team]}">
                <circle cx="${(x * 1.05).toFixed(1)}" cy="${(y * 0.68).toFixed(1)}" r="2.4" fill="${TEAM_COLOR[team]}" stroke="#111827" stroke-width="0.4"/>
                <text x="${(x * 1.05).toFixed(1)}" y="${(y * 0.68 + 0.9).toFixed(1)}" fill="${TEAM_INK[team]}">${p.num}</text></g>`;
        }
    }
    $("avg-pitch").innerHTML = pitchSvg() + dots;
}

/* ---------- IN-DEPTH ANALYSIS TAB ---------- */
function matchEntries() { return history.filter(h => h.key === matchKey); }

function renderXgChart() {
    const svg = $("xg-chart");
    const w = svg.getBoundingClientRect().width || 600, h = 170, m = { l: 34, r: 74, t: 10, b: 22 };
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const entries = matchEntries();
    const pts = [[0, 0, 0]];
    const goals = [];
    entries.forEach(e => {
        pts.push([e.event.minute, e.summary.xg[0], e.summary.xg[1]]);
        if (e.event.outcome === "GOAL") goals.push([e.event.minute, e.event.team, e.summary.xg[e.event.team === HOME ? 0 : 1], e.event.player]);
    });
    const maxY = Math.max(1, ...pts.map(p => Math.max(p[1], p[2]))) * 1.1;
    const sx = v => m.l + (w - m.l - m.r) * v / 90, sy = v => h - m.b - (h - m.t - m.b) * v / maxY;
    const step = k => pts.map((p, i) => `${i ? "H" : "M"}${sx(p[0]).toFixed(1)}${i ? "" : `,${sy(p[k]).toFixed(1)}`}${i ? ` V${sy(p[k]).toFixed(1)}` : ""}`).join(" ");
    let grid = "";
    for (let v = 0; v <= maxY; v += maxY > 3 ? 1 : 0.5) grid += `<line x1="${m.l}" x2="${w - m.r}" y1="${sy(v)}" y2="${sy(v)}" class="grid"/><text x="${m.l - 6}" y="${sy(v) + 3}" class="axis" text-anchor="end">${v.toFixed(1)}</text>`;
    for (const v of [0, 15, 30, 45, 60, 75, 90]) grid += `<text x="${sx(v)}" y="${h - 6}" class="axis" text-anchor="middle">${v}'</text>`;
    const last = pts[pts.length - 1];
    const labelY = [sy(last[1]), sy(last[2])];
    if (Math.abs(labelY[0] - labelY[1]) < 13) { const mid = (labelY[0] + labelY[1]) / 2; labelY[0] = mid + (last[1] >= last[2] ? -7 : 7); labelY[1] = mid + (last[1] >= last[2] ? 7 : -7); }
    svg.innerHTML = grid +
        `<path d="${step(1)}" class="xg-line" stroke="${TEAM_COLOR[HOME]}"/><path d="${step(2)}" class="xg-line" stroke="${TEAM_COLOR[AWAY]}"/>` +
        goals.map(([mn, t, v, p]) => `<circle cx="${sx(mn)}" cy="${sy(v)}" r="5" fill="${TEAM_COLOR[t]}" stroke="#111827" stroke-width="2" data-tip="⚽ ${mn.toFixed(0)}' ${esc(p)} (${TEAM_LABEL[t]})"/>`).join("") +
        `<text x="${sx(last[0]) + 8}" y="${labelY[0] + 4}" class="direct-label">ARS ${last[1].toFixed(2)}</text>` +
        `<text x="${sx(last[0]) + 8}" y="${labelY[1] + 4}" class="direct-label">MCI ${last[2].toFixed(2)}</text>` +
        `<line class="crosshair" x1="0" x2="0" y1="${m.t}" y2="${h - m.b}" visibility="hidden"/>` +
        `<rect x="${m.l}" y="${m.t}" width="${w - m.l - m.r}" height="${h - m.t - m.b}" fill="transparent" class="hover-catch"/>`;
    svg._xg = { pts, sx, m, w };
}

$("xg-chart").addEventListener("mousemove", e => {
    const svg = $("xg-chart"), d = svg._xg;
    if (!d || d.pts.length < 2) return;
    const r = svg.getBoundingClientRect();
    const px = (e.clientX - r.left) * (d.w / r.width);
    const minute = Math.max(0, Math.min(90, (px - d.m.l) / (d.w - d.m.l - d.m.r) * 90));
    let p = d.pts[0];
    for (const q of d.pts) { if (q[0] <= minute) p = q; else break; }
    const ch = svg.querySelector(".crosshair");
    ch.setAttribute("x1", d.sx(minute)); ch.setAttribute("x2", d.sx(minute)); ch.setAttribute("visibility", "visible");
    tooltip(e, `<strong>${Math.floor(minute)}'</strong><br><span class="sw" style="background:${TEAM_COLOR[HOME]}"></span>Arsenal ${p[1].toFixed(2)} xG<br><span class="sw" style="background:${TEAM_COLOR[AWAY]}"></span>Man City ${p[2].toFixed(2)} xG`);
});
$("xg-chart").addEventListener("mouseleave", () => {
    const ch = $("xg-chart").querySelector(".crosshair");
    if (ch) ch.setAttribute("visibility", "hidden");
    hideTooltip();
});

function renderMomentum() {
    const svg = $("momentum-chart");
    const w = svg.getBoundingClientRect().width || 600, h = 110, m = { l: 34, r: 10, t: 6, b: 18 };
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const buckets = new Map();
    for (const e of matchEntries()) {
        if (!e.event.team) continue;
        const b = Math.min(29, Math.floor(e.event.minute / 3));
        const arr = buckets.get(b) || []; arr.push(e.summary.momentum); buckets.set(b, arr);
    }
    const bw = (w - m.l - m.r) / 30, mid = m.t + (h - m.t - m.b) / 2, half = (h - m.t - m.b) / 2;
    let bars = `<line x1="${m.l}" x2="${w - m.r}" y1="${mid}" y2="${mid}" class="baseline"/>
        <text x="${m.l - 6}" y="${m.t + 9}" class="axis" text-anchor="end">ARS</text><text x="${m.l - 6}" y="${h - m.b}" class="axis" text-anchor="end">MCI</text>`;
    for (const v of [0, 45, 90]) bars += `<text x="${m.l + (w - m.l - m.r) * v / 90}" y="${h - 4}" class="axis" text-anchor="middle">${v}'</text>`;
    for (const [b, vals] of buckets) {
        const v = vals.reduce((s, x) => s + x, 0) / vals.length;
        const bh = Math.max(1, Math.abs(v) / 100 * half);
        const x = m.l + b * bw + 1, y = v >= 0 ? mid - bh : mid;
        const team = v >= 0 ? HOME : AWAY;
        bars += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${bh.toFixed(1)}" rx="2" fill="${TEAM_COLOR[team]}"
            data-tip="${b * 3}'-${b * 3 + 3}': ${Math.abs(v) < 8 ? "even" : `${TEAM_LABEL[team]} on top (${Math.round(Math.abs(v))})`}"/>`;
    }
    svg.innerHTML = bars;
}

function renderShotMap() {
    let dots = "";
    for (const e of matchEntries()) {
        const ev = e.event;
        if (ev.event_type !== "SHOT") continue;
        const x = ev.location.start_x * 1.05, y = ev.location.start_y * 0.68, r = 0.9 + ev.metrics.xg * 4.5;
        const goal = ev.outcome === "GOAL", c = TEAM_COLOR[ev.team];
        dots += `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(2)}" fill="${goal ? c : "transparent"}" stroke="${c}" stroke-width="${goal ? 0.5 : 0.7}" class="shot-dot" data-seq="${ev.seq}"
            data-tip="${ev.clock} ${esc(ev.player)} (${TEAM_LABEL[ev.team]}) · ${ev.metrics.xg.toFixed(2)} xG · ${ev.outcome}"/>`;
    }
    $("shot-map").innerHTML = pitchSvg() + dots;
}
$("shot-map").addEventListener("click", e => { const d = e.target.closest(".shot-dot"); if (d) replayBuildUp(+d.dataset.seq); });

function renderImpactList() {
    const items = matchEntries().filter(e => e.event.is_impact_moment).slice(-30).reverse();
    $("impact-list").innerHTML = items.map(e => {
        const ev = e.event;
        return `<li data-seq="${ev.seq}" tabindex="0"><span class="time-tag">${ev.clock}</span>
            <span class="reason">${ev.impact_reasons.map(r => REASON_LABEL[r] || r).join(" · ")}</span>
            <span class="src ${e.commentary.source === "AZURE OPENAI" ? "from-azure" : ""}">${e.commentary.source === "AZURE OPENAI" ? "AI" : "local"}</span>
            <p>${esc(e.commentary.analyst)}</p></li>`;
    }).join("") || `<li class="text-muted">No impact moments yet.</li>`;
}
$("impact-list").addEventListener("click", e => { const li = e.target.closest("li[data-seq]"); if (li) replayBuildUp(+li.dataset.seq); });

function renderAnalysis() { renderXgChart(); renderMomentum(); renderShotMap(); renderImpactList(); }

/* ---------- TOOLTIP ---------- */
function tooltip(e, html) {
    const tip = $("chart-tooltip");
    tip.innerHTML = html; tip.hidden = false;
    const pad = 14, tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = e.clientX + pad, y = e.clientY + pad;
    if (x + tw > window.innerWidth - 8) x = e.clientX - tw - pad;
    if (y + th > window.innerHeight - 8) y = e.clientY - th - pad;
    tip.style.left = `${x}px`; tip.style.top = `${y}px`;
}
function hideTooltip() { $("chart-tooltip").hidden = true; }
document.addEventListener("mouseover", e => {
    const el = e.target.closest("[data-tip]");
    if (el && el.closest("svg")) tooltip(e, esc(el.dataset.tip));
});
document.addEventListener("mousemove", e => {
    const el = e.target.closest("[data-tip]");
    if (el && el.closest("svg")) tooltip(e, esc(el.dataset.tip));
});
document.addEventListener("mouseout", e => { if (e.target.closest("[data-tip]")) hideTooltip(); });

/* ---------- TABS ---------- */
function renderActiveTab() {
    if (activeTab === "stats") renderStats();
    else if (activeTab === "tactics") renderTactics();
    else if (activeTab === "analysis") renderAnalysis();
}
document.querySelectorAll(".drawer-tab-btn").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll(".drawer-tab-btn").forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    activeTab = btn.dataset.tab;
    $(`panel-${activeTab}`).classList.add("active");
    renderActiveTab();
}));

/* ---------- TALK TO AI ---------- */
function ask(question) {
    question = question.trim();
    if (!question) return;
    const box = $("ai-query-response");
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        box.innerHTML = "<p>Start the match first so there is live data to analyse.</p>";
        return;
    }
    const id = ++askId;
    box.querySelector(".placeholder-text")?.remove();
    const qa = document.createElement("div");
    qa.className = "qa";
    qa.dataset.id = id;
    qa.innerHTML = `<p class="q">${esc(question)}</p><p class="a text-muted">Thinking…</p>`;
    box.prepend(qa);
    while (box.children.length > 6) box.lastChild.remove();
    ws.send(JSON.stringify({ type: "ask", id, question }));
    $("ai-query-input").value = "";
}
$("ai-query-send-btn").addEventListener("click", () => ask($("ai-query-input").value));
$("ai-query-input").addEventListener("keydown", e => { if (e.key === "Enter") ask(e.target.value); });
$("ai-suggestions").addEventListener("click", e => { const c = e.target.closest(".chip"); if (c) ask(c.innerText); });

function onAnswer(msg) {
    const qa = document.querySelector(`.qa[data-id="${msg.id}"] .a`);
    if (!qa) return;
    qa.classList.remove("text-muted");
    qa.innerHTML = `${esc(msg.text)} <span class="ai-source ${msg.source === "AZURE OPENAI" ? "from-azure" : ""}">${msg.source}</span>`;
}

/* ---------- SOCKET MESSAGES ---------- */
function resetMatch(key) {
    matchKey = key;
    liveStats = null;
    $("event-log-container").innerHTML = "";
    $("key-events-list").innerHTML = "";
    history = history.filter(h => h.key === key);
    idx = -1;
    anim = { start: 0, dur: 800, ballDur: 500, from: null, entry: null };
    drawn = null;
    live = true; replayPlaying = false; stopAt = null;
    clearTimeout(replayTimer);
}

function onEvent(msg) {
    const key = `${connId}:${msg.match_id}`;
    if (key !== matchKey) resetMatch(key);
    const entry = { key, event: msg.event, positions: msg.positions, possession: msg.possession,
                    commentary: msg.commentary, summary: msg.summary };
    history.push(entry);
    if (history.length > MAX_HISTORY) { history.shift(); idx = Math.max(0, idx - 1); }
    liveStats = msg.stats;
    $("timeline-slider").max = history.length - 1;
    $("replay-duration").innerText = msg.event.clock;
    addLogItem(entry);
    addKeyEvent(entry);
    renderMarkers();
    if (live) show(history.length - 1);
    else updateLiveButton();
    renderActiveTab();
    requestAnimationFrame(() => recordLatency(msg.event.generated_at));
}

function onCommentary(msg) {
    const key = `${connId}:${msg.match_id}`;
    const entry = history.find(h => h.key === key && h.event.seq === msg.seq);
    if (!entry) return;
    entry.commentary = msg.commentary;
    if (entry === anim.entry) showCommentary(entry, msg.commentary.source === "AZURE OPENAI");
    if (activeTab === "analysis") renderImpactList();
}

function recordLatency(generatedAt) {
    latencies.push(Math.round(Date.now() - generatedAt));
    if (latencies.length > 100) latencies.shift();
    const sorted = latencies.slice().sort((a, b) => a - b);
    const p95 = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))];
    if (ws && ws.readyState === WebSocket.OPEN) $("connection-text").innerText = `CONNECTED · p95 ${p95} ms`;
    $("connection-badge").classList.toggle("slow", p95 > 2000);
    if (latencies.length === 100 && history.length % 50 === 0) console.info(`[SecondTouch] event-to-render p95 = ${p95} ms (target < 2000 ms)`);
}

function onHello(msg) {
    interval = msg.interval;
    squads = msg.squads;
    buildPlayerDropdown(settings.team, settings.player);
    const st = $("ai-status");
    st.classList.toggle("on", msg.ai_configured);
    $("ai-status-text").innerText = msg.ai_configured ? `AI: Azure · ${msg.deployment}` : "AI: local templates";
    st.title = msg.ai_configured
        ? "Impact moments are explained by Azure OpenAI; other events use the local engine."
        : "No Azure OpenAI keys in .env, so all commentary comes from the local template engine.";
}

/* ---------- CONNECTION ---------- */
function setConnected(on) {
    $("connection-badge").classList.toggle("connected", on);
    $("connection-text").innerText = on ? "CONNECTED" : "RECONNECTING…";
    if (!on) {
        const pill = $("live-indicator");
        pill.innerText = "OFFLINE"; pill.classList.remove("active-live");
    }
}

function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/telemetry`);
    connId += 1;
    ws.onopen = () => { setConnected(true); sendConfig(); updateLiveButton(); };
    ws.onmessage = e => {
        const msg = JSON.parse(e.data);
        if (msg.type === "event") onEvent(msg);
        else if (msg.type === "commentary") onCommentary(msg);
        else if (msg.type === "answer") onAnswer(msg);
        else if (msg.type === "hello") onHello(msg);
    };
    ws.onclose = () => {
        setConnected(false);
        if (started) setTimeout(connect, 2000);
    };
}

function sendConfig() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "config", ...settings }));
    }
}

/* ---------- CONTROLS ---------- */
$("kickoff-btn").addEventListener("click", () => {
    if (started) return;
    started = true;
    $("kickoff-btn").style.display = "none";
    connect();
});

$("speed-select").addEventListener("change", e => {
    settings.speed = parseInt(e.target.value, 10);
    sendConfig();
});

$("lang-select").addEventListener("change", e => {
    settings.lang = e.target.value;
    document.documentElement.lang = settings.lang;
    sendConfig();  // the server re-sends the latest commentary in the new language at once
});

function buildPlayerDropdown(team, selected) {
    const sel = $("player-select");
    if (!squads) return;
    sel.innerHTML = "";
    for (const [pid, p] of Object.entries(squads[team])) {
        const opt = document.createElement("option");
        opt.value = pid;
        opt.innerText = `${p.num}. ${p.name} (${p.pos})${p.starter ? "" : " · bench"}`;
        sel.appendChild(opt);
    }
    sel.value = selected;
}

function defaultPlayer(team) {
    const entries = Object.entries(squads[team]);
    return (entries.find(([, p]) => p.pos === "ST") || entries[0])[0];
}

function setFocus(team, pid) {
    settings.team = team; settings.player = pid;
    $("team-select").value = team;
    buildPlayerDropdown(team, pid);
    setMode("PLAYER_CAM");
    if (activeTab === "stats") renderPlayerTable();
}

$("team-select").addEventListener("change", e => {
    settings.team = e.target.value;
    settings.player = defaultPlayer(settings.team);
    buildPlayerDropdown(settings.team, settings.player);
    sendConfig();
});
$("player-select").addEventListener("change", e => { settings.player = e.target.value; sendConfig(); });

function setMode(mode) {
    settings.mode = mode;
    document.querySelectorAll(".mode-btn").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
    $("player-focus-container").style.display = mode === "PLAYER_CAM" ? "flex" : "none";
    if (anim.entry) showCommentary(anim.entry);  // all three personas are already here: switch instantly
    sendConfig();
}
document.querySelectorAll(".mode-btn").forEach(btn => btn.addEventListener("click", () => setMode(btn.dataset.mode)));

/* ---------- BOOT ---------- */
fetch("/api/squads").then(r => r.json()).then(d => { squads = d.squads; buildPlayerDropdown(settings.team, settings.player); }).catch(() => {});
window.addEventListener("resize", resize);
resize();
requestAnimationFrame(frame);
