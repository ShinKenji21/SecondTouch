/* SecondTouch frontend: live pitch, replay, broadcast cards, mode panels and analysis tabs.
 * The server sends one payload per event with all 22 player positions, the three
 * persona commentaries, alerts, stories, reports, overlay cues and the running
 * statistics; this file only draws them. */

const HOME = "Brackenford", AWAY = "Kestermouth";
const TEAMS = [HOME, AWAY];
const TEAM_COLOR = { Brackenford: "#22B5AF", Kestermouth: "#E8732C" };
const TEAM_INK = { Brackenford: "#04211F", Kestermouth: "#14213D" };
const TEAM_SHORT = { Brackenford: "BRA", Kestermouth: "KHB" };
const TEAM_LABEL = { Brackenford: "Brackenford", Kestermouth: "Kestermouth" };
const MODE_KEY = { ANALYST: "analyst", CASUAL: "casual", PLAYER_CAM: "player_cam" };
const MODE_LABEL = { ANALYST: "ANALYST", CASUAL: "CASUAL FAN", PLAYER_CAM: "PLAYER CAM" };
const REASON_LABEL = {
    goal: "Goal", shot: "Shot", big_chance: "Big chance", line_breaking_pass: "Line-breaking pass",
    high_press_turnover: "High-press turnover", yellow_card: "Yellow card", red_card: "Red card",
    penalty: "Penalty", penalty_awarded: "Penalty awarded", direct_free_kick: "Direct free kick",
};
const SP_LABEL = { FREE_KICK: "Free kick", CORNER: "Corner", THROW_IN: "Throw-in", PENALTY: "Penalty", GOAL_KICK: "Goal kick" };
const ON_BALL = new Set(["PASS", "DRIBBLE", "SHOT"]);
const MAX_HISTORY = 2000;
const TRAIL = 4;

const $ = id => document.getElementById(id);
const canvas = $("pitchCanvas");
const ctx = canvas.getContext("2d");

/* ---------- STATE ---------- */
const settings = { mode: "PLAYER_CAM", team: HOME, player: "Thornquist", speed: 1, lang: "en", fav_team: "NONE" };
let pinned = "none";
let squads = null;            // team -> pid -> {name, num, pos, starter}
let interval = 1.5;           // seconds between events at 1x (from the server)
let ws = null, started = false, connId = 0;
let history = [];             // [{key, event, positions, possession, commentary, summary, alerts, story, report, overlays}]
let matchKey = null, metadata = null;
let liveStats = null;
let idx = -1;                 // index of the event on screen
let live = true, replayPlaying = false, replayTimer = null, stopAt = null;
let anim = { start: 0, dur: 800, ballDur: 500, from: null, entry: null };
let drawn = null;             // positions as last drawn, so jumps glide instead of teleport
let hitTargets = [];
let activeTab = "stats", statsTeam = HOME, sortKey = null, sortDir = -1;
let reportEntry = null, lastPinnedText = "";
const latencies = [];
let askId = 0;

const crests = { Brackenford: new Image(), Kestermouth: new Image() };
crests.Brackenford.src = "/static/images/brackenford.svg";
crests.Kestermouth.src = "/static/images/kestermouth.svg";
Object.values(crests).forEach(i => i.onload = buildPitchLayer);

const player = (team, pid) => (squads && squads[team] && squads[team][pid]) || { name: pid, num: "", pos: "" };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const other = t => t === HOME ? AWAY : HOME;
const fav = () => settings.fav_team === "NONE" ? null : settings.fav_team;
const rightTeam = entry => (entry && entry.event.right_team) || HOME;
/* Show the home side attacking → regardless of the half (shot map, average positions). */
const normHome = (x, y, rt) => rt === HOME ? [x, y] : [100 - x, 100 - y];

/* ---------- PITCH GEOMETRY (metres, 105 x 68, 4m margin) ---------- */
let W = 0, H = 0, S = 1, OX = 0, OY = 0, dpr = 1;
let pitchRight = HOME;        // team attacking →; each crest sits in the half its team defends
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
    [pitchRight, other(pitchRight)].forEach((t, i) => {  // left half, right half
        const img = crests[t];
        if (!img.complete || !img.naturalWidth) return;
        const sz = 13 * S;
        const cx = i === 0 ? X(52.5) - sz / 2 - 2 * S : X(52.5) + sz / 2 + 2 * S;
        c.globalAlpha = 0.12;
        c.drawImage(img, cx - sz / 2, Y(34) - sz / 2, sz, sz);
        c.globalAlpha = 0.3;
        c.fillStyle = "#FFFFFF";
        c.font = `800 ${Math.max(10, Math.round(1.6 * S))}px system-ui, sans-serif`;
        c.textAlign = "center"; c.textBaseline = "top";
        c.fillText(i === 0 ? `${TEAM_SHORT[t]} →` : `← ${TEAM_SHORT[t]}`, cx, Y(34) + sz / 2 + S);
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
const easeMove = t => -(Math.cos(Math.PI * t) - 1) / 2;
const lerp = (a, b, t) => a + (b - a) * t;

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
        if (t >= 1 && ev.outcome !== "INTERCEPTED" && ev.outcome !== "OFFSIDE") arrowHead(x0, y0, x1, y1, Math.max(6, S * 0.9));
    }
    if (t >= 1 && (ev.outcome === "INTERCEPTED" || ev.outcome === "OFFSIDE" || ev.event_type === "TACKLE")) {
        const s = Math.max(5, S * 0.7);
        ctx.strokeStyle = ev.outcome === "FOUL" || ev.outcome === "OFFSIDE" ? "#EAB308" : "#F97316"; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(x1 - s, y1 - s); ctx.lineTo(x1 + s, y1 + s);
        ctx.moveTo(x1 + s, y1 - s); ctx.lineTo(x1 - s, y1 + s); ctx.stroke();
    }
    ctx.restore();
}

function interpPositions(from, to, t) {
    const out = {};
    for (const team of TEAMS) {
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
        for (const team of TEAMS) for (const pid in (anim.from[team] || {})) {
            if (pos[team][pid]) continue;
            const [x, y] = pctPx(...anim.from[team][pid]);
            ctx.globalAlpha = Math.max(0, 1 - t);
            ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fillStyle = TEAM_COLOR[team]; ctx.fill();
            ctx.globalAlpha = 1;
        }
    }
    const screen = {};
    for (const team of TEAMS) {
        for (const pid in pos[team]) {
            const [jx, jy] = jog(pid, now);
            const [x, y] = pctPx(pos[team][pid][0] + jx, pos[team][pid][1] + jy);
            screen[`${team}|${pid}`] = [x, y];
            const isFocus = team === settings.team && pid === settings.player;
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
            if (isFocus && camFocus) {
                const pulse = (Math.sin(now / 260) + 1) / 2;
                ctx.strokeStyle = `rgba(234,179,8,${0.55 + pulse * 0.45})`; ctx.lineWidth = 2.5;
                ctx.beginPath(); ctx.arc(x, y, r + 4 + pulse * 3, 0, Math.PI * 2); ctx.stroke();
            } else if (isFocus) {
                ctx.fillStyle = "#EAB308"; ctx.font = "11px sans-serif";
                ctx.fillText("★", x + r + 3, y - r - 1);  // favourite player, visible in every mode
            }
            if ((isFocus && camFocus) || pid === ev?.player || (pid === ev?.receiver && t > 0.6)) {
                labels.push([pid.toUpperCase(), x, y - r - 9, isFocus && camFocus]);
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
    const ev = entry.event, l = ev.location, rt = rightTeam(entry);
    const r = Math.max(6, S * 1.05);
    const dir = team => (team === rt ? 1 : -1) * r * 1.15;
    const startTeam = ev.event_type === "TACKLE" ? other(ev.team) : (ev.team || entry.possession);
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

/* Speed and distance badges, drawn from the overlay cue feed. */
function drawBadges(entry, screen, now) {
    const elapsed = now - anim.start;
    for (const cue of entry.overlays || []) {
        if (cue.type !== "speed_badge" && cue.type !== "distance_badge") continue;
        const t0 = cue.start_ms / settings.speed, t1 = t0 + cue.duration_ms / settings.speed;
        if (elapsed < t0 || elapsed > t1) continue;
        const p = screen[`${cue.team}|${cue.player}`];
        if (!p) continue;
        const fade = Math.min(1, (elapsed - t0) / 200, (t1 - elapsed) / 300);
        const speedy = cue.type === "speed_badge";
        const text = speedy ? `⚡ ${cue.player} ${cue.value_kmh.toFixed(1)} km/h` : `🏃 ${cue.player} ${cue.value_km} km`;
        ctx.save();
        ctx.globalAlpha = Math.max(0, fade);
        ctx.font = "800 11px system-ui, sans-serif";
        const w = ctx.measureText(text).width + 12, bx = p[0] + 10, by = p[1] + 10;
        ctx.fillStyle = speedy ? "#EAB308" : "#F9FAFB";
        ctx.beginPath(); ctx.roundRect ? ctx.roundRect(bx, by, w, 18, 9) : ctx.rect(bx, by, w, 18); ctx.fill();
        ctx.fillStyle = "#111827"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
        ctx.fillText(text, bx + 6, by + 9.5);
        ctx.restore();
    }
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
        const cheer = fav() ? (ev.team === fav() ? "GOAL! ★" : "GOAL") : "GOAL!";
        banner(cheer, "#EAB308", `${ev.player} · ${TEAM_LABEL[ev.team]} ${ev.score.home}-${ev.score.away}`);
    } else if (ev.restart === "PENALTY" && done) {
        const card = ev.card ? ` · ${ev.card === "RED" ? "🟥" : "🟨"} ${ev.player}` : "";
        banner("PENALTY!", "#EF4444", `${TEAM_LABEL[ev.restart_team]} · ${ev.opponent} fouled by ${ev.player}${card}`);
    } else if (ev.card && done) {
        banner(ev.card === "RED" ? "RED CARD" : "YELLOW CARD", ev.card === "RED" ? "#EF4444" : "#EAB308",
            `${ev.player} (${TEAM_LABEL[ev.team]}) on ${ev.opponent}`);
    } else if (ev.event_type === "SUBSTITUTION") {
        banner("SUBSTITUTION", "#E5E7EB", `${TEAM_LABEL[ev.team]}: ${ev.player} on, ${ev.player_off} off`);
    } else if (ev.event_type === "HALF_TIME" || ev.event_type === "FULL_TIME") {
        banner(ev.event_type === "HALF_TIME" ? "HALF-TIME · TEAMS CHANGE ENDS" : "FULL-TIME", "#FFFFFF",
            `${TEAM_LABEL[HOME]} ${ev.score.home}-${ev.score.away} ${TEAM_LABEL[AWAY]}`);
    }
    let chipY = 8;
    if (ev.is_impact_moment) {
        const why = ev.impact_reasons.map(r => REASON_LABEL[r] || r).join(" · ");
        chip(`⚡ IMPACT · ${why}`, 8, chipY, "rgba(234,179,8,0.92)", "#000");
        chipY += 24;
    }
    if (ev.set_piece) {
        chip(`${ICON[ev.set_piece]} ${SP_LABEL[ev.set_piece].toUpperCase()} · ${ev.player}`, 8, chipY, "rgba(8,12,20,0.85)", TEAM_COLOR[ev.team]);
    } else if (ev.outcome === "OFFSIDE" && done) {
        chip(`🚩 OFFSIDE · ${ev.receiver}`, 8, chipY, "rgba(234,179,8,0.92)", "#000");
    } else if (ev.restart && ev.restart !== "PENALTY" && done) {
        chip(`${ICON[ev.restart]} ${SP_LABEL[ev.restart].toUpperCase()} · ${TEAM_SHORT[ev.restart_team]}`, 8, chipY, "rgba(8,12,20,0.85)", TEAM_COLOR[ev.restart_team]);
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
            drawBadges(entry, screen, now);
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

/* ---------- BROADCAST CARD, TOASTS, PINNED METRIC ---------- */
function showCommentary(entry, flash = false) {
    const c = entry.commentary;
    $("ai-commentary").innerText = c[MODE_KEY[settings.mode]];
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

const TOAST_ICON = { first_goal: "⚽", brace: "⚽⚽", hat_trick: "🎩", touches: "👟", passes_completed: "🎯", team_passes: "🔗",
    tackles_won: "🛡️", saves: "🧤", spell: "🔄", top_speed: "⚡", chaos: "🌪️", control: "🎛️", press_up: "📈" };

function showToasts(entry) {
    const stack = $("toast-stack");
    for (const a of entry.alerts || []) {
        if (a.kind !== "milestone" && a.kind !== "flow") continue;
        const el = document.createElement("div");
        el.className = `toast ${a.kind}${a.team && a.team === fav() ? " fav" : ""}`;
        if (a.team) el.style.setProperty("--tc", TEAM_COLOR[a.team]);
        el.innerHTML = `<span class="toast-icon">${TOAST_ICON[a.key] || "•"}</span><span>${esc(a.text)}</span>`;
        stack.prepend(el);
        while (stack.children.length > 3) stack.lastChild.remove();
        setTimeout(() => el.classList.add("out"), 4200 / Math.sqrt(settings.speed));
        setTimeout(() => el.remove(), 4700 / Math.sqrt(settings.speed));
    }
}

function pinnedText() {
    if (pinned === "none" || !liveStats || !anim.entry) return "";
    const s = anim.entry.summary, T = liveStats.teams;
    const pair = (label, h, a) => `📌 ${label}  ${TEAM_SHORT[HOME]} ${h} · ${a} ${TEAM_SHORT[AWAY]}`;
    switch (pinned) {
        case "xg": return pair("xG", s.xg[0].toFixed(2), s.xg[1].toFixed(2));
        case "possession": return pair("Possession", `${s.possession[0]}%`, `${s.possession[1]}%`);
        case "on_target": return pair("On target", s.on_target[0], s.on_target[1]);
        case "corners": return pair("Corners", T[HOME].corners, T[AWAY].corners);
        case "cards": return pair("Cards", `${T[HOME].yellow}🟨${T[HOME].red ? ` ${T[HOME].red}🟥` : ""}`, `${T[AWAY].yellow}🟨${T[AWAY].red ? ` ${T[AWAY].red}🟥` : ""}`);
        case "pass_pct": return pair("Pass accuracy", `${T[HOME].pass_pct}%`, `${T[AWAY].pass_pct}%`);
        case "press": return pair("Pressure applied", s.flow.press[HOME], s.flow.press[AWAY]);
        case "distance": return pair("Distance", `${T[HOME].distance_km} km`, `${T[AWAY].distance_km} km`);
        case "top_speed": {
            let best = null;
            for (const t of TEAMS) for (const p of liveStats.players[t]) if (!best || p.top_speed > best.p.top_speed) best = { t, p };
            return best && best.p.top_speed ? `📌 Top speed  ${best.p.id} (${TEAM_SHORT[best.t]}) ${best.p.top_speed.toFixed(1)} km/h` : "📌 Top speed  —";
        }
    }
    return "";
}

function updatePinned() {
    const el = $("pinned-metric");
    const text = pinnedText();
    el.hidden = !text;
    if (text && text !== lastPinnedText) {
        el.innerText = text;
        if (lastPinnedText) { el.classList.remove("pulse"); void el.offsetWidth; el.classList.add("pulse"); }
    }
    lastPinnedText = text;
}

function updateUI(entry) {
    const ev = entry.event;
    showCommentary(entry);
    $("match-clock").innerText = ev.clock;
    $("score-home").innerText = ev.score.home;
    $("score-away").innerText = ev.score.away;
    $("replay-time").innerText = ev.clock;
    const poss = entry.summary.possession;
    $("poss-home-label").innerText = `${poss[0]}%`;
    $("poss-away-label").innerText = `${poss[1]}%`;
    $("poss-home-bar").style.width = `${poss[0]}%`;
    const rt = rightTeam(entry);
    if (rt !== pitchRight) { pitchRight = rt; buildPitchLayer(); }  // teams changed ends: swap the crests
    $(`dir-${HOME}`).innerText = `${TEAM_LABEL[HOME]} attack ${rt === HOME ? "→" : "←"}`;
    $(`dir-${AWAY}`).innerText = `${TEAM_LABEL[AWAY]} attack ${rt === AWAY ? "→" : "←"}`;
    updatePinned();
    renderModePanel();
}

/* ---------- MODE PANELS ---------- */
function renderModePanel() {
    if (!anim.entry) return;
    if (settings.mode === "ANALYST") renderTeamTelemetry();
    else if (settings.mode === "CASUAL") renderGlance();
    else renderPlayerCard();
}

function lastActionOf(team) {
    for (let i = idx; i >= 0; i--) {
        const h = history[i];
        if (!h || h.key !== matchKey) break;
        const ev = h.event;
        if (ev.team === team && (ON_BALL.has(ev.event_type) || ev.event_type === "TACKLE")) return ev;
    }
    return null;
}

function metricRow(label, value, pct, cls = "blue") {
    return `<div class="metric-row"><span>${label}</span><span>${value}</span></div>
        <div class="progress-bar-bg"><div class="progress-bar-fill ${cls}" style="width:${Math.max(0, Math.min(100, pct || 0))}%"></div></div>`;
}

function renderTeamTelemetry() {
    const s = anim.entry.summary;
    const T = liveStats ? liveStats.teams : null;
    $("team-telemetry").innerHTML = TEAMS.map(team => {
        const ev = lastActionOf(team);
        const m = ev ? ev.metrics : {};
        const kind = ev ? (ev.set_piece ? SP_LABEL[ev.set_piece].toUpperCase() : ev.body_part === "HEAD" ? "HEADER" : ev.event_type) : "";
        const what = ev ? `#${player(team, ev.player).num} ${esc(ev.player)} · ${kind}${ev.outcome ? " " + ev.outcome.toLowerCase() : ""} · ${ev.clock}` : "no action yet";
        const ts = T ? T[team] : null;
        const i = team === HOME ? 0 : 1;
        return `<div class="card telemetry-card team-tele" style="--tc:${TEAM_COLOR[team]}">
            <div class="card-header-flex"><h3><span class="legend-dot" style="background:${TEAM_COLOR[team]}"></span> ${TEAM_LABEL[team]} telemetry</h3></div>
            <div class="tele-last">Last action: <strong>${what}</strong></div>
            ${metricRow("xG (shot)", m.xg != null ? m.xg.toFixed(2) : "—", (m.xg || 0) * 100)}
            ${metricRow("Pass difficulty", m.pass_difficulty != null ? `${m.pass_difficulty}/100` : "—", m.pass_difficulty)}
            ${metricRow(`Pressure on the ball${m.nearest_defender_m != null ? ` · defender ${m.nearest_defender_m}m` : ""}`, m.pressure ? `${m.pressure} · ${m.pressure_index}` : "—", m.pressure_index, "yellow")}
            <div class="telemetry-grid">
                <div><span class="tg-label">Ball speed</span><span>${m.ball_speed_kmh != null ? `${m.ball_speed_kmh} km/h` : "—"}</span></div>
                <div><span class="tg-label">Forward gain</span><span>${m.forward_gain_m != null ? `${m.forward_gain_m} m` : "—"}</span></div>
                <div><span class="tg-label">Bypassed</span><span>${m.players_bypassed ?? "—"}</span></div>
            </div>
            <div class="tele-totals">
                <span title="Total expected goals">xG <strong>${s.xg[i].toFixed(2)}</strong></span>
                <span title="Average difficulty of attempted passes">Avg pass diff. <strong>${ts ? ts.avg_pass_difficulty : "—"}</strong></span>
                <span title="Average pressure index this team puts on the opponent's player on the ball">Pressure applied <strong>${s.flow.press[team]}</strong></span>
                <span title="Fastest pass or shot">Top ball speed <strong>${ts && ts.top_ball_speed ? ts.top_ball_speed + " km/h" : "—"}</strong></span>
                <span title="Estimated total distance covered">Distance <strong>${ts ? ts.distance_km + " km" : "—"}</strong></span>
            </div>
        </div>`;
    }).join("");
}

function moodText(flow) {
    const tempo = flow.tempo === "HIGH" ? " Fast and frantic right now." : flow.tempo === "SLOW" ? " The pace has dropped." : "";
    if (flow.state === "CONTROL") return `😎 ${TEAM_LABEL[flow.state_team]} are calmly keeping the ball.${tempo}`;
    if (flow.state === "CHAOS") return `🔥 End to end! The ball keeps changing hands.${tempo}`;
    return `⚖️ An even contest at the moment.${tempo}`;
}

function renderGlance() {
    const e = anim.entry, s = e.summary;
    const T = liveStats ? liveStats.teams : null;
    $("glance-mood").innerText = moodText(s.flow);
    const rows = [
        ["Possession", s.possession[0], s.possession[1], v => `${v}%`],
        ["Shots", s.shots[0], s.shots[1]],
        ["Shots on target", s.on_target[0], s.on_target[1]],
        ["Big chances", T ? T[HOME].big_chances : 0, T ? T[AWAY].big_chances : 0],
        ["Saves", T ? T[HOME].saves : 0, T ? T[AWAY].saves : 0],
        ["Corners", T ? T[HOME].corners : 0, T ? T[AWAY].corners : 0],
        ["Fouls", T ? T[HOME].fouls : 0, T ? T[AWAY].fouls : 0],
        ["Cards", T ? T[HOME].yellow + T[HOME].red : 0, T ? T[AWAY].yellow + T[AWAY].red : 0],
    ];
    $("glance-bars").innerHTML = rows.map(([label, h, a, fmt = v => v]) => {
        const max = Math.max(h, a, 1);
        return `<div class="glance-row">
            <span class="g-val">${fmt(h)}</span>
            <div class="g-bar left"><div style="width:${100 * h / max}%; background:${TEAM_COLOR[HOME]}"></div></div>
            <span class="g-label">${label}</span>
            <div class="g-bar"><div style="width:${100 * a / max}%; background:${TEAM_COLOR[AWAY]}"></div></div>
            <span class="g-val">${fmt(a)}</span></div>`;
    }).join("");
    $("momentum-needle").style.left = `${50 - s.momentum / 2}%`;
    const goals = history.filter(h => h.key === matchKey && h.event.outcome === "GOAL" && history.indexOf(h) <= idx);
    $("glance-goals").innerHTML = goals.map(h => `<li style="--tc:${TEAM_COLOR[h.event.team]}">⚽ ${h.event.clock} ${esc(h.event.player)} <span class="text-muted">${TEAM_LABEL[h.event.team]}</span></li>`).join("")
        || `<li class="text-muted">No goals yet</li>`;
}

const PC_STATS = {
    outfield: [["touches", "Touches"], ["passes_completed", "Passes completed"], ["shots", "Shots"],
               ["tackles_won", "Tackles won"], ["sprints", "Sprints"], ["distance_km", "Distance (km)"], ["top_speed", "Top speed (km/h)"]],
    keeper: [["saves", "Saves"], ["touches", "Touches"], ["passes_completed", "Passes completed"], ["distance_km", "Distance (km)"]],
};

function renderPlayerCard() {
    if (!liveStats) return;
    const team = settings.team, rows = liveStats.players[team];
    const p = rows.find(r => r.id === settings.player);
    if (!p) return;
    $("pc-num").innerText = p.num;
    $("pc-num").style.background = TEAM_COLOR[team];
    $("pc-num").style.color = TEAM_INK[team];
    $("pc-name").innerText = p.name;
    const status = p.sub_off != null ? ` · off ${p.sub_off}'` : p.minutes === 0 ? " · not played yet" : ` · ${p.minutes}'`;
    $("pc-sub").innerText = `${p.pos} · ${TEAM_LABEL[team]}${status}`;
    $("pc-rating").innerText = p.rating != null ? p.rating.toFixed(1) : "–";
    const keeper = p.pos === "GK";
    const peers = rows.filter(r => r.minutes > 0 && (r.pos === "GK") === keeper);
    $("pc-bars").innerHTML = PC_STATS[keeper ? "keeper" : "outfield"].map(([k, label]) => {
        const vals = peers.map(r => r[k] || 0);
        const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
        const max = Math.max(...vals, p[k] || 0, 1);
        const v = p[k] || 0;
        const fmt = x => (k === "distance_km" || k === "top_speed") ? x.toFixed(1) : Math.round(x * 10) / 10;
        return `<div class="pc-row"><div class="pc-row-label"><span>${label}</span><span><strong>${fmt(v)}</strong> <span class="text-muted">team avg ${fmt(avg)}</span></span></div>
            <div class="pc-bar"><div class="pc-fill" style="width:${100 * v / max}%; background:${TEAM_COLOR[team]}"></div><div class="pc-avg" style="left:${100 * avg / max}%"></div></div></div>`;
    }).join("");
    renderHeatMap(team, settings.player);
}

function renderHeatMap(team, pid) {
    const c = $("pc-heat"), g = c.getContext("2d");
    const w = c.width, h = c.height, sx = w / 100, sy = h / 100;
    g.fillStyle = "#164227"; g.fillRect(0, 0, w, h);
    g.strokeStyle = "rgba(255,255,255,0.45)"; g.lineWidth = 1.5;
    g.strokeRect(1, 1, w - 2, h - 2);
    g.beginPath(); g.moveTo(w / 2, 0); g.lineTo(w / 2, h); g.stroke();
    g.beginPath(); g.arc(w / 2, h / 2, h * 0.135, 0, Math.PI * 2); g.stroke();
    g.strokeRect(1, h * 0.204, w * 0.157, h * 0.593); g.strokeRect(w * 0.843, h * 0.204, w * 0.157 - 1, h * 0.593);
    const pts = [];
    for (let i = 0; i <= idx; i++) {
        const e = history[i];
        if (!e || e.key !== matchKey) continue;
        const p = e.positions[team] && e.positions[team][pid];
        if (!p) continue;
        // always show the player's team attacking to the right
        pts.push(e.event.right_team === team ? p : [100 - p[0], 100 - p[1]]);
    }
    g.globalCompositeOperation = "lighter";
    const rad = w * 0.09;
    for (const [x, y] of pts) {
        const grd = g.createRadialGradient(x * sx, y * sy, 0, x * sx, y * sy, rad);
        grd.addColorStop(0, "rgba(234,179,8,0.16)");
        grd.addColorStop(1, "rgba(234,179,8,0)");
        g.fillStyle = grd;
        g.beginPath(); g.arc(x * sx, y * sy, rad, 0, Math.PI * 2); g.fill();
    }
    g.globalCompositeOperation = "source-over";
    if (!pts.length) {
        g.fillStyle = "rgba(255,255,255,0.7)"; g.font = "600 16px system-ui"; g.textAlign = "center";
        g.fillText("No positions yet", w / 2, h / 2);
    }
    $("pc-heat-note").innerText = `${pts.length} snapshots · ${TEAM_LABEL[team]} attacking →`;
}

/* ---------- REPORT CARD ---------- */
function openReport(entry) {
    const r = entry.report;
    if (!r) return;
    reportEntry = entry;
    $("report-title").innerText = r.kind === "HALF_TIME" ? "HALF-TIME REPORT" : "FULL-TIME REPORT";
    $("report-score").innerHTML = `<span style="color:${TEAM_COLOR[HOME]}">${TEAM_LABEL[HOME].toUpperCase()}</span> <strong>${r.score.home} – ${r.score.away}</strong> <span style="color:${TEAM_COLOR[AWAY]}">${TEAM_LABEL[AWAY].toUpperCase()}</span>`;
    const th = r.teams[HOME], ta = r.teams[AWAY];
    const rows = [["xG", th.xg.toFixed(2), ta.xg.toFixed(2), th.xg, ta.xg], ["Shots", th.shots, ta.shots], ["On target", th.on_target, ta.on_target],
        ["Possession", `${th.possession}%`, `${ta.possession}%`, th.possession, ta.possession], ["Pass accuracy", `${th.pass_pct}%`, `${ta.pass_pct}%`, th.pass_pct, ta.pass_pct],
        ["Big chances", th.big_chances, ta.big_chances], ["Ball wins in opp. half", th.press_wins, ta.press_wins],
        ["Corners", th.corners, ta.corners], ["Fouls", th.fouls, ta.fouls], ["Offsides", th.offsides, ta.offsides],
        ["Cards", `${th.yellow}🟨 ${th.red}🟥`, `${ta.yellow}🟨 ${ta.red}🟥`, th.yellow + 2 * th.red, ta.yellow + 2 * ta.red],
        ["Distance (km)", th.distance_km, ta.distance_km]];
    $("report-stats").innerHTML = rows.map(([label, h, a, hn = +h, an = +a]) => {
        const tot = hn + an, hp = tot ? 100 * hn / tot : 50;
        return `<div class="rs-row"><span>${h}</span><div><span class="rs-label">${label}</span>
            <div class="h2h-bar"><div class="h2h-home" style="width:${hp}%"></div><div class="h2h-away" style="width:${100 - hp}%"></div></div></div><span>${a}</span></div>`;
    }).join("");
    $("report-narrative").innerText = r.narrative;
    const b = r.best_player;
    $("report-best").innerHTML = b ? `<span class="rb-label">Best player</span> <strong>${esc(b.name)}</strong> <span style="color:${TEAM_COLOR[b.team]}">${TEAM_LABEL[b.team]}</span> <span class="rating r-high">${b.rating.toFixed(1)}</span>` : "";
    const icon = m => m.outcome === "GOAL" ? "⚽" : m.restart === "PENALTY" ? ICON.PENALTY : m.card === "RED" ? "🟥" : m.card ? "🟨" : m.outcome === "SAVED" ? "🧤" : "🎯";
    $("report-moments").innerHTML = r.key_moments.map(m => `<li>${icon(m)} ${m.clock} ${esc(m.player)} <span class="text-muted">${TEAM_LABEL[m.team]}</span></li>`).join("");
    $("report-source").innerText = `${entry.reportSource || "LOCAL ENGINE"} · ${r.kind === "HALF_TIME" ? "Second half kicks off shortly" : "New match starts shortly"}`;
    $("report-modal").hidden = false;
}
function closeReport() { $("report-modal").hidden = true; reportEntry = null; }
$("report-close").addEventListener("click", closeReport);

/* ---------- TIMELINE / REPLAY ---------- */
function show(i) {
    if (!history[i]) return;
    const prevEntry = anim.entry;
    idx = i;
    const entry = history[i];
    const sameMatch = prevEntry && prevEntry.key === entry.key;
    const dur = animDuration();
    anim = { start: performance.now(), dur, ballDur: ballDuration(entry.event, dur), from: sameMatch ? drawn : null, entry };
    $("timeline-slider").value = i;
    updateUI(entry);
    if (entry !== prevEntry) showToasts(entry);
    if (entry.report && live) openReport(entry);
    else if (reportEntry && !entry.report && entry.event.team) closeReport();
    document.querySelectorAll(".event-item.active-replay").forEach(el => el.classList.remove("active-replay"));
    if (!live) {
        const el = document.querySelector(`.event-item[data-seq="${entry.event.seq}"]`);
        if (el) { el.classList.add("active-replay"); scrollWithin($("event-log-container"), el); }
    }
    updateLiveButton();
}

/* Bring an item into view inside its list only: scrollIntoView would also scroll the page. */
function scrollWithin(list, el) {
    const l = list.getBoundingClientRect(), r = el.getBoundingClientRect();
    if (r.top < l.top) list.scrollTop -= l.top - r.top;
    else if (r.bottom > l.bottom) list.scrollTop += r.bottom - l.bottom;
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
    live = false;
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
    closeReport();
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
    if (e.target.closest && e.target.closest("input, select, textarea")) return;
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); $("step-back-btn").click(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); $("step-fwd-btn").click(); }
    else if (e.key.toLowerCase() === "l") goLive();
    else if (e.key === "Escape") closeReport();
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

/* ---------- EVENT LOG ---------- */
const ICON = { GOAL: "⚽", SAVED: "🧤", MISS: "🎯", BLOCKED: "🧱", COMPLETE: "➡️", INTERCEPTED: "✂️", SUCCESS: "💨",
               WON: "🛡️", FOUL: "✋", OUT: "↗️", OFFSIDE: "🚩", SUBSTITUTION: "🔁", HALF_TIME: "⏸", FULL_TIME: "🏁",
               CORNER: "⛳", FREE_KICK: "🦶", THROW_IN: "🙌", GOAL_KICK: "🥅", PENALTY: "❗" };

/* What kind of shot: penalty, free kick, header or an ordinary shot. */
const shotKind = ev => ev.set_piece === "PENALTY" ? "PENALTY" : ev.set_piece === "FREE_KICK" ? "FREE KICK" : ev.body_part === "HEAD" ? "HEADER" : "SHOT";

function logLabel(ev) {
    const sp = ev.set_piece ? SP_LABEL[ev.set_piece].toUpperCase() + " " : "";
    switch (ev.event_type) {
        case "PASS":
            if (ev.outcome === "COMPLETE") return `${sp || "PASS "}→ ${ev.receiver}`;
            if (ev.outcome === "OUT") return `${sp || "PASS "}OUT OF PLAY`;
            if (ev.outcome === "OFFSIDE") return `OFFSIDE: ${ev.receiver}`;
            return `${sp || "PASS "}${ev.restart === "CORNER" ? "TURNED BEHIND by" : sp ? "CLEARED by" : "INTERCEPTED by"} ${ev.opponent}`;
        case "DRIBBLE": return "DRIBBLE";
        case "SHOT": return `${shotKind(ev)} · ${ev.outcome}`;
        case "TACKLE": return ev.outcome === "WON" ? `TACKLE WON on ${ev.opponent}`
            : `${ev.restart === "PENALTY" ? "PENALTY! FOUL" : "FOUL"} on ${ev.opponent}${ev.card ? (ev.card === "RED" ? " 🟥" : " 🟨") : ""}`;
        case "SUBSTITUTION": return `SUB ${ev.player} ⇄ ${ev.player_off}`;
        default: return ev.event_type.replace("_", " ");
    }
}

function addLogItem(entry) {
    const ev = entry.event;
    const item = document.createElement("div");
    const mine = fav() && ev.team === fav();
    item.className = `event-item clickable new${ev.is_impact_moment ? " impact" : ""}${mine ? " fav" : ""}`;
    item.dataset.seq = ev.seq;
    item.setAttribute("role", "button");
    item.tabIndex = 0;
    const who = ev.team && ev.event_type !== "SUBSTITUTION"
        ? `<span class="team-tag" style="--tc:${TEAM_COLOR[ev.team]}">${esc(ev.player)}</span> ` : "";
    const icon = ev.outcome === "GOAL" ? ICON.GOAL : ev.restart === "PENALTY" ? ICON.PENALTY
        : ev.set_piece && ev.event_type === "PASS" ? ICON[ev.set_piece] : ICON[ev.outcome || ev.event_type];
    const restart = ev.restart ? ` <span class="restart-tag" title="Play restarts with this set piece">→ ${SP_LABEL[ev.restart].toLowerCase()} ${TEAM_SHORT[ev.restart_team]}</span>` : "";
    item.innerHTML = `<span class="event-time">${esc(ev.clock)}</span><span>${mine ? "★ " : ""}${icon || "•"} ${who}<strong>${esc(logLabel(ev))}</strong>${restart}${ev.possession_change ? ' <span class="poss-chg" title="Possession changed">⇄</span>' : ""}${ev.is_impact_moment ? ' <span class="zap">⚡</span>' : ""}</span>`;
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

/* ---------- KEY EVENTS & STORIES ---------- */
function isKeyEvent(ev) {
    return ev.outcome === "GOAL" || ev.card || ev.restart === "PENALTY" || ev.event_type === "SUBSTITUTION" || ev.event_type === "HALF_TIME"
        || ev.event_type === "FULL_TIME" || (ev.event_type === "SHOT" && (ev.metrics.xg >= 0.3 || ev.outcome === "SAVED"
            || ev.set_piece === "PENALTY" || ev.set_piece === "FREE_KICK"));
}

function keyEventText(ev) {
    const how = ev.event_type === "SHOT" && shotKind(ev) !== "SHOT" ? `, ${shotKind(ev).toLowerCase()}` : "";
    const xg = ev.metrics.xg != null ? ` (${ev.metrics.xg.toFixed(2)} xG${how})` : "";
    if (ev.outcome === "GOAL") return `⚽ <strong>GOAL</strong> ${esc(ev.player)}, ${TEAM_LABEL[ev.team]}${xg} · ${ev.score.home}-${ev.score.away}`;
    if (ev.restart === "PENALTY") return `${ICON.PENALTY} <strong>PENALTY</strong> to ${TEAM_LABEL[ev.restart_team]}: ${esc(ev.opponent)} fouled by ${esc(ev.player)}${ev.card ? (ev.card === "RED" ? " 🟥" : " 🟨") : ""}`;
    if (ev.card) return `${ev.card === "RED" ? "🟥 <strong>RED CARD</strong>" : "🟨 <strong>YELLOW CARD</strong>"} ${esc(ev.player)} (${TEAM_LABEL[ev.team]}) for a foul on ${esc(ev.opponent)}`;
    if (ev.event_type === "SUBSTITUTION") return `🔁 <strong>SUB</strong> ${TEAM_LABEL[ev.team]}: ${esc(ev.player)} on, ${esc(ev.player_off)} off`;
    if (ev.event_type === "HALF_TIME") return `⏸ <strong>HALF-TIME REPORT</strong> ${TEAM_LABEL[HOME]} ${ev.score.home}-${ev.score.away} ${TEAM_LABEL[AWAY]}`;
    if (ev.event_type === "FULL_TIME") return `🏁 <strong>FULL-TIME REPORT</strong> ${TEAM_LABEL[HOME]} ${ev.score.home}-${ev.score.away} ${TEAM_LABEL[AWAY]}`;
    if (ev.outcome === "SAVED") return `🧤 <strong>${ev.set_piece === "PENALTY" ? "PENALTY SAVED" : "SAVE"}</strong> ${esc(ev.opponent)} denies ${esc(ev.player)}${xg}`;
    const label = ev.set_piece === "PENALTY" ? "PENALTY MISSED" : ev.set_piece === "FREE_KICK" ? "FREE KICK" : "BIG CHANCE";
    return `🎯 <strong>${label}</strong> ${esc(ev.player)}, ${TEAM_LABEL[ev.team]}${xg}: ${ev.outcome.toLowerCase()}`;
}

function keyEventStory(entry) {
    if (entry.report) return entry.report.narrative;
    return entry.story || "";
}

function addKeyEvent(entry) {
    const ev = entry.event;
    if (!isKeyEvent(ev)) return;
    const li = document.createElement("li");
    li.dataset.seq = ev.seq;
    li.tabIndex = 0;
    const mine = fav() && ev.team === fav();
    li.className = `ke ${ev.team ? (ev.team === HOME ? "home" : "away") : "neutral"}${mine ? " fav" : ""}`;
    li.innerHTML = `<div class="ke-top"><span class="time-tag">${esc(ev.clock)}</span> ${keyEventText(ev)}
        ${entry.report ? '<button class="chip open-report">Open report</button>' : ""}
        <span class="replay-hint"><i class="fa-solid fa-rotate-left"></i> replay</span></div>
        <p class="story"></p>`;
    $("key-events-list").prepend(li);
    updateKeyEventStory(entry);
}

function updateKeyEventStory(entry) {
    const li = document.querySelector(`#key-events-list li[data-seq="${entry.event.seq}"]`);
    if (!li) return;
    const p = li.querySelector(".story");
    const text = keyEventStory(entry);
    const src = entry.report ? entry.reportSource : entry.storySource;
    p.innerHTML = text ? `${esc(text)} <span class="ai-source ${src === "AZURE OPENAI" ? "from-azure" : ""}">${src || "LOCAL ENGINE"}</span>` : "";
}

function onKeyEventActivate(e) {
    const li = e.target.closest("li[data-seq]");
    if (!li || (e.type === "keydown" && e.key !== "Enter")) return;
    const entry = history.find(h => h.key === matchKey && h.event.seq === +li.dataset.seq);
    if (e.target.closest(".open-report") || (entry && entry.report)) { if (entry) openReport(entry); return; }
    replayBuildUp(+li.dataset.seq);
}
$("key-events-list").addEventListener("click", onKeyEventActivate);
$("key-events-list").addEventListener("keydown", onKeyEventActivate);
$("ke-fav-only").addEventListener("change", e => $("key-events-list").classList.toggle("fav-only", e.target.checked));

/* ---------- MATCH STATS TAB ---------- */
const H2H = [
    ["Possession", s => s.possession, v => `${v}%`],
    ["Shots", s => s.shots], ["Shots on target", s => s.on_target],
    ["Expected goals (xG)", s => s.xg, v => v.toFixed(2)], ["Big chances", s => s.big_chances],
    ["Passes", s => s.passes], ["Pass accuracy", s => s.pass_pct, v => `${v}%`],
    ["Avg pass difficulty", s => s.avg_pass_difficulty],
    ["Tackles won", s => s.tackles_won], ["Interceptions", s => s.interceptions],
    ["Ball wins in opp. half", s => s.press_wins],
    ["Distance covered (km)", s => s.distance_km, v => v.toFixed(1)],
    ["Top sprint (km/h)", s => s.top_speed, v => v.toFixed(1)],
    ["Saves", s => s.saves], ["Corners", s => s.corners], ["Free kicks", s => s.free_kicks],
    ["Throw-ins", s => s.throw_ins], ["Goal kicks", s => s.goal_kicks], ["Penalties", s => s.penalties],
    ["Offsides", s => s.offsides], ["Fouls", s => s.fouls], ["Yellow cards", s => s.yellow], ["Red cards", s => s.red],
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
    ["interceptions", "Int."], ["saves", "Saves"], ["fouls", "Fouls"], ["fouls_won", "Fouled"], ["offsides", "Off."], ["cards", "Cards"],
    ["touches", "Touches"], ["sprints", "Sprints"], ["distance_km", "Dist. km"], ["top_speed", "Top km/h"],
];
const COL_TITLE = {
    minutes: "Minutes played", rating: "Match rating (starts at 6.0)", goals: "Goals", assists: "Assists",
    shots: "Shots (on target)", passes: "Completed / attempted passes", key_passes: "Passes that led to a shot",
    dribbles_won: "Successful / attempted dribbles", tackles_won: "Tackles won / attempted",
    interceptions: "Interceptions", touches: "Touches of the ball", fouls: "Fouls committed",
    fouls_won: "Times fouled (free kicks or penalties won)", offsides: "Caught offside", sprints: "Sprints and runs in behind",
    distance_km: "Estimated distance covered", top_speed: "Fastest sprint recorded",
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
            <td>${r.minutes}</td><td><span class="rating ${ratingCls(r.rating)}">${r.rating != null ? r.rating.toFixed(1) : "–"}</span></td>
            <td>${r.goals || "–"}</td><td>${r.assists || "–"}</td><td>${r.shots} (${r.on_target})</td><td>${r.xg.toFixed(2)}</td>
            <td>${r.passes_completed}/${r.passes}</td><td>${r.key_passes}</td><td>${r.dribbles_won}/${r.dribbles}</td>
            <td>${r.tackles_won}/${r.tackles}</td><td>${r.interceptions}</td><td>${r.saves}</td><td>${r.fouls}</td>
            <td>${r.fouls_won}</td><td>${r.offsides}</td>
            <td>${cards}</td><td>${r.touches}</td><td>${r.sprints}</td><td>${r.distance_km.toFixed(1)}</td>
            <td>${r.top_speed ? r.top_speed.toFixed(1) : "–"}</td></tr>`;
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
function setStatsTeam(team) {
    statsTeam = team;
    document.querySelectorAll(".seg-btn").forEach(x => x.classList.toggle("active", x.dataset.team === team));
    renderPlayerTable();
}
document.querySelectorAll(".seg-btn").forEach(b => b.addEventListener("click", () => setStatsTeam(b.dataset.team)));

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
    const ch = tac.channels, favCh = Object.keys(ch).reduce((a, b) => ch[a] >= ch[b] ? a : b);
    if (tac.final_third_actions >= 4) parts.push(favCh === "central" ? `Attacks go mostly through the centre (${ch.central}%).` : `Attacks lean down the ${favCh} (${ch[favCh]}% of final-third actions).`);
    parts.push(tac.directness >= 40 ? `Direct: ${tac.directness}% of recent passes go 15m+ forward.` : `Patient build-up: only ${tac.directness}% of recent passes go 15m+ forward.`);
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
    $("tactics-cards").innerHTML = TEAMS.map(team => {
        const tac = T[team], opp = T[other(team)], ch = tac.channels;
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
    for (const team of TEAMS) {
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
        `<text x="${sx(last[0]) + 8}" y="${labelY[0] + 4}" class="direct-label">${TEAM_SHORT[HOME]} ${last[1].toFixed(2)}</text>` +
        `<text x="${sx(last[0]) + 8}" y="${labelY[1] + 4}" class="direct-label">${TEAM_SHORT[AWAY]} ${last[2].toFixed(2)}</text>` +
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
    tooltip(e, `<strong>${Math.floor(minute)}'</strong><br><span class="sw" style="background:${TEAM_COLOR[HOME]}"></span>${TEAM_LABEL[HOME]} ${p[1].toFixed(2)} xG<br><span class="sw" style="background:${TEAM_COLOR[AWAY]}"></span>${TEAM_LABEL[AWAY]} ${p[2].toFixed(2)} xG`);
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
        <text x="${m.l - 6}" y="${m.t + 9}" class="axis" text-anchor="end">${TEAM_SHORT[HOME]}</text><text x="${m.l - 6}" y="${h - m.b}" class="axis" text-anchor="end">${TEAM_SHORT[AWAY]}</text>`;
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

const FLOW_COLOR = { CHAOS: "#F59E0B", BALANCED: "#4B5563" };
function renderFlow() {
    const svg = $("flow-chart");
    const w = svg.getBoundingClientRect().width || 600, h = 170, m = { l: 34, r: 74, t: 8, b: 22 };
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    const entries = matchEntries().filter(e => e.event.team);
    const sx = v => m.l + (w - m.l - m.r) * v / 90;
    const bandH = 14, top = m.t + bandH + 8, sy = v => h - m.b - (h - m.b - top) * v / 100;
    let out = "";
    for (const v of [0, 50, 100]) out += `<line x1="${m.l}" x2="${w - m.r}" y1="${sy(v)}" y2="${sy(v)}" class="grid"/><text x="${m.l - 6}" y="${sy(v) + 3}" class="axis" text-anchor="end">${v}</text>`;
    for (const v of [0, 15, 30, 45, 60, 75, 90]) out += `<text x="${sx(v)}" y="${h - 6}" class="axis" text-anchor="middle">${v}'</text>`;
    // state band in 2-minute buckets: majority state wins
    const buckets = new Map();
    for (const e of entries) {
        const b = Math.min(44, Math.floor(e.event.minute / 2));
        const f = e.summary.flow, key = f.state === "CONTROL" ? `CONTROL|${f.state_team}` : f.state;
        const counts = buckets.get(b) || {}; counts[key] = (counts[key] || 0) + 1; buckets.set(b, counts);
    }
    const bw = (w - m.l - m.r) / 45;
    for (const [b, counts] of buckets) {
        const key = Object.keys(counts).reduce((a, c) => counts[a] >= counts[c] ? a : c);
        const [state, team] = key.split("|");
        const color = state === "CONTROL" ? TEAM_COLOR[team] : FLOW_COLOR[state];
        const label = state === "CONTROL" ? `${TEAM_LABEL[team]} in control` : state === "CHAOS" ? "Chaotic: frequent turnovers" : "Balanced";
        out += `<rect x="${(m.l + b * bw + 1).toFixed(1)}" y="${m.t}" width="${Math.max(1, bw - 2).toFixed(1)}" height="${bandH}" rx="2" fill="${color}" opacity="${state === "BALANCED" ? 0.7 : 0.9}" data-tip="${b * 2}'-${b * 2 + 2}': ${label}"/>`;
    }
    const line = team => entries.map((e, i) => `${i ? "L" : "M"}${sx(e.event.minute).toFixed(1)},${sy(e.summary.flow.press[team]).toFixed(1)}`).join(" ");
    if (entries.length > 1) {
        out += `<path d="${line(HOME)}" class="xg-line" stroke="${TEAM_COLOR[HOME]}"/><path d="${line(AWAY)}" class="xg-line" stroke="${TEAM_COLOR[AWAY]}"/>`;
        const lf = entries[entries.length - 1].summary.flow.press;
        const ly = [sy(lf[HOME]), sy(lf[AWAY])];
        if (Math.abs(ly[0] - ly[1]) < 13) { const mid = (ly[0] + ly[1]) / 2; ly[0] = mid + (lf[HOME] >= lf[AWAY] ? -7 : 7); ly[1] = mid + (lf[HOME] >= lf[AWAY] ? 7 : -7); }
        const lx = sx(entries[entries.length - 1].event.minute) + 8;
        out += `<text x="${lx}" y="${ly[0] + 4}" class="direct-label">${TEAM_SHORT[HOME]} ${lf[HOME]}</text><text x="${lx}" y="${ly[1] + 4}" class="direct-label">${TEAM_SHORT[AWAY]} ${lf[AWAY]}</text>`;
    }
    svg.innerHTML = out;
    const cur = anim.entry ? anim.entry.summary.flow : null;
    $("flow-now").innerHTML = cur ? `<strong>Now:</strong> ${esc(moodText(cur))} Turnovers in recent play: ${cur.turnover_rate}%. Tempo: ${cur.tempo.toLowerCase()}.
        <span class="flow-legend"><span style="background:${TEAM_COLOR[HOME]}"></span>${TEAM_LABEL[HOME]} control <span style="background:${TEAM_COLOR[AWAY]}"></span>${TEAM_LABEL[AWAY]} control <span style="background:${FLOW_COLOR.BALANCED}"></span>Balanced <span style="background:${FLOW_COLOR.CHAOS}"></span>Chaos</span>` : "";
}

function renderShotMap() {
    let dots = "";
    for (const e of matchEntries()) {
        const ev = e.event;
        if (ev.event_type !== "SHOT") continue;
        const [nx, ny] = normHome(ev.location.start_x, ev.location.start_y, ev.right_team);
        const x = nx * 1.05, y = ny * 0.68, r = 0.9 + ev.metrics.xg * 4.5;
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

function renderReports() {
    const reps = matchEntries().filter(e => e.report);
    $("reports-list").innerHTML = reps.map(e => `<div class="report-item" data-seq="${e.event.seq}">
        <div class="ke-top"><strong>${e.report.kind === "HALF_TIME" ? "Half-time" : "Full-time"}</strong> · ${TEAM_LABEL[HOME]} ${e.report.score.home}-${e.report.score.away} ${TEAM_LABEL[AWAY]}
        <button class="chip open-report">Open</button></div><p>${esc(e.report.narrative)}</p></div>`).join("")
        || `<p class="text-muted">No reports yet: the half-time report appears at 45'.</p>`;
}
$("reports-list").addEventListener("click", e => {
    const it = e.target.closest(".report-item");
    if (!it) return;
    const entry = history.find(h => h.key === matchKey && h.event.seq === +it.dataset.seq);
    if (entry) openReport(entry);
});

function renderAnalysis() { renderXgChart(); renderMomentum(); renderFlow(); renderShotMap(); renderImpactList(); renderReports(); }

/* ---------- DATA & OVERLAYS TAB ---------- */
function renderData() {
    const entries = matchEntries();
    const cues = entries.flatMap(e => e.overlays || []);
    $("cue-count").innerText = `${cues.length} cues`;
    const latest = cues.slice(-8).reverse();
    $("cue-feed").textContent = latest.length ? latest.map(c => JSON.stringify(c, null, 1)).join("\n") : "Start the match to see cues.";
    if (metadata) {
        const m = metadata, pair = o => `${o[HOME]} · ${o[AWAY]}`, h2h = m.head_to_head;
        const rows = [["Competition", `${m.competition} ${m.season || ""} · matchday ${m.matchday}`],
            ["Clubs", `${m.club_names[HOME]} (${m.nicknames[HOME]}) · ${m.club_names[AWAY]} (${m.nicknames[AWAY]})`],
            ["League position before", pair(m.league_positions)],
            ["Venue", `${m.venue} · capacity ${m.capacity.toLocaleString()}`],
            ["Attendance", m.attendance.toLocaleString()], ["Referee", m.referee],
            ["Weather", `${m.weather}, ${m.temperature_c}°C, wind ${m.wind}`], ["Pitch", m.pitch],
            ["Managers", pair(m.coaches)], ["Formations", pair(m.formations)],
            ["Head-to-head", `${h2h.meetings} meetings: ${h2h.home_wins} ${TEAM_SHORT[HOME]} wins, ${h2h.away_wins} ${TEAM_SHORT[AWAY]} wins, ${h2h.draws} draws · last ${h2h.last_result}`],
            ...m.storylines.map((s, i) => [i ? "" : "Storylines", s]),
            ["Kick-off (UTC)", m.kickoff_utc], ["Data", "100% synthetic, fictional clubs and people"]];
        $("meta-table").innerHTML = rows.map(([k, v]) => `<div><span>${k}</span><span>${esc(v)}</span></div>`).join("");
    }
}

function download(name, text, type) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const fileStem = () => `secondtouch_match_${(metadata && metadata.kickoff_utc || "live").replace(/[:]/g, "-")}`;
const EVENT_COLS = ["seq", "minute", "clock", "team", "player", "event_type", "outcome", "receiver", "opponent", "player_off", "card",
    "set_piece", "restart", "restart_team", "body_part",
    "length_m", "start_x", "start_y", "end_x", "end_y", "xg", "pass_difficulty", "pressure", "pressure_index", "nearest_defender_m",
    "sprint_speed_kmh", "ball_speed_kmh", "forward_gain_m", "players_bypassed", "possession_change", "right_team",
    "is_impact_moment", "impact_reasons", "score_home", "score_away"];
const csvCell = v => v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v);

$("dl-jsonl").addEventListener("click", () => download(`${fileStem()}_events.jsonl`,
    matchEntries().map(e => JSON.stringify({ ...e.event, positions: e.positions, commentary: e.commentary, story: e.story || null })).join("\n"), "application/x-ndjson"));
$("dl-cues").addEventListener("click", () => download(`${fileStem()}_overlay_cues.jsonl`,
    matchEntries().flatMap(e => e.overlays || []).map(c => JSON.stringify(c)).join("\n"), "application/x-ndjson"));
$("dl-csv").addEventListener("click", () => {
    const rows = matchEntries().map(({ event: ev }) => {
        const flat = { ...ev, ...ev.metrics, ...ev.location, impact_reasons: ev.impact_reasons.join("|"), score_home: ev.score.home, score_away: ev.score.away };
        return EVENT_COLS.map(k => csvCell(flat[k])).join(",");
    });
    download(`${fileStem()}_events.csv`, [EVENT_COLS.join(","), ...rows].join("\n"), "text/csv");
});
$("dl-players").addEventListener("click", () => {
    if (!liveStats) return;
    const rows = TEAMS.flatMap(t => liveStats.players[t].map(r => ({ team: t, ...r })));
    if (!rows.length) return;
    const cols = Object.keys(rows[0]);
    download(`${fileStem()}_players.csv`, [cols.join(","), ...rows.map(r => cols.map(k => csvCell(r[k])).join(","))].join("\n"), "text/csv");
});

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
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el && el.closest("svg")) tooltip(e, esc(el.dataset.tip));
});
document.addEventListener("mousemove", e => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    if (el && el.closest("svg")) tooltip(e, esc(el.dataset.tip));
});
document.addEventListener("mouseout", e => { if (e.target.closest && e.target.closest("[data-tip]")) hideTooltip(); });

/* ---------- TABS ---------- */
function renderActiveTab() {
    if (activeTab === "stats") renderStats();
    else if (activeTab === "tactics") renderTactics();
    else if (activeTab === "analysis") renderAnalysis();
    else if (activeTab === "data") renderData();
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
    $("toast-stack").innerHTML = "";
    closeReport();
    history = history.filter(h => h.key === key);
    idx = -1;
    anim = { start: 0, dur: 800, ballDur: 500, from: null, entry: null };
    drawn = null;
    live = true; replayPlaying = false; stopAt = null;
    clearTimeout(replayTimer);
}

const WEATHER_ICON = { "Clear": "sun", "Light rain": "cloud-rain", "Light drizzle": "cloud-rain", "Overcast": "cloud", "Cold and dry": "temperature-low", "Mild evening": "cloud-moon" };

function onMatchStart(msg) {
    metadata = msg.metadata;
    const m = metadata;
    const item = (icon, html, title, cls = "") => `<span class="mi-item ${cls}" title="${title}"><i class="fa-solid fa-${icon}"></i>${html}</span>`;
    $("match-info").innerHTML = [
        item("trophy", `${esc(m.competition)} <span class="mi-dim">· Matchday ${m.matchday}</span>`, "Competition", "mi-comp"),
        item("location-dot", esc(m.venue), "Venue"),
        item(WEATHER_ICON[m.weather] || "cloud-sun", `${esc(m.weather)} · ${m.temperature_c}°C · wind ${esc(m.wind)}`, "Weather at kick-off"),
        item("flag", `Ref ${esc(m.referee)}`, "Referee"),
        item("users", m.attendance.toLocaleString(), "Attendance"),
    ].join("") + `<span class="mi-tag" title="All match data is generated">SYNTHETIC DATA</span>`;
    if (activeTab === "data") renderData();
}

function onEvent(msg) {
    const key = `${connId}:${msg.match_id}`;
    if (key !== matchKey) resetMatch(key);
    const entry = { key, event: msg.event, positions: msg.positions, possession: msg.possession,
                    commentary: msg.commentary, summary: msg.summary, alerts: msg.alerts || [],
                    story: msg.story, report: msg.report, overlays: msg.overlays || [] };
    history.push(entry);
    if (history.length > MAX_HISTORY) { history.shift(); idx = Math.max(0, idx - 1); }
    liveStats = msg.stats;
    $("timeline-slider").max = history.length - 1;
    $("replay-duration").innerText = msg.event.clock;
    addLogItem(entry);
    addKeyEvent(entry);
    renderMarkers();
    if (live) show(history.length - 1);
    else { updateLiveButton(); updatePinned(); }
    renderActiveTab();
    requestAnimationFrame(() => recordLatency(msg.event.generated_at));
}

function findEntry(msg) {
    const key = `${connId}:${msg.match_id}`;
    return history.find(h => h.key === key && h.event.seq === msg.seq);
}

function onCommentary(msg) {
    const entry = findEntry(msg);
    if (!entry) return;
    entry.commentary = msg.commentary;
    if (msg.alerts) entry.alerts = msg.alerts;
    if ("story" in msg) { entry.story = msg.story; entry.storySource = "LOCAL ENGINE"; updateKeyEventStory(entry); }
    if (msg.report_narrative && entry.report) { entry.report.narrative = msg.report_narrative; entry.reportSource = "LOCAL ENGINE"; updateKeyEventStory(entry); }
    if (entry === anim.entry) showCommentary(entry, msg.commentary.source === "AZURE OPENAI");
    if (reportEntry === entry) openReport(entry);
    if (activeTab === "analysis") { renderImpactList(); renderReports(); }
}

function onStory(msg) {
    const entry = findEntry(msg);
    if (!entry) return;
    entry.story = msg.story;
    entry.storySource = msg.source;
    updateKeyEventStory(entry);
}

function onReport(msg) {
    const entry = findEntry(msg);
    if (!entry || !entry.report) return;
    entry.report.narrative = msg.narrative;
    entry.reportSource = msg.source;
    updateKeyEventStory(entry);
    if (reportEntry === entry) openReport(entry);
    if (activeTab === "analysis") renderReports();
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
        ? "Impact moments, stories and reports are written by Azure OpenAI; everything else uses the local engine."
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
        else if (msg.type === "story") onStory(msg);
        else if (msg.type === "report") onReport(msg);
        else if (msg.type === "answer") onAnswer(msg);
        else if (msg.type === "match_start") onMatchStart(msg);
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
    savePrefs();
}

/* ---------- PREFERENCES (this browser only) ---------- */
function savePrefs() {
    try {
        localStorage.setItem("secondtouch-prefs", JSON.stringify({ ...settings, speed: undefined, pinned }));
    } catch (e) { /* private mode or blocked storage: preferences just aren't remembered */ }
}
function loadPrefs() {
    try {
        const p = JSON.parse(localStorage.getItem("secondtouch-prefs") || "{}");
        for (const k of ["mode", "team", "player", "lang", "fav_team"]) if (p[k]) settings[k] = p[k];
        // preferences saved for clubs that no longer exist fall back to the defaults
        if (!TEAMS.includes(settings.team)) { settings.team = HOME; settings.player = "Thornquist"; }
        if (settings.fav_team !== "NONE" && !TEAMS.includes(settings.fav_team)) settings.fav_team = "NONE";
        if (p.pinned) pinned = p.pinned;
    } catch (e) { /* ignore */ }
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

function applyFav() {
    for (const t of TEAMS) $(`team-col-${t}`).classList.toggle("fav", fav() === t);
    if (fav()) setStatsTeam(fav());
}
$("fav-select").addEventListener("change", e => {
    settings.fav_team = e.target.value;
    applyFav();
    sendConfig();  // Casual commentary now speaks as a supporter of this club
});

$("pin-select").addEventListener("change", e => {
    pinned = e.target.value;
    lastPinnedText = "";
    updatePinned();
    savePrefs();
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
    renderModePanel();
});
$("player-select").addEventListener("change", e => { settings.player = e.target.value; sendConfig(); renderModePanel(); });

function setMode(mode) {
    settings.mode = mode;
    document.querySelectorAll(".mode-btn").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
    for (const m of ["ANALYST", "CASUAL", "PLAYER_CAM"]) $(`panel-mode-${m}`).hidden = m !== mode;
    $("player-focus-container").style.display = mode === "PLAYER_CAM" ? "flex" : "none";
    if (anim.entry) showCommentary(anim.entry);  // all three personas are already here: switch instantly
    renderModePanel();
    sendConfig();
}
document.querySelectorAll(".mode-btn").forEach(btn => btn.addEventListener("click", () => setMode(btn.dataset.mode)));

/* ---------- BOOT ---------- */
loadPrefs();
$("lang-select").value = settings.lang;
$("fav-select").value = settings.fav_team;
$("pin-select").value = pinned;
$("team-select").value = settings.team;
fetch("/api/squads").then(r => r.json()).then(d => {
    squads = d.squads;
    if (!squads[settings.team] || !squads[settings.team][settings.player]) { settings.team = HOME; settings.player = "Thornquist"; }
    buildPlayerDropdown(settings.team, settings.player);
}).catch(() => {});
setMode(settings.mode);
applyFav();
window.addEventListener("resize", resize);
resize();
requestAnimationFrame(frame);
