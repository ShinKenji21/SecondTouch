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
// what the team's shape shows on the pitch; the manager's intent behind it is not something we can see
const STANCE_LABEL = { CHASING: "Pushing forward", PROTECTING: "Sitting deep" };
const STANCE_ICON = { CHASING: "bullhorn", PROTECTING: "shield-halved" };
/* One line-icon set for the whole page (Font Awesome), and card shapes for bookings, as on a TV graphic. */
const fa = name => `<i class="fa-solid fa-${name}" aria-hidden="true"></i>`;
const cardIco = c => `<span class="card-ico ${c === "RED" ? "red" : "yellow"}" title="${c === "RED" ? "Red card" : "Yellow card"}"></span>`;
/* A goal for ev.team: scored, or put into their own net by the opponent. */
const isGoal = ev => ev.outcome === "GOAL" || ev.outcome === "OWN_GOAL";
/* Minute on the 0-90 chart axis: first-half added time stays at 45, not over the second half. */
const chartMin = ev => Math.min(ev.minute, (ev.period || 1) === 1 ? 45 : 90);
const ON_BALL = new Set(["PASS", "DRIBBLE", "SHOT"]);
const MAX_HISTORY = 2000;
const TRAIL = 4;

const $ = id => document.getElementById(id);
const canvas = $("pitchCanvas");
const ctx = canvas.getContext("2d");

/* ---------- MATCH VIEW LANGUAGE ----------
 * Everything the match view writes (pitch banners and labels, the event log, key events) follows the
 * commentary language; the controls around it stay in English. */
const UI = {
    en: {
        teams: { Brackenford: "Brackenford", Kestermouth: "Kestermouth" },
        goal: "GOAL", own_goal: "OWN GOAL", og: "o.g.", var_stands: "VAR: goal stands", var_no: "VAR: NO GOAL",
        var_ruled: "{p}'s goal ruled out for {why}", woodwork: "OFF THE WOODWORK!", injury: "INJURY",
        injury_sub: "{p} ({t}) is down and needs treatment", penalty: "PENALTY!", pen_sub: "{t} · {o} fouled by {p}",
        red: "RED CARD", yellow: "YELLOW CARD", card_sub: "{p} ({t}) on {o}", sub: "SUBSTITUTION",
        sub_sub: "{t}: {p} on, {o} off", ht: "HALF-TIME · TEAMS CHANGE ENDS", ft: "FULL-TIME", impact: "IMPACT",
        offside: "OFFSIDE", added: "+{n} MIN ADDED", replay: "REPLAY",
        reasons: { goal: "Goal", shot: "Shot", big_chance: "Big chance", line_breaking_pass: "Line-breaking pass",
                   high_press_turnover: "High-press turnover", yellow_card: "Yellow card", red_card: "Red card",
                   penalty: "Penalty", penalty_awarded: "Penalty awarded", direct_free_kick: "Direct free kick",
                   own_goal: "Own goal", var_no_goal: "VAR: no goal", woodwork: "Woodwork" },
        sp: { FREE_KICK: "Free kick", CORNER: "Corner", THROW_IN: "Throw-in", PENALTY: "Penalty", GOAL_KICK: "Goal kick" },
        var_reason: { OFFSIDE: "offside", FOUL: "a foul in the build-up", HANDBALL: "handball" },
        sub_reason: { injury: "injury" },  // the only reason for a change a viewer can actually see
        pass: "PASS", cross: "CROSS", through: "THROUGH BALL", long: "LONG BALL", out: "OUT OF PLAY",
        offside_log: "OFFSIDE: {r}", own_goal_by: "OWN GOAL by {o}", claimed: "CLAIMED by {o}",
        behind: "TURNED BEHIND by {o}", cleared: "CLEARED by {o}", intercepted: "INTERCEPTED by {o}",
        dribble: "DRIBBLE", shot: "SHOT", header: "HEADER", pen: "PENALTY", fk: "FREE KICK", rebound: "REBOUND",
        outcome: { GOAL: "GOAL", SAVED: "SAVED", MISS: "MISS", BLOCKED: "BLOCKED", WOODWORK: "WOODWORK" },
        disallowed: "GOAL DISALLOWED (VAR: {why})", injury_log: "INJURY, treatment on the pitch",
        tackle_won: "TACKLE WON on {o}", foul: "FOUL on {o}", pen_foul: "PENALTY! FOUL on {o}", sub_log: "SUB",
        half_time: "HALF TIME", full_time: "FULL TIME", restart: "→ {sp} {t}",
        k_own_goal: "{o} for {t}", k_penalty: "PENALTY to {t}: {o} fouled by {p}", k_card: "{p} ({t}) for a foul on {o}",
        k_sub: "{t}: {p} on, {o} off", k_ht: "HALF-TIME REPORT", k_ft: "FULL-TIME REPORT", k_save: "SAVE",
        k_pen_saved: "PENALTY SAVED", k_denies: "{o} denies {p}", k_pen_missed: "PENALTY MISSED", k_big: "BIG CHANCE",
        k_woodwork: "WOODWORK", k_recap: "RECAP",
    },
    es: {
        teams: { Brackenford: "Brackenford", Kestermouth: "Kestermouth" },
        goal: "GOL", own_goal: "GOL EN PROPIA", og: "p.p.", var_stands: "VAR: gol válido", var_no: "VAR: NO ES GOL",
        var_ruled: "Gol de {p} anulado por {why}", woodwork: "¡AL PALO!", injury: "LESIÓN",
        injury_sub: "{p} ({t}) está en el suelo y recibe atención", penalty: "¡PENALTI!", pen_sub: "{t} · falta de {p} sobre {o}",
        red: "TARJETA ROJA", yellow: "TARJETA AMARILLA", card_sub: "{p} ({t}) por falta sobre {o}", sub: "CAMBIO",
        sub_sub: "{t}: entra {p}, sale {o}", ht: "DESCANSO · CAMBIO DE CAMPO", ft: "FINAL", impact: "IMPACTO",
        offside: "FUERA DE JUEGO", added: "+{n} MIN DE AÑADIDO", replay: "REPETICIÓN",
        reasons: { goal: "Gol", shot: "Disparo", big_chance: "Ocasión clara", line_breaking_pass: "Pase entre líneas",
                   high_press_turnover: "Robo en presión alta", yellow_card: "Amarilla", red_card: "Roja",
                   penalty: "Penalti", penalty_awarded: "Penalti señalado", direct_free_kick: "Falta directa",
                   own_goal: "Gol en propia", var_no_goal: "VAR: no es gol", woodwork: "Al palo" },
        sp: { FREE_KICK: "Tiro libre", CORNER: "Córner", THROW_IN: "Saque de banda", PENALTY: "Penalti", GOAL_KICK: "Saque de puerta" },
        var_reason: { OFFSIDE: "fuera de juego", FOUL: "falta previa", HANDBALL: "mano" },
        sub_reason: { injury: "lesión" },
        pass: "PASE", cross: "CENTRO", through: "PASE AL HUECO", long: "PASE LARGO", out: "FUERA",
        offside_log: "FUERA DE JUEGO: {r}", own_goal_by: "GOL EN PROPIA de {o}", claimed: "ATRAPADO por {o}",
        behind: "DESPEJADO A CÓRNER por {o}", cleared: "DESPEJADO por {o}", intercepted: "INTERCEPTADO por {o}",
        dribble: "REGATE", shot: "DISPARO", header: "CABEZAZO", pen: "PENALTI", fk: "TIRO LIBRE", rebound: "RECHACE",
        outcome: { GOAL: "GOL", SAVED: "PARADA", MISS: "FUERA", BLOCKED: "BLOQUEADO", WOODWORK: "AL PALO" },
        disallowed: "GOL ANULADO (VAR: {why})", injury_log: "LESIÓN, atención en el campo",
        tackle_won: "ENTRADA GANADA a {o}", foul: "FALTA sobre {o}", pen_foul: "¡PENALTI! FALTA sobre {o}", sub_log: "CAMBIO",
        half_time: "DESCANSO", full_time: "FINAL", restart: "→ {sp} {t}",
        k_own_goal: "{o}, a favor de {t}", k_penalty: "PENALTI para {t}: falta de {p} sobre {o}", k_card: "{p} ({t}) por falta sobre {o}",
        k_sub: "{t}: entra {p}, sale {o}", k_ht: "INFORME DEL DESCANSO", k_ft: "INFORME FINAL", k_save: "PARADA",
        k_pen_saved: "PENALTI PARADO", k_denies: "{o} detiene a {p}", k_pen_missed: "PENALTI FALLADO", k_big: "OCASIÓN CLARA",
        k_woodwork: "AL PALO", k_recap: "RESUMEN",
    },
    ja: {
        teams: { Brackenford: "ブラッケンフォード", Kestermouth: "ケスターマス" },
        goal: "ゴール", own_goal: "オウンゴール", og: "OG", var_stands: "VAR：ゴール認定", var_no: "VAR：ノーゴール",
        var_ruled: "{p}のゴールは{why}で取り消し", woodwork: "ポスト直撃！", injury: "負傷",
        injury_sub: "{p}（{t}）が倒れて治療中", penalty: "PK！", pen_sub: "{t} · {p}が{o}を倒す",
        red: "レッドカード", yellow: "イエローカード", card_sub: "{p}（{t}）、{o}へのファウル", sub: "選手交代",
        sub_sub: "{t}：{p} IN、{o} OUT", ht: "ハーフタイム · エンドが替わる", ft: "試合終了", impact: "注目",
        offside: "オフサイド", added: "アディショナルタイム +{n}分", replay: "リプレイ",
        reasons: { goal: "ゴール", shot: "シュート", big_chance: "決定機", line_breaking_pass: "ライン突破のパス",
                   high_press_turnover: "ハイプレスで奪取", yellow_card: "イエローカード", red_card: "レッドカード",
                   penalty: "PK", penalty_awarded: "PK獲得", direct_free_kick: "直接FK",
                   own_goal: "オウンゴール", var_no_goal: "VARでノーゴール", woodwork: "ポスト直撃" },
        sp: { FREE_KICK: "フリーキック", CORNER: "コーナーキック", THROW_IN: "スローイン", PENALTY: "PK", GOAL_KICK: "ゴールキック" },
        var_reason: { OFFSIDE: "オフサイド", FOUL: "攻撃中のファウル", HANDBALL: "ハンド" },
        sub_reason: { injury: "負傷" },
        pass: "パス", cross: "クロス", through: "スルーパス", long: "ロングボール", out: "ラインアウト",
        offside_log: "オフサイド：{r}", own_goal_by: "{o}のオウンゴール", claimed: "{o}がキャッチ",
        behind: "{o}がクリア、CKに", cleared: "{o}がクリア", intercepted: "{o}がカット",
        dribble: "ドリブル", shot: "シュート", header: "ヘディング", pen: "PK", fk: "FK", rebound: "こぼれ球",
        outcome: { GOAL: "ゴール", SAVED: "セーブ", MISS: "枠外", BLOCKED: "ブロック", WOODWORK: "ポスト" },
        disallowed: "ゴール取り消し（VAR：{why}）", injury_log: "負傷、ピッチ上で治療",
        tackle_won: "{o}からボール奪取", foul: "{o}へのファウル", pen_foul: "PK！{o}へのファウル", sub_log: "交代",
        half_time: "ハーフタイム", full_time: "試合終了", restart: "→ {t}の{sp}",
        k_own_goal: "{o}（{t}の得点）", k_penalty: "{t}にPK：{p}が{o}を倒す", k_card: "{p}（{t}）、{o}へのファウル",
        k_sub: "{t}：{p} IN、{o} OUT", k_ht: "ハーフタイムレポート", k_ft: "試合終了レポート", k_save: "セーブ",
        k_pen_saved: "PKストップ", k_denies: "{o}が{p}のシュートを阻止", k_pen_missed: "PK失敗", k_big: "決定機",
        k_woodwork: "ポスト直撃", k_recap: "まとめ",
    },
};
const ui = () => UI[settings.lang] || UI.en;
/* A match-view string with {placeholders} filled in. */
const tr = (key, vars = {}) => String(ui()[key] ?? UI.en[key]).replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");
const teamName = t => ui().teams[t] || TEAM_LABEL[t] || t;
const reasonName = r => ui().reasons[r] || UI.en.reasons[r] || r;
const spName = sp => ui().sp[sp] || UI.en.sp[sp] || sp;
const varWhy = ev => (ui().var_reason[ev.var.reason] || UI.en.var_reason[ev.var.reason]);

/* ---------- INTERFACE LANGUAGE ----------
 * Labels, tabs, headings and buttons follow the language too: elements marked data-i18n keep their English
 * text in the page and take these when Spanish or Japanese is picked. Long help notes stay in English. */
const CHROME = {
    en: {"open_report": "Open report", "rs_shots": "Shots", "rs_on_target": "On target", "rs_possession": "Possession", "rs_pass": "Pass accuracy", "rs_big": "Big chances", "rs_press": "Ball wins in opp. half", "rs_corners": "Corners", "rs_fouls": "Fouls", "rs_offsides": "Offsides", "rs_woodwork": "Woodwork", "rs_tilt": "Field tilt", "rs_cards": "Cards", "rs_distance": "Distance (km)", "best": "Best player", "next_half": "Second half kicks off shortly", "next_match": "New match starts shortly", "lg_corner": "corner", "lg_fk": "free kick", "lg_throw": "throw-in", "lg_gk": "goal kick", "lg_pen": "penalty", "lg_off": "offside", "pc_touches": "Touches", "pc_passes_completed": "Passes completed", "pc_shots": "Shots", "pc_tackles_won": "Tackles won", "pc_sprints": "Sprints", "pc_distance_km": "Distance (km)", "pc_top_speed": "Top speed (km/h)", "pc_saves": "Saves", "team_avg": "team avg {v}", "fitness": "Est. fitness", "heat": "Heat map", "heat_note": "{n} snapshots · {t} attacking →", "attack": "{t} attack {a}", "lg_pass": "Pass difficulty easy → hard", "lg_keys": "Click a player to follow them · Space pause · ← → step · L live", "q_best": "Who is the best player so far?", "q_player": "How is {p} playing?", "q_sofar": "What has happened so far?", "q_ht": "Give me the half-time report", "q_ft": "Give me the full-time report", "fav_only": "{t} only", "fav_any": "My club only", "ask_ph": "Ask about the match, e.g. 'Who is pressing better?' or 'How is Thornquist playing?'", "live": "LIVE", "thinking": "Thinking…"},
    es: {"open_report": "Abrir informe", "rs_shots": "Disparos", "rs_on_target": "A puerta", "rs_possession": "Posesión", "rs_pass": "Precisión de pase", "rs_big": "Ocasiones claras", "rs_press": "Recuperaciones en campo rival", "rs_corners": "Córners", "rs_fouls": "Faltas", "rs_offsides": "Fueras de juego", "rs_woodwork": "Palos", "rs_tilt": "Dominio territorial", "rs_cards": "Tarjetas", "rs_distance": "Distancia (km)", "best": "Mejor jugador", "next_half": "La segunda parte empieza en breve", "next_match": "El próximo partido empieza en breve", "lg_corner": "córner", "lg_fk": "tiro libre", "lg_throw": "saque de banda", "lg_gk": "saque de puerta", "lg_pen": "penalti", "lg_off": "fuera de juego", "pc_touches": "Toques", "pc_passes_completed": "Pases completados", "pc_shots": "Disparos", "pc_tackles_won": "Entradas ganadas", "pc_sprints": "Sprints", "pc_distance_km": "Distancia (km)", "pc_top_speed": "Velocidad máx. (km/h)", "pc_saves": "Paradas", "team_avg": "media equipo {v}", "fitness": "Forma física est.", "heat": "Mapa de calor", "heat_note": "{n} capturas · {t} ataca →", "attack": "{t} ataca {a}", "lg_pass": "Dificultad del pase: fácil → difícil", "lg_keys": "Clic en un jugador para seguirlo · Espacio pausa · ← → paso · L directo", "guide": "Guía", "m_analyst": "Analista", "m_casual": "Casual", "m_cam": "Cámara jugador", "kickoff": "EMPEZAR PARTIDO", "away": "Mientras no estabas", "h_ai": "Análisis IA en directo", "h_tele": "Telemetría de equipos", "h_glance": "El partido de un vistazo", "h_log": "Registro en directo", "impact_only": "Solo impacto", "t_stats": "Estadísticas", "t_tactics": "Táctica", "t_events": "Momentos e historias", "t_analysis": "Análisis a fondo", "t_ask": "Pregunta a la IA", "t_agents": "Agentes IA", "t_data": "Datos y gráficos", "h_players": "Estadísticas de jugadores", "h_avgpos": "Posiciones medias", "h_xg": "Carrera de xG", "h_mom": "Dominio", "h_flow": "Ritmo: control o caos, y presión", "h_shots": "Mapa de disparos", "h_impact": "Momentos de impacto", "h_reports": "Informes", "h_desk": "La mesa de agentes", "h_runs": "Ejecuciones en directo", "h_dataset": "Conjunto de datos sintético", "h_cues": "Señales de gráficos", "ask_btn": "Preguntar", "fav_none": "Sin favorito", "fav_home": "Hincha del Brackenford", "fav_away": "Hincha del Kestermouth", "pin_none": "Sin dato fijado", "pin_xg": "Fijar: xG", "pin_poss": "Fijar: posesión", "pin_ot": "Fijar: tiros a puerta", "pin_corners": "Fijar: córners", "pin_cards": "Fijar: tarjetas", "pin_pass": "Fijar: precisión de pase", "pin_press": "Fijar: presión", "pin_dist": "Fijar: distancia recorrida", "pin_speed": "Fijar: velocidad máxima", "q_mom": "¿Quién domina ahora?", "q_chances": "¿Quién crea mejores ocasiones?", "q_press": "¿Cómo presionan los equipos?", "q_set": "¿Cuántos córners y faltas?", "q_best": "¿Quién es el mejor jugador hasta ahora?", "q_player": "¿Cómo está jugando {p}?", "q_sofar": "¿Qué ha pasado hasta ahora?", "q_ht": "Dame el informe del descanso", "q_ft": "Dame el informe final", "fav_only": "Solo {t}", "fav_any": "Solo mi club", "ask_ph": "Pregunta sobre el partido, p. ej. «¿Quién presiona mejor?»", "live": "EN VIVO", "thinking": "Pensando…"},
    ja: {"open_report": "レポートを開く", "rs_shots": "シュート", "rs_on_target": "枠内", "rs_possession": "ポゼッション", "rs_pass": "パス成功率", "rs_big": "決定機", "rs_press": "敵陣でのボール奪取", "rs_corners": "コーナーキック", "rs_fouls": "ファウル", "rs_offsides": "オフサイド", "rs_woodwork": "ポスト直撃", "rs_tilt": "敵陣支配率", "rs_cards": "カード", "rs_distance": "走行距離（km）", "best": "ベストプレーヤー", "next_half": "まもなく後半開始", "next_match": "まもなく次の試合開始", "lg_corner": "CK", "lg_fk": "FK", "lg_throw": "スローイン", "lg_gk": "ゴールキック", "lg_pen": "PK", "lg_off": "オフサイド", "pc_touches": "タッチ", "pc_passes_completed": "パス成功", "pc_shots": "シュート", "pc_tackles_won": "タックル成功", "pc_sprints": "スプリント", "pc_distance_km": "走行距離（km）", "pc_top_speed": "最高速度（km/h）", "pc_saves": "セーブ", "team_avg": "チーム平均 {v}", "fitness": "推定コンディション", "heat": "ヒートマップ", "heat_note": "{n}スナップショット · {t}が右へ攻撃 →", "attack": "{t} 攻撃方向 {a}", "lg_pass": "パス難度：易 → 難", "lg_keys": "選手をクリックで追跡 · Spaceで一時停止 · ← →でコマ送り · Lでライブ", "guide": "ガイド", "m_analyst": "アナリスト", "m_casual": "カジュアル", "m_cam": "選手カメラ", "kickoff": "試合開始", "away": "見逃した間に", "h_ai": "AIライブ分析", "h_tele": "チームデータ", "h_glance": "試合の概要", "h_log": "ライブイベントログ", "impact_only": "注目のみ", "t_stats": "スタッツ", "t_tactics": "戦術", "t_events": "主な出来事とストーリー", "t_analysis": "詳細分析", "t_ask": "AIに質問", "t_agents": "AIエージェント", "t_data": "データとオーバーレイ", "h_players": "選手スタッツ", "h_avgpos": "平均ポジション", "h_xg": "xGの推移", "h_mom": "流れ", "h_flow": "試合の流れ：支配か混戦か、プレス", "h_shots": "シュートマップ", "h_impact": "注目の場面", "h_reports": "レポート", "h_desk": "エージェントデスク", "h_runs": "エージェントの実行ログ", "h_dataset": "合成データセット", "h_cues": "オーバーレイ指示フィード", "ask_btn": "質問する", "fav_none": "応援クラブなし", "fav_home": "ブラッケンフォードを応援", "fav_away": "ケスターマスを応援", "pin_none": "固定表示なし", "pin_xg": "固定：xG", "pin_poss": "固定：ポゼッション", "pin_ot": "固定：枠内シュート", "pin_corners": "固定：コーナーキック", "pin_cards": "固定：カード", "pin_pass": "固定：パス成功率", "pin_press": "固定：プレス強度", "pin_dist": "固定：走行距離", "pin_speed": "固定：最高速度", "q_mom": "今、流れはどちらに？", "q_chances": "より良いチャンスを作っているのは？", "q_press": "両チームのプレスは？", "q_set": "コーナーとファウルの数は？", "q_best": "ここまでのベストプレーヤーは？", "q_player": "{p}の出来は？", "q_sofar": "ここまでの展開は？", "q_ht": "ハーフタイムレポートを見せて", "q_ft": "試合終了レポートを見せて", "fav_only": "{t}のみ", "fav_any": "応援クラブのみ", "ask_ph": "試合について質問：例「どちらのプレスが効いている？」", "live": "ライブ", "thinking": "考え中…"},
};
/* An interface string in the current language, with {placeholders} filled in. */
const ct = (key, vars = {}) => String((CHROME[settings.lang] || {})[key] ?? CHROME.en[key])
    .replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? "");

function applyChrome() {
    for (const el of Array.from(document.querySelectorAll("[data-i18n]"))) {
        if (el.dataset.en === undefined) el.dataset.en = el.textContent;
        el.textContent = (CHROME[settings.lang] || {})[el.dataset.i18n] || el.dataset.en;
    }
    $("ai-query-input").placeholder = ct("ask_ph");
    updateSuggestions();
    if (anim.entry) updateUI(anim.entry);  // the player card and the pitch legend are drawn from code
}

/* ---------- STATE ---------- */
const settings = { mode: "PLAYER_CAM", team: HOME, player: "Thornquist", speed: 1, lang: "en", fav_team: "NONE" };
let pinned = "none";
let squads = null;            // team -> pid -> {name, num, pos, starter}
let interval = 1.5;           // seconds between events at 1x (from the server)
let ws = null, started = false, connId = 0;
let history = [];             // [{key, event, positions, possession, commentary, summary, alerts, story, report, overlays}]
let matchKey = null, metadata = null;
let liveStats = null, liveFitness = null, liveStance = null, liveSubs = null;
let agentRuns = [], aiEngine;          // agent desk runs (newest first); the model, null if off, undefined until connected
let aiHold = null;                     // fresh AI commentary stays on the card for a moment
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
    if (!ev.team || ev.event_type === "SUBSTITUTION" || ev.event_type === "INJURY") return dur * 0.3;
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
    if (!ev.team || ev.event_type === "SUBSTITUTION" || ev.event_type === "INJURY") return;
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
function drawBall(entry, t, screen, now) {
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
    let x = lerp(x0, x1, t), y = lerp(y0, y1, t);
    // play stopped (out of play, a goal, a save held): once the ball has landed it is carried to
    // where play restarts (corner flag, six-yard box, keeper's hands, centre spot) instead of jumping there
    if (t >= 1 && entry.ball && Math.hypot(entry.ball[0] - l.end_x, entry.ball[1] - l.end_y) > 3) {
        const k = easeMove(Math.max(0, Math.min(1, (now - anim.start - anim.ballDur - 250) / 650)));
        const [bx, by] = pctPx(...entry.ball);
        x = lerp(x, bx + dir(entry.possession), k);
        y = lerp(y, by, k);
    }
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
        const text = speedy ? `${cue.player} ${cue.value_kmh.toFixed(1)} km/h` : `${cue.player} ${cue.value_km} km`;
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
    if (isGoal(ev) && done) {
        const k = Math.min(1, (now - anim.start - anim.ballDur) / 700);
        if (k > 0) {
            const [gx, gy] = pctPx(ev.location.end_x, ev.location.end_y);
            ctx.strokeStyle = `rgba(234,179,8,${1 - k})`; ctx.lineWidth = 4;
            ctx.beginPath(); ctx.arc(gx, gy, 10 + k * 50, 0, Math.PI * 2); ctx.stroke();
        }
        const word = tr(ev.outcome === "OWN_GOAL" ? "own_goal" : "goal");
        const cheer = fav() ? (ev.team === fav() ? `${word}! ★` : word) : `${word}!`;
        const scorer = ev.outcome === "OWN_GOAL" ? `${ev.opponent} (${tr("og")})` : ev.player;
        const checked = ev.var && ev.var.decision === "GOAL_STANDS" ? ` · ${tr("var_stands")}` : "";
        banner(cheer, "#EAB308", `${scorer} · ${teamName(ev.team)} ${ev.score.home}-${ev.score.away}${checked}`);
    } else if (ev.outcome === "DISALLOWED" && done) {
        banner(tr("var_no"), "#EF4444", tr("var_ruled", { p: ev.player, why: varWhy(ev) }));
    } else if (ev.outcome === "WOODWORK" && done) {
        banner(tr("woodwork"), "#F97316", `${ev.player} · ${teamName(ev.team)}`);
    } else if (ev.event_type === "INJURY") {
        banner(tr("injury"), "#E5E7EB", tr("injury_sub", { p: ev.player, t: teamName(ev.team) }));
    } else if (ev.restart === "PENALTY" && done) {
        const card = ev.card ? ` · ${tr(ev.card === "RED" ? "red" : "yellow")}` : "";
        banner(tr("penalty"), "#EF4444", tr("pen_sub", { t: teamName(ev.restart_team), o: ev.opponent, p: ev.player }) + card);
    } else if (ev.card && done) {
        banner(tr(ev.card === "RED" ? "red" : "yellow"), ev.card === "RED" ? "#EF4444" : "#EAB308",
            tr("card_sub", { p: ev.player, t: teamName(ev.team), o: ev.opponent }));
    } else if (ev.event_type === "SUBSTITUTION") {
        const why = (ev.tags || []).map(x => ui().sub_reason[x]).filter(Boolean)[0];
        banner(tr("sub"), "#E5E7EB", tr("sub_sub", { t: teamName(ev.team), p: ev.player, o: ev.player_off }) + (why ? ` · ${why}` : ""));
    } else if (ev.event_type === "HALF_TIME" || ev.event_type === "FULL_TIME") {
        banner(tr(ev.event_type === "HALF_TIME" ? "ht" : "ft"), "#FFFFFF",
            `${teamName(HOME)} ${ev.score.home}-${ev.score.away} ${teamName(AWAY)}`);
    }
    let chipY = 8;
    if (ev.is_impact_moment) {
        const why = ev.impact_reasons.map(reasonName).join(" · ");
        chip(`${tr("impact")} · ${why}`, 8, chipY, "rgba(234,179,8,0.92)", "#000");
        chipY += 24;
    }
    if (ev.set_piece) {
        chip(`${spName(ev.set_piece).toUpperCase()} · ${ev.player}`, 8, chipY, "rgba(8,12,20,0.85)", TEAM_COLOR[ev.team]);
    } else if (ev.outcome === "OFFSIDE" && done) {
        chip(`${tr("offside")} · ${ev.receiver}`, 8, chipY, "rgba(234,179,8,0.92)", "#000");
    } else if (ev.restart && ev.restart !== "PENALTY" && done) {
        chip(`${spName(ev.restart).toUpperCase()} · ${TEAM_SHORT[ev.restart_team]}`, 8, chipY, "rgba(8,12,20,0.85)", TEAM_COLOR[ev.restart_team]);
    }
    if (ev.added_time) chip(tr("added", { n: ev.added_time }), W - 8, live ? 8 : 32, "rgba(8,12,20,0.85)", "#E5E7EB", "right");
    if (!live) chip(`${tr("replay")} ${ev.clock}`, W - 8, 8, "rgba(8,12,20,0.85)", "#EAB308", "right");
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
            drawBall(entry, entry.event.event_type === "DRIBBLE" ? easeMove(tb) : ease(tb), screen, now);
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
const AGENT_ICON = { Analyst: "magnifying-glass", Commentator: "pen-nib", Storyteller: "book-open", "Studio analyst": "microphone",
    "Match desk": "comments", "Fact-checker": "circle-check", Orchestrator: "triangle-exclamation" };
const STEP_LABEL = { passed: "passed", revise: "sent back", rejected: "rejected", revised: "revised", timeout: "timed out", error: "error" };

/* The fact-checker's icon says how its check went: passed, sent back or rejected. */
const stepIcon = s => fa(s.agent === "Fact-checker" ? (s.status === "passed" ? "circle-check" : s.status === "revise" ? "rotate-left" : "circle-xmark")
    : AGENT_ICON[s.agent] || "circle");

/* "Analyst 2.4s · 1 tool → Commentator 1.5s → Fact-checker passed": who did what for this text. */
/* `compact` (the live card, two rows at most) folds a send-back and its rewrite into "passed after a revision";
 * the AI Agents tab shows every step. */
function trailHtml(p, compact = false) {
    if (!p || !p.steps) return "";
    const revised = compact && p.steps.some(s => s.status === "revise");
    const steps = revised ? p.steps.filter(s => s.status !== "revise" && s.status !== "revised") : p.steps;
    return steps.map(s => {
        const icon = stepIcon(s);
        const tools = /^(\d+) tool/.exec(s.detail || "");
        const extra = s.agent === "Fact-checker" ? ` ${STEP_LABEL[s.status] || s.status}${revised && s.status === "passed" ? " after a revision" : ""}` : `${s.status === "revised" ? " (revised)" : ""} ${(s.ms / 1000).toFixed(1)}s${tools && +tools[1] ? ` · ${tools[1]} tool${+tools[1] > 1 ? "s" : ""}` : ""}`;
        return `<span class="at-step at-${s.status}" title="${esc(s.detail || "")}">${icon} ${esc(s.agent)}${extra}</span>`;
    }).join('<span class="at-arrow">→</span>');
}
/* Who wrote a text, as the viewer sees it: the agents on Azure, or the instant templates that keep pace with play. */
const srcLabel = s => s === "AZURE OPENAI" ? "AZURE OPENAI" : "INSTANT";
const verifiedTag = p => p && (p.status === "passed" || p.status === "revised") ? ' <span class="ai-source verified">✓ fact-checked</span>' : "";

/* While fresh AI commentary is on hold, routine events don't replace it (impact moments still do). */
function cardEntry() {
    return aiHold && performance.now() < aiHold.until && live ? aiHold.entry : anim.entry;
}

function showCommentary(entry, flash = false) {
    const c = entry.commentary;
    $("ai-commentary").innerText = c[MODE_KEY[settings.mode]];
    const lang = { en: "EN", es: "ES", ja: "JA" }[c.lang] || "";
    const behind = entry !== anim.entry ? ` · ${entry.event.clock}` : "";
    $("ai-source").innerText = `${srcLabel(c.source)} · ${MODE_LABEL[settings.mode]} · ${lang}${behind}`;
    $("ai-source").classList.toggle("from-azure", c.source === "AZURE OPENAI");
    const trail = c.source === "AZURE OPENAI" ? trailHtml(entry.pipeline, true) : "";
    $("agent-trail").classList.toggle("empty", !trail);  // the row keeps its height: the panels below stay put
    $("agent-trail").innerHTML = trail;
    const ev = entry.event;
    const badge = $("impact-badge");
    badge.hidden = !ev.is_impact_moment;
    badge.innerHTML = ev.is_impact_moment ? `${fa("bolt")} ${esc(reasonName(ev.impact_reasons[0]))}` : "";
    if (flash) {
        const card = $("ai-card");
        card.classList.remove("ai-flash"); void card.offsetWidth; card.classList.add("ai-flash");
    }
}

const TOAST_ICON = { added_time: "stopwatch", chasing: "bullhorn", protecting: "shield-halved", recap: "newspaper",
    first_goal: "futbol", brace: "futbol", hat_trick: "futbol", touches: "shoe-prints", passes_completed: "bullseye",
    team_passes: "link", tackles_won: "shield", saves: "hand", spell: "rotate", top_speed: "bolt", chaos: "tornado",
    control: "sliders", press_up: "chart-line" };

function showToasts(entry) {
    const stack = $("toast-stack");
    for (const a of entry.alerts || []) {
        if (a.kind !== "milestone" && a.kind !== "flow") continue;
        const el = document.createElement("div");
        el.className = `toast ${a.kind}${a.team && a.team === fav() ? " fav" : ""}`;
        if (a.team) el.style.setProperty("--tc", TEAM_COLOR[a.team]);
        const times = a.key === "hat_trick" ? 3 : a.key === "brace" ? 2 : 1;
        el.innerHTML = `<span class="toast-icon">${fa(TOAST_ICON[a.key] || "circle-info").repeat(times)}</span><span>${esc(a.text)}</span>`;
        stack.prepend(el);
        while (stack.children.length > 3) stack.lastChild.remove();
        setTimeout(() => el.classList.add("out"), 4200 / Math.sqrt(settings.speed));
        setTimeout(() => el.remove(), 4700 / Math.sqrt(settings.speed));
    }
}

function pinnedText() {
    if (pinned === "none" || !liveStats || !anim.entry) return "";
    const s = anim.entry.summary, T = liveStats.teams;
    const pair = (label, h, a) => `${label}  ${TEAM_SHORT[HOME]} ${h} · ${a} ${TEAM_SHORT[AWAY]}`;
    const cards = x => `${x.yellow} yellow${x.red ? `, ${x.red} red` : ""}`;
    switch (pinned) {
        case "xg": return pair("xG", s.xg[0].toFixed(2), s.xg[1].toFixed(2));
        case "possession": return pair("Possession", `${s.possession[0]}%`, `${s.possession[1]}%`);
        case "on_target": return pair("On target", s.on_target[0], s.on_target[1]);
        case "corners": return pair("Corners", T[HOME].corners, T[AWAY].corners);
        case "cards": return pair("Cards", cards(T[HOME]), cards(T[AWAY]));
        case "pass_pct": return pair("Pass accuracy", `${T[HOME].pass_pct}%`, `${T[AWAY].pass_pct}%`);
        case "press": return pair("Pressure applied", s.flow.press[HOME], s.flow.press[AWAY]);
        case "distance": return pair("Distance", `${T[HOME].distance_km} km`, `${T[AWAY].distance_km} km`);
        case "top_speed": {
            let best = null;
            for (const t of TEAMS) for (const p of liveStats.players[t]) if (!best || p.top_speed > best.p.top_speed) best = { t, p };
            return best && best.p.top_speed ? `Top speed  ${best.p.id} (${TEAM_SHORT[best.t]}) ${best.p.top_speed.toFixed(1)} km/h` : "Top speed  —";
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
    if (ev.is_impact_moment || !aiHold || performance.now() >= aiHold.until || !live) { aiHold = null; showCommentary(entry); }
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
    $(`dir-${HOME}`).innerText = ct("attack", { t: teamName(HOME), a: rt === HOME ? "→" : "←" });
    $(`dir-${AWAY}`).innerText = ct("attack", { t: teamName(AWAY), a: rt === AWAY ? "→" : "←" });
    updatePinned();
    renderModePanel();
}

/* ---------- MODE PANELS ---------- */
function renderModePanel() {
    updateSuggestions();
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

/* One row comparing the two teams: values at the ends, bars growing out from the label. */
function compareRow(label, h, a, fmt = v => v) {
    const max = Math.max(h || 0, a || 0, 1e-9);
    return `<div class="glance-row">
        <span class="g-val">${fmt(h, 0)}</span>
        <div class="g-bar left"><div style="width:${100 * (h || 0) / max}%; background:${TEAM_COLOR[HOME]}"></div></div>
        <span class="g-label">${label}</span>
        <div class="g-bar"><div style="width:${100 * (a || 0) / max}%; background:${TEAM_COLOR[AWAY]}"></div></div>
        <span class="g-val">${fmt(a, 1)}</span></div>`;
}

/* Analyst: both teams side by side in one card, plus the numbers behind the action on screen. */
function renderTeamTelemetry() {
    const e = anim.entry, s = e.summary, ev = e.event, m = ev.metrics || {};
    const T = liveStats ? liveStats.teams : null;
    const stance = TEAMS.filter(t => liveStance && STANCE_LABEL[liveStance[t]])
        .map(t => `<span class="stance-chip" style="border-color:${TEAM_COLOR[t]}" title="What the team's shape shows: a higher line and more direct play, or dropping deeper">${TEAM_SHORT[t]} ${fa(STANCE_ICON[liveStance[t]])} ${STANCE_LABEL[liveStance[t]]}</span>`).join("");
    const last = TEAMS.map(team => {
        const a = lastActionOf(team);
        const what = a ? `#${player(team, a.player).num} <strong>${esc(a.player)}</strong> · ${a.set_piece ? spName(a.set_piece).toLowerCase()
            : a.event_type === "SHOT" ? shotKind(a).toLowerCase() : a.event_type === "PASS" ? passKind(a).toLowerCase() : a.event_type.toLowerCase()}${a.outcome ? " " + a.outcome.toLowerCase() : ""} · ${a.clock}` : "no action yet";
        return `<div class="tt-last" style="--tc:${TEAM_COLOR[team]}"><span class="tt-team">${TEAM_SHORT[team]}</span>${what}</div>`;
    }).join("");
    const now = ev.team && ev.event_type !== "SUBSTITUTION" && ev.event_type !== "INJURY" ? `
        <div class="tt-now-head">On screen now: <strong>${esc(ev.player)}</strong>, ${TEAM_LABEL[ev.team]}</div>
        <div class="telemetry-grid">
            <div><span class="tg-label">Pass difficulty</span><span>${m.pass_difficulty != null ? `${m.pass_difficulty}/100` : "—"}</span></div>
            <div><span class="tg-label">Pressure</span><span>${m.pressure ? `${m.pressure.toLowerCase()} · ${m.pressure_index}` : "—"}</span></div>
            <div><span class="tg-label">Defender</span><span>${m.nearest_defender_m != null ? `${m.nearest_defender_m} m` : "—"}</span></div>
            <div><span class="tg-label">Ball speed</span><span>${m.ball_speed_kmh != null ? `${m.ball_speed_kmh} km/h` : "—"}</span></div>
            <div><span class="tg-label">${m.xg != null ? "Shot xG" : "Forward gain"}</span><span>${m.xg != null ? m.xg.toFixed(2) : m.forward_gain_m != null ? `${m.forward_gain_m} m` : "—"}</span></div>
            <div><span class="tg-label">Bypassed</span><span>${m.players_bypassed ?? "—"}</span></div>
        </div>` : "";
    const maxSubs = metadata ? metadata.max_subs : 5;
    const rows = T ? [
        compareRow("xG", s.xg[0], s.xg[1], v => v.toFixed(2)),
        compareRow("Shots (on target)", s.shots[0], s.shots[1], (v, i) => `${v} (${s.on_target[i]})`),
        compareRow("Possession", s.possession[0], s.possession[1], v => `${v}%`),
        compareRow("Field tilt", T[HOME].field_tilt, T[AWAY].field_tilt, v => `${v}%`),
        compareRow("Pressure applied", s.flow.press[HOME], s.flow.press[AWAY]),
        compareRow("Pass accuracy", T[HOME].pass_pct, T[AWAY].pass_pct, v => `${v}%`),
        compareRow("Avg pass difficulty", T[HOME].avg_pass_difficulty, T[AWAY].avg_pass_difficulty),
        compareRow("Top ball speed", T[HOME].top_ball_speed, T[AWAY].top_ball_speed, v => v ? Math.round(v) : "—"),
        compareRow("Distance (km)", T[HOME].distance_km, T[AWAY].distance_km, v => v.toFixed(1)),
        compareRow("Subs used", liveSubs ? liveSubs[HOME] : 0, liveSubs ? liveSubs[AWAY] : 0, v => `${v}/${maxSubs}`),
    ].join("") : "";
    $("team-telemetry").innerHTML = `
        <div class="card-header-flex"><h3>Team telemetry <span class="info" data-tip="Both teams compared live. Bars grow towards the team that leads each number. 'On screen now' breaks down the action being shown: how hard the pass was, how much pressure was on the ball, and how fast it travelled.">ⓘ</span></h3>${stance}</div>
        ${last}${now}<div class="tt-rows">${rows}</div>`;
}

function moodText(flow) {
    const tempo = flow.tempo === "HIGH" ? " Fast and frantic right now." : flow.tempo === "SLOW" ? " The pace has dropped." : "";
    if (flow.state === "CONTROL") return `${TEAM_LABEL[flow.state_team]} are calmly keeping the ball.${tempo}`;
    if (flow.state === "CHAOS") return `End to end: the ball keeps changing hands.${tempo}`;
    return `An even contest at the moment.${tempo}`;
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
    const goals = history.filter(h => h.key === matchKey && isGoal(h.event) && history.indexOf(h) <= idx);
    const scorer = ev => ev.outcome === "OWN_GOAL" ? `${esc(ev.opponent)} (o.g.)` : esc(ev.player);
    $("glance-goals").innerHTML = goals.map(h => `<li style="--tc:${TEAM_COLOR[h.event.team]}">${fa("futbol")} ${h.event.clock} ${scorer(h.event)} <span class="text-muted">${TEAM_LABEL[h.event.team]}</span></li>`).join("")
        || `<li class="text-muted">No goals yet</li>`;
}

const PC_STATS = {
    outfield: ["touches", "passes_completed", "shots", "tackles_won", "sprints", "distance_km", "top_speed"],
    keeper: ["saves", "touches", "passes_completed", "distance_km"],
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
    const fitNow = liveFitness && liveFitness[team] ? liveFitness[team][p.id] : null;
    $("pc-fitness").hidden = fitNow == null;
    if (fitNow != null) {
        $("pc-fitness-val").innerText = `${fitNow}%`;
        $("pc-fitness-fill").style.width = `${fitNow}%`;
        $("pc-fitness-fill").style.background = fitNow >= 70 ? "var(--accent-green)" : fitNow >= 55 ? "var(--accent-yellow)" : "var(--accent-red)";
    }
    const keeper = p.pos === "GK";
    const peers = rows.filter(r => r.minutes > 0 && (r.pos === "GK") === keeper);
    $("pc-bars").innerHTML = PC_STATS[keeper ? "keeper" : "outfield"].map(k => {
        const label = ct(`pc_${k}`);
        const vals = peers.map(r => r[k] || 0);
        const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
        const max = Math.max(...vals, p[k] || 0, 1);
        const v = p[k] || 0;
        const fmt = x => k === "top_speed" && !x ? "–" : (k === "distance_km" || k === "top_speed") ? x.toFixed(1) : Math.round(x * 10) / 10;
        return `<div class="pc-row"><div class="pc-row-label"><span>${label}</span><span><strong>${fmt(v)}</strong> <span class="text-muted">${ct("team_avg", { v: fmt(avg) })}</span></span></div>
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
    $("pc-heat-note").innerText = ct("heat_note", { n: pts.length, t: teamName(team) });
}

/* ---------- REPORT CARD ---------- */
function openReport(entry) {
    const r = entry.report;
    if (!r) return;
    reportEntry = entry;
    $("report-title").innerText = tr(r.kind === "HALF_TIME" ? "k_ht" : "k_ft");
    $("report-score").innerHTML = `<span style="color:${TEAM_COLOR[HOME]}">${TEAM_LABEL[HOME].toUpperCase()}</span> <strong>${r.score.home} – ${r.score.away}</strong> <span style="color:${TEAM_COLOR[AWAY]}">${TEAM_LABEL[AWAY].toUpperCase()}</span>`;
    const th = r.teams[HOME], ta = r.teams[AWAY];
    const rows = [["xG", th.xg.toFixed(2), ta.xg.toFixed(2), th.xg, ta.xg], [ct("rs_shots"), th.shots, ta.shots], [ct("rs_on_target"), th.on_target, ta.on_target],
        [ct("rs_possession"), `${th.possession}%`, `${ta.possession}%`, th.possession, ta.possession], [ct("rs_pass"), `${th.pass_pct}%`, `${ta.pass_pct}%`, th.pass_pct, ta.pass_pct],
        [ct("rs_big"), th.big_chances, ta.big_chances], [ct("rs_press"), th.press_wins, ta.press_wins],
        [ct("rs_corners"), th.corners, ta.corners], [ct("rs_fouls"), th.fouls, ta.fouls], [ct("rs_offsides"), th.offsides, ta.offsides],
        [ct("rs_woodwork"), th.woodwork, ta.woodwork], [ct("rs_tilt"), `${th.field_tilt}%`, `${ta.field_tilt}%`, th.field_tilt, ta.field_tilt],
        [ct("rs_cards"), `${th.yellow}${cardIco("YELLOW")} ${th.red}${cardIco("RED")}`, `${ta.yellow}${cardIco("YELLOW")} ${ta.red}${cardIco("RED")}`, th.yellow + 2 * th.red, ta.yellow + 2 * ta.red],
        [ct("rs_distance"), th.distance_km, ta.distance_km]];
    $("report-stats").innerHTML = rows.map(([label, h, a, hn = +h, an = +a]) => {
        const tot = hn + an, hp = tot ? 100 * hn / tot : 50;
        return `<div class="rs-row"><span>${h}</span><div><span class="rs-label">${label}</span>
            <div class="h2h-bar"><div class="h2h-home" style="width:${hp}%"></div><div class="h2h-away" style="width:${100 - hp}%"></div></div></div><span>${a}</span></div>`;
    }).join("");
    $("report-narrative").innerText = r.narrative;
    const b = r.best_player;
    $("report-best").innerHTML = b ? `<span class="rb-label">${esc(ct("best"))}</span> <strong>${esc(b.name)}</strong> <span style="color:${TEAM_COLOR[b.team]}">${TEAM_LABEL[b.team]}</span> <span class="rating r-high">${b.rating.toFixed(1)}</span>` : "";
    const icon = m => m.card && m.restart !== "PENALTY" ? cardIco(m.card) : fa(isGoal(m) ? ICON.GOAL : m.outcome === "DISALLOWED" ? ICON.DISALLOWED
        : m.restart === "PENALTY" ? ICON.PENALTY : m.outcome === "SAVED" ? ICON.SAVED : ICON.MISS);
    $("report-moments").innerHTML = r.key_moments.map(m => `<li>${icon(m)} ${m.clock} ${esc(m.player)} <span class="text-muted">${TEAM_LABEL[m.team]}</span></li>`).join("");
    const checked = entry.reportSource === "AZURE OPENAI" && entry.reportPipeline && entry.reportPipeline.status !== "rejected" ? " · ✓ fact-checked" : "";
    $("report-source").innerText = `${srcLabel(entry.reportSource)}${checked} · ${ct(r.kind === "HALF_TIME" ? "next_half" : "next_match")}`;
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
    $("return-live-text").innerText = live ? ct("live") : `GO LIVE${behind > 0 ? ` · +${behind}` : ""}`;
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
    if (!$("guide").hidden) { if (e.key === "Escape") closeGuide(); return; }
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
        if (isGoal(ev)) { cls = "goal"; label = `Goal ${ev.clock} ${ev.outcome === "OWN_GOAL" ? `${ev.opponent} (o.g.)` : ev.player}`; }
        else if (ev.outcome === "DISALLOWED") { cls = "var"; label = `${ev.clock} ${ev.player}: VAR, no goal`; }
        else if (ev.card) { cls = ev.card === "RED" ? "red" : "yellow"; label = `${ev.card === "RED" ? "Red" : "Yellow"} card ${ev.clock} ${ev.player}`; }
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
const ICON = { GOAL: "futbol", SAVED: "hand", MISS: "crosshairs", BLOCKED: "shield-halved", COMPLETE: "arrow-right",
              INTERCEPTED: "scissors", SUCCESS: "wind", WON: "shield", FOUL: "circle-exclamation", OUT: "arrow-turn-up",
              OFFSIDE: "flag", SUBSTITUTION: "right-left", HALF_TIME: "pause", FULL_TIME: "flag-checkered",
              CORNER: "border-top-left", FREE_KICK: "shoe-prints", THROW_IN: "hands-holding", GOAL_KICK: "arrow-up-long",
              PENALTY: "circle-dot", OWN_GOAL: "futbol", WOODWORK: "grip-lines-vertical", DISALLOWED: "ban", INJURY: "kit-medical" };

/* What kind of shot: penalty, free kick, header, rebound or an ordinary shot. */
const shotKind = ev => tr(ev.set_piece === "PENALTY" ? "pen" : ev.set_piece === "FREE_KICK" ? "fk"
    : ev.body_part === "HEAD" ? "header" : (ev.tags || []).includes("rebound") ? "rebound" : "shot");
/* What kind of pass: a set piece, a cross, a through ball, a long ball or an ordinary pass. */
const passKind = ev => {
    const tags = ev.tags || [];
    if (ev.set_piece) return spName(ev.set_piece).toUpperCase();
    return tr(tags.includes("cross") ? "cross" : tags.includes("through_ball") ? "through" : tags.includes("long_ball") ? "long" : "pass");
};

function logLabel(ev) {
    const kind = passKind(ev) + " ";
    const tags = ev.tags || [];
    switch (ev.event_type) {
        case "PASS":
            if (ev.outcome === "COMPLETE") return `${kind}→ ${ev.receiver}`;
            if (ev.outcome === "OWN_GOAL") return `${kind}· ${tr("own_goal_by", { o: ev.opponent })}`;
            if (ev.outcome === "OUT") return `${kind}${tr("out")}`;
            if (ev.outcome === "OFFSIDE") return tr("offside_log", { r: ev.receiver });
            if (tags.includes("claimed")) return `${kind}${tr("claimed", { o: ev.opponent })}`;
            return kind + tr(ev.restart === "CORNER" ? "behind" : tags.includes("delivery") ? "cleared" : "intercepted", { o: ev.opponent });
        case "DRIBBLE": return tr("dribble");
        case "SHOT":
            if (ev.outcome === "DISALLOWED") return `${shotKind(ev)} · ${tr("disallowed", { why: varWhy(ev) })}`;
            return `${shotKind(ev)} · ${ui().outcome[ev.outcome] || ev.outcome}${ev.var && ev.var.decision === "GOAL_STANDS" ? " (VAR ✓)" : ""}`;
        case "INJURY": return tr("injury_log");
        case "TACKLE": return ev.outcome === "WON" ? tr("tackle_won", { o: ev.opponent })
            : tr(ev.restart === "PENALTY" ? "pen_foul" : "foul", { o: ev.opponent });
        case "SUBSTITUTION": {
            const why = tags.map(x => ui().sub_reason[x]).filter(Boolean)[0];
            return `${tr("sub_log")} ${ev.player} ⇄ ${ev.player_off}${why ? ` (${why})` : ""}`;
        }
        case "HALF_TIME": return tr("half_time");
        case "FULL_TIME": return tr("full_time");
        default: return ev.event_type.replace("_", " ");
    }
}

function logItemHtml(ev) {
    const mine = fav() && ev.team === fav();
    const who = ev.team && ev.event_type !== "SUBSTITUTION"
        ? `<span class="team-tag" style="--tc:${TEAM_COLOR[ev.team]}">${esc(ev.player)}</span> ` : "";
    const name = isGoal(ev) ? ICON.GOAL : ev.restart === "PENALTY" ? ICON.PENALTY
        : ev.set_piece && ev.event_type === "PASS" ? ICON[ev.set_piece] : ICON[ev.outcome || ev.event_type];
    const icon = name ? fa(name) : "";
    const card = ev.card ? ` ${cardIco(ev.card)}` : "";
    const restart = ev.restart ? ` <span class="restart-tag" title="Play restarts with this set piece">${esc(tr("restart", { sp: spName(ev.restart).toLowerCase(), t: TEAM_SHORT[ev.restart_team] }))}</span>` : "";
    const added = ev.added_time ? ` <span class="restart-tag">${fa("stopwatch")} +${ev.added_time}</span>` : "";
    return `<span class="event-time">${esc(ev.clock)}</span><span>${mine ? `<span class="fav-star">${fa("star")}</span> ` : ""}${icon || "•"} ${who}<strong>${esc(logLabel(ev))}</strong>${card}${restart}${added}${ev.possession_change ? ' <span class="poss-chg" title="Possession changed">⇄</span>' : ""}${ev.is_impact_moment ? ` <span class="zap">${fa("bolt")}</span>` : ""}</span>`;
}

function addLogItem(entry) {
    const ev = entry.event;
    const item = document.createElement("div");
    const mine = fav() && ev.team === fav();
    item.className = `event-item clickable new${ev.is_impact_moment ? " impact" : ""}${mine ? " fav" : ""}`;
    item.dataset.seq = ev.seq;
    item.setAttribute("role", "button");
    item.tabIndex = 0;
    item.innerHTML = logItemHtml(ev);
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
    return isGoal(ev) || ev.outcome === "DISALLOWED" || ev.outcome === "WOODWORK" || ev.event_type === "INJURY"
        || ev.card || ev.restart === "PENALTY" || ev.event_type === "SUBSTITUTION" || ev.event_type === "HALF_TIME"
        || ev.event_type === "FULL_TIME" || (ev.event_type === "SHOT" && (ev.metrics.xg >= 0.3 || ev.outcome === "SAVED"
            || ev.set_piece === "PENALTY" || ev.set_piece === "FREE_KICK"));
}

function keyEventText(ev) {
    const how = ev.event_type === "SHOT" && (ev.set_piece || ev.body_part === "HEAD" || (ev.tags || []).includes("rebound"))
        ? `, ${shotKind(ev).toLowerCase()}` : "";
    const xg = ev.metrics.xg != null ? ` (${ev.metrics.xg.toFixed(2)} xG${how})` : "";
    const tn = teamName(ev.team);
    const big = s => `<strong>${s}</strong>`;
    if (ev.outcome === "GOAL") return `${fa(ICON.GOAL)} ${big(tr("goal"))} ${esc(ev.player)}, ${tn}${xg} · ${ev.score.home}-${ev.score.away}${ev.var && ev.var.decision === "GOAL_STANDS" ? " · VAR ✓" : ""}`;
    if (ev.outcome === "OWN_GOAL") return `${fa(ICON.GOAL)} ${big(tr("own_goal"))} ${esc(tr("k_own_goal", { o: ev.opponent, t: tn }))} · ${ev.score.home}-${ev.score.away}`;
    if (ev.outcome === "DISALLOWED") return `${fa(ICON.DISALLOWED)} ${big(tr("var_no"))} ${esc(ev.player)}, ${tn}: ${varWhy(ev)}`;
    if (ev.outcome === "WOODWORK") return `${fa(ICON.WOODWORK)} ${big(tr("k_woodwork"))} ${esc(ev.player)}, ${tn}${xg}`;
    if (ev.event_type === "INJURY") return `${fa(ICON.INJURY)} ${big(tr("injury"))} ${esc(ev.player)}, ${tn}`;
    if (ev.restart === "PENALTY") return `${fa(ICON.PENALTY)} ${esc(tr("k_penalty", { t: teamName(ev.restart_team), o: ev.opponent, p: ev.player }))}${ev.card ? ` ${cardIco(ev.card)}` : ""}`;
    if (ev.card) return `${cardIco(ev.card)} ${big(tr(ev.card === "RED" ? "red" : "yellow"))} ${esc(tr("k_card", { p: ev.player, t: tn, o: ev.opponent }))}`;
    if (ev.event_type === "SUBSTITUTION") {
        const why = (ev.tags || []).map(x => ui().sub_reason[x]).filter(Boolean)[0];
        return `${fa(ICON.SUBSTITUTION)} ${big(tr("sub_log"))} ${esc(tr("k_sub", { t: tn, p: ev.player, o: ev.player_off }))}${why ? ` (${why})` : ""}`;
    }
    if (ev.event_type === "HALF_TIME") return `${fa(ICON.HALF_TIME)} ${big(tr("k_ht"))} ${teamName(HOME)} ${ev.score.home}-${ev.score.away} ${teamName(AWAY)}`;
    if (ev.event_type === "FULL_TIME") return `${fa(ICON.FULL_TIME)} ${big(tr("k_ft"))} ${teamName(HOME)} ${ev.score.home}-${ev.score.away} ${teamName(AWAY)}`;
    if (ev.outcome === "SAVED") return `${fa(ICON.SAVED)} ${big(tr(ev.set_piece === "PENALTY" ? "k_pen_saved" : "k_save"))} ${esc(tr("k_denies", { o: ev.opponent, p: ev.player }))}${xg}`;
    const label = tr(ev.set_piece === "PENALTY" ? "k_pen_missed" : ev.set_piece === "FREE_KICK" ? "fk" : "k_big");
    return `${fa(ICON.MISS)} ${big(label)} ${esc(ev.player)}, ${tn}${xg}: ${(ui().outcome[ev.outcome] || ev.outcome).toLowerCase()}`;
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
    li.innerHTML = `<div class="ke-top">${keTopHtml(entry)}</div><p class="story"></p>`;
    $("key-events-list").prepend(li);
    updateKeyEventStory(entry);
}

function keTopHtml(entry) {
    const ev = entry.event;
    return `<span class="time-tag">${esc(ev.clock)}</span> ${keyEventText(ev)}
        ${entry.report ? `<button class="chip open-report">${esc(ct("open_report"))}</button>` : ""}
        <span class="replay-hint"><i class="fa-solid fa-rotate-left"></i> replay</span>`;
}

function updateKeyEventStory(entry) {
    const li = document.querySelector(`#key-events-list li[data-seq="${entry.event.seq}"]`);
    if (!li) return;
    const p = li.querySelector(".story");
    const text = keyEventStory(entry);
    const src = entry.report ? entry.reportSource : entry.storySource;
    const checked = src === "AZURE OPENAI" ? verifiedTag(entry.report ? entry.reportPipeline : entry.storyPipeline) : "";
    p.innerHTML = text ? `${esc(text)} <span class="ai-source ${src === "AZURE OPENAI" ? "from-azure" : ""}">${srcLabel(src)}</span>${checked}` : "";
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
    ["Expected assists (xA)", s => s.xa, v => v.toFixed(2)], ["Big chances missed", s => s.big_chances_missed],
    ["Woodwork", s => s.woodwork], ["Field tilt", s => s.field_tilt, v => `${v}%`],
    ["Crosses (completed)", s => s.crosses_completed], ["Long balls (completed)", s => s.long_balls_completed],
    ["Progressive passes", s => s.progressive_passes], ["Aerial duels won", s => s.aerials_won],
    ["Clearances", s => s.clearances], ["Blocks", s => s.blocks],
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
    ["num", "#"], ["name", "Player"], ["pos", "Pos"], ["minutes", "Min"], ["fitness", "Est. fit."], ["rating", "Rating"],
    ["goals", "G"], ["assists", "A"], ["shots", "Shots (OT)"], ["xg", "xG"], ["xa", "xA"], ["passes", "Passes"],
    ["key_passes", "Key P."], ["dribbles_won", "Dribbles"], ["tackles_won", "Tackles"],
    ["interceptions", "Int."], ["aerials_won", "Aerials"], ["clearances", "Clr."], ["blocks", "Blk."],
    ["saves", "Saves"], ["fouls", "Fouls"], ["fouls_won", "Fouled"], ["offsides", "Off."], ["cards", "Cards"],
    ["touches", "Touches"], ["sprints", "Sprints"], ["distance_km", "Dist. km"], ["top_speed", "Top km/h"],
];
const COL_TITLE = {
    minutes: "Minutes played", rating: "Match rating (starts at 6.0)", goals: "Goals", assists: "Assists",
    shots: "Shots (on target)", passes: "Completed / attempted passes", key_passes: "Passes that led to a shot",
    dribbles_won: "Successful / attempted dribbles", tackles_won: "Tackles won / attempted",
    interceptions: "Interceptions", touches: "Touches of the ball", fouls: "Fouls committed",
    fitness: "Estimated fitness (100 = fresh). Our estimate, not a measurement: it starts at 100 and drops with minutes played and sprints, faster for players with a low stamina rating.",
    xa: "Expected assists: xG of the shots this player set up", aerials_won: "Aerial duels won",
    clearances: "Clearances", blocks: "Shots blocked",
    fouls_won: "Times fouled (free kicks or penalties won)", offsides: "Caught offside", sprints: "Sprints and runs in behind",
    distance_km: "Estimated distance covered", top_speed: "Fastest sprint recorded",
};

function renderPlayerTable() {
    if (!liveStats) return;
    const fit = liveFitness && liveFitness[statsTeam] || {};
    let rows = liveStats.players[statsTeam].map(r => ({ ...r, fitness: fit[r.id] ?? null }));
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
        const offTxt = r.sub_off != null ? ` <span class="sub-off">${r.red ? cardIco("RED") : "↓"}${r.sub_off}'</span>` : "";
        const cards = cardIco("YELLOW").repeat(r.yellow) + cardIco("RED").repeat(r.red) || "–";
        return `<tr class="${r.minutes === 0 && r.sub_on == null && !r.starter ? "bench" : ""}${focus ? " focus" : ""}" data-pid="${esc(r.id)}">
            <td class="num">${r.num}</td><td class="pname">${esc(r.name)}${squads && squads[statsTeam][r.id]?.captain ? ' <span class="capt" title="Captain">C</span>' : ""}${subTxt}${offTxt}</td><td>${r.pos}</td>
            <td>${r.minutes}</td><td>${r.fitness != null ? `${r.fitness}%` : "–"}</td><td><span class="rating ${ratingCls(r.rating)}">${r.rating != null ? r.rating.toFixed(1) : "–"}</span></td>
            <td>${r.goals || "–"}</td><td>${r.assists || "–"}</td><td>${r.shots} (${r.on_target})</td><td>${r.xg.toFixed(2)}</td><td>${r.xa.toFixed(2)}</td>
            <td>${r.passes_completed}/${r.passes}</td><td>${r.key_passes}</td><td>${r.dribbles_won}/${r.dribbles}</td>
            <td>${r.tackles_won}/${r.tackles}</td><td>${r.interceptions}</td><td>${r.aerials_won}/${r.aerials}</td>
            <td>${r.clearances}</td><td>${r.blocks}</td><td>${r.saves}</td><td>${r.fouls}</td>
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
        pts.push([chartMin(e.event), e.summary.xg[0], e.summary.xg[1]]);
        if (isGoal(e.event)) goals.push([chartMin(e.event), e.event.team, e.summary.xg[e.event.team === HOME ? 0 : 1],
            e.event.outcome === "OWN_GOAL" ? `${e.event.opponent} (o.g.)` : e.event.player]);
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
        goals.map(([mn, t, v, p]) => `<circle cx="${sx(mn)}" cy="${sy(v)}" r="5" fill="${TEAM_COLOR[t]}" stroke="#111827" stroke-width="2" data-tip="Goal ${mn.toFixed(0)}' ${esc(p)} (${TEAM_LABEL[t]})"/>`).join("") +
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
        const b = Math.min(29, Math.floor(chartMin(e.event) / 3));
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
        const b = Math.min(44, Math.floor(chartMin(e.event) / 2));
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
    const line = team => entries.map((e, i) => `${i ? "L" : "M"}${sx(chartMin(e.event)).toFixed(1)},${sy(e.summary.flow.press[team]).toFixed(1)}`).join(" ");
    if (entries.length > 1) {
        out += `<path d="${line(HOME)}" class="xg-line" stroke="${TEAM_COLOR[HOME]}"/><path d="${line(AWAY)}" class="xg-line" stroke="${TEAM_COLOR[AWAY]}"/>`;
        const lf = entries[entries.length - 1].summary.flow.press;
        const ly = [sy(lf[HOME]), sy(lf[AWAY])];
        if (Math.abs(ly[0] - ly[1]) < 13) { const mid = (ly[0] + ly[1]) / 2; ly[0] = mid + (lf[HOME] >= lf[AWAY] ? -7 : 7); ly[1] = mid + (lf[HOME] >= lf[AWAY] ? 7 : -7); }
        const lx = sx(chartMin(entries[entries.length - 1].event)) + 8;
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
            <span class="reason">${ev.impact_reasons.map(reasonName).join(" · ")}</span>
            <span class="src ${e.commentary.source === "AZURE OPENAI" ? "from-azure" : ""}">${e.commentary.source === "AZURE OPENAI" ? "AI" : "instant"}</span>
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
    "set_piece", "restart", "restart_team", "body_part", "period", "tags", "var_decision", "var_reason", "added_time",
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
        const flat = { ...ev, ...ev.metrics, ...ev.location, impact_reasons: ev.impact_reasons.join("|"), score_home: ev.score.home, score_away: ev.score.away,
            tags: (ev.tags || []).join("|"), var_decision: ev.var ? ev.var.decision : null, var_reason: ev.var ? ev.var.reason : null };
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
const tipTarget = e => {
    const el = e.target.closest && e.target.closest("[data-tip]");
    return el && (el.closest("svg") || el.classList.contains("info")) ? el : null;
};
document.addEventListener("mouseover", e => { const el = tipTarget(e); if (el) tooltip(e, esc(el.dataset.tip)); });
document.addEventListener("mousemove", e => { const el = tipTarget(e); if (el) tooltip(e, esc(el.dataset.tip)); });
document.addEventListener("mouseout", e => { if (e.target.closest && e.target.closest("[data-tip]")) hideTooltip(); });

/* ---------- TABS ---------- */
function renderActiveTab() {
    if (activeTab === "stats") renderStats();
    else if (activeTab === "tactics") renderTactics();
    else if (activeTab === "analysis") renderAnalysis();
    else if (activeTab === "data") renderData();
    else if (activeTab === "agents") renderAgents();
}
document.querySelectorAll(".drawer-tab-btn").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll(".drawer-tab-btn").forEach(b => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    activeTab = btn.dataset.tab;
    $(`panel-${activeTab}`).classList.add("active");
    renderActiveTab();
}));

/* ---------- TALK TO AI ---------- */
/* `hint` is the English question behind a suggestion, for the local engine when the model is off. */
function ask(question, hint) {
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
    qa.innerHTML = `<p class="q">${esc(question)}</p><p class="a text-muted">${esc(ct("thinking"))}</p>`;
    box.prepend(qa);
    while (box.children.length > 6) box.lastChild.remove();
    ws.send(JSON.stringify({ type: "ask", id, question, hint }));
    $("ai-query-input").value = "";
}
$("ai-query-send-btn").addEventListener("click", () => ask($("ai-query-input").value));
$("ai-query-input").addEventListener("keydown", e => { if (e.key === "Enter") ask(e.target.value); });
$("ai-suggestions").addEventListener("click", e => { const c = e.target.closest(".chip"); if (c) ask(c.innerText, c.dataset.q); });

/* Two suggestions follow the viewer and the match: the player they follow in Player Cam, and the
 * latest report once there is one (before half-time there is none to ask for). */
function updateSuggestions() {
    const followed = settings.mode === "PLAYER_CAM" && settings.player;
    const q = (el, key, vars) => { el.innerText = ct(key, vars); el.dataset.q = CHROME.en[key].replace("{p}", vars ? vars.p : ""); };
    q($("ask-player"), followed ? "q_player" : "q_best", { p: settings.player });
    const done = matchEntries().map(e => e.event.event_type);
    q($("ask-story"), done.includes("FULL_TIME") ? "q_ft" : done.includes("HALF_TIME") ? "q_ht" : "q_sofar");
}

function onAnswer(msg) {
    const qa = document.querySelector(`.qa[data-id="${msg.id}"] .a`);
    if (!qa) return;
    qa.classList.remove("text-muted");
    qa.innerHTML = `${esc(msg.text)} <span class="ai-source ${msg.source === "AZURE OPENAI" ? "from-azure" : ""}">${srcLabel(msg.source)}</span>${msg.source === "AZURE OPENAI" ? verifiedTag(msg.pipeline) : ""}`
        + (msg.pipeline && msg.source === "AZURE OPENAI" ? `<div class="agent-trail">${trailHtml(msg.pipeline)}</div>` : "");
}

/* ---------- RECAPS AND CATCH-UP ---------- */
let awayFrom = null, catchId = 0, catchTimer = null;
let recaps = new Map();  // seq -> {clock, local: {lang: text}, ai: {lang: {text, pipeline}}}
const lastSeq = () => (history.length ? history[history.length - 1].event.seq : 0);

/* A recap every quarter of an hour, in Key Events & Stories; the agents' version replaces the template. */
function onRecap(msg) {
    const key = `${connId}:${msg.match_id}`;
    if (key !== matchKey) return;
    const rec = recaps.get(msg.seq) || { clock: msg.clock, local: {}, ai: {} };
    recaps.set(msg.seq, rec);
    if (msg.source === "AZURE OPENAI") rec.ai[msg.lang] = { text: msg.text, pipeline: msg.pipeline };
    else rec.local = msg.i18n || { ...rec.local, [msg.lang]: msg.text };
    let li = document.querySelector(`#key-events-list li[data-recap="${msg.seq}"]`);
    const fresh = !li;
    if (fresh) {
        li = document.createElement("li");
        li.className = "ke neutral recap";
        li.dataset.recap = msg.seq;
        $("key-events-list").prepend(li);
    }
    renderRecap(li, rec);
    if (fresh && live) showToasts({ alerts: [{ kind: "milestone", key: "recap", text: `${msg.clock} recap in Key Events & Stories` }] });
}

/* A recap in the language on screen: the agents' version if they wrote one in it, else the template. */
function renderRecap(li, rec) {
    const ai = rec.ai[settings.lang];
    const text = ai ? ai.text : rec.local[settings.lang] || Object.values(rec.local)[0] || "";
    const src = ai ? "AZURE OPENAI" : "LOCAL ENGINE";
    li.innerHTML = `<div class="ke-top"><span class="time-tag">${esc(rec.clock)}</span> ${fa("newspaper")} <strong>${esc(tr("k_recap"))}</strong></div>
        <p class="story">${esc(text)} <span class="ai-source ${ai ? "from-azure" : ""}">${srcLabel(src)}</span>${ai ? verifiedTag(ai.pipeline) : ""}</p>`;
}

function requestCatchup(since) {
    catchId += 1;
    $("catchup-text").innerText = "Catching you up…";
    $("catchup-source").innerText = "";
    $("catchup-span").innerText = "";
    $("catchup").hidden = false;
    ws.send(JSON.stringify({ type: "catchup", id: catchId, since_seq: since }));
}

function onCatchup(msg) {
    if (msg.id !== catchId) return;
    const ai = msg.source === "AZURE OPENAI";
    $("catchup-span").innerText = `${msg.start} to ${msg.end}`;
    $("catchup-text").innerText = msg.text;
    $("catchup-source").innerHTML = `<span class="${ai ? "from-azure" : ""}">${srcLabel(msg.source)}</span>${ai ? verifiedTag(msg.pipeline) : ""}`;
    $("catchup").hidden = false;
    clearTimeout(catchTimer);
    catchTimer = setTimeout(() => { $("catchup").hidden = true; }, 30000);
}
$("catchup-close").addEventListener("click", () => { $("catchup").hidden = true; clearTimeout(catchTimer); });

/* ---------- SOCKET MESSAGES ---------- */
function resetMatch(key) {
    matchKey = key;
    liveStats = null;
    $("event-log-container").innerHTML = "";
    $("key-events-list").innerHTML = "";
    recaps = new Map();
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
    const entry = { key, event: msg.event, positions: msg.positions, possession: msg.possession, ball: msg.ball,
                    commentary: msg.commentary, summary: msg.summary, alerts: msg.alerts || [],
                    story: msg.story, report: msg.report, overlays: msg.overlays || [],
                    local: msg.i18n || { [msg.commentary.lang]: { commentary: msg.commentary, story: msg.story,
                                                                   report_narrative: msg.report && msg.report.narrative } },
                    ai: {} };
    history.push(entry);
    if (history.length > MAX_HISTORY) { history.shift(); idx = Math.max(0, idx - 1); }
    liveStats = msg.stats;
    liveFitness = msg.fitness || null;
    liveStance = msg.stance || null;
    liveSubs = msg.subs_used || null;
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

/* ---------- LANGUAGE ----------
 * Every event carries its template text in each language (entry.local) and keeps the agents' text per
 * language (entry.ai). The fields the page reads are filled for the language on screen, so switching
 * language rewrites the whole match so far, and switching back brings the agents' text back. */
function useLang(entry, lang = settings.lang) {
    const local = entry.local[lang] || entry.local[Object.keys(entry.local)[0]];
    const ai = entry.ai[lang] || {};
    entry.commentary = ai.commentary || local.commentary;
    entry.pipeline = ai.commentary ? ai.pipeline : null;
    entry.story = ai.story || local.story || null;
    entry.storySource = ai.story ? "AZURE OPENAI" : "LOCAL ENGINE";
    entry.storyPipeline = ai.story ? ai.storyPipeline : null;
    if (entry.report) {
        entry.report.narrative = ai.report || local.report_narrative;
        entry.reportSource = ai.report ? "AZURE OPENAI" : "LOCAL ENGINE";
        entry.reportPipeline = ai.report ? ai.reportPipeline : null;
    }
}
const aiText = (entry, lang) => (entry.ai[lang] = entry.ai[lang] || {});

/* The language changed: rewrite the event log, key events, recaps, the card and the open tab. */
function switchMatchLanguage() {
    const entries = matchEntries();
    entries.forEach(e => useLang(e));
    const bySeq = new Map(entries.map(e => [e.event.seq, e]));
    for (const item of Array.from($("event-log-container").children)) {
        const e = bySeq.get(+item.dataset.seq);
        if (e) item.innerHTML = logItemHtml(e.event);
    }
    for (const li of Array.from($("key-events-list").children)) {
        if (li.dataset.recap) { const rec = recaps.get(+li.dataset.recap); if (rec) renderRecap(li, rec); continue; }
        const e = bySeq.get(+li.dataset.seq);
        if (e) { li.querySelector(".ke-top").innerHTML = keTopHtml(e); updateKeyEventStory(e); }
    }
    if (anim.entry) showCommentary(cardEntry());
    if (reportEntry) openReport(reportEntry);
    renderActiveTab();
}

function onCommentary(msg) {
    const entry = findEntry(msg);
    if (!entry) return;
    const lang = msg.commentary.lang || settings.lang;
    const fromAi = msg.commentary.source === "AZURE OPENAI";
    if (fromAi) Object.assign(aiText(entry, lang), { commentary: msg.commentary, pipeline: msg.pipeline });
    else {  // the latest event again, for a new language, focus player or club
        const local = entry.local[lang] = entry.local[lang] || {};
        local.commentary = msg.commentary;
        if ("story" in msg) local.story = msg.story;
        if (msg.report_narrative) local.report_narrative = msg.report_narrative;
    }
    if (msg.alerts && lang === settings.lang) entry.alerts = msg.alerts;
    if (lang !== settings.lang) return;  // kept for when the viewer switches back
    useLang(entry);
    updateKeyEventStory(entry);
    const recent = history.length - 1 - history.indexOf(entry) <= 6;
    if (fromAi && live && recent) {
        // the agents take a few seconds: keep their line on the card long enough to read
        aiHold = { entry, until: performance.now() + 7000 / Math.sqrt(settings.speed) };
        showCommentary(entry, true);
    } else if (entry === anim.entry) showCommentary(entry, fromAi);
    if (reportEntry === entry) openReport(entry);
    if (activeTab === "analysis") { renderImpactList(); renderReports(); }
}

function onStory(msg) {
    const entry = findEntry(msg);
    if (!entry) return;
    const lang = msg.lang || settings.lang;
    Object.assign(aiText(entry, lang), { story: msg.story, storyPipeline: msg.pipeline });
    if (lang !== settings.lang) return;
    useLang(entry);
    updateKeyEventStory(entry);
}

function onReport(msg) {
    const entry = findEntry(msg);
    if (!entry || !entry.report) return;
    const lang = msg.lang || settings.lang;
    Object.assign(aiText(entry, lang), { report: msg.narrative, reportPipeline: msg.pipeline });
    if (lang !== settings.lang) return;
    useLang(entry);
    updateKeyEventStory(entry);
    if (reportEntry === entry) openReport(entry);
    if (activeTab === "analysis") renderReports();
}

const RUN_KIND = { commentary: `${fa("bolt")} Impact moment`, story: `${fa("book-open")} Key-event story`, report: `${fa("pause")} Report`,
                   answer: `${fa("comments")} Question`, recap: `${fa("newspaper")} Recap`, catchup: `${fa("backward")} Catch-up` };
const RUN_STATUS = { passed: `${fa("circle-check")} verified`, revised: `${fa("rotate-left")} revised, then verified`,
                     rejected: `${fa("circle-xmark")} rejected: templates kept`, error: `${fa("triangle-exclamation")} fell back to templates` };

function onAgentRun(msg) {
    agentRuns.unshift({ kind: msg.kind, clock: msg.clock, seq: msg.seq, p: msg.pipeline });
    agentRuns.length = Math.min(agentRuns.length, 60);
    if (activeTab === "agents") renderAgents();
}

function renderAgents() {
    const n = agentRuns.length, by = s => agentRuns.filter(r => r.p.status === s).length;
    const ms = n ? Math.round(agentRuns.reduce((a, r) => a + r.p.ms, 0) / n) : 0;
    const tools = agentRuns.reduce((a, r) => a + (r.p.tools || []).length, 0);
    const stat = (v, l, t) => `<div title="${t}"><strong>${v}</strong><span>${l}</span></div>`;
    $("agent-stats").innerHTML = stat(n, "runs", "Agent pipeline runs this session")
        + stat(by("passed"), "verified first time", "The fact-checker passed the first draft")
        + stat(by("revised"), "fixed on revision", "The fact-checker sent a draft back and the fixed version passed")
        + stat(by("rejected") + by("error"), "kept templates", "Rejected twice, timed out or failed: the instant template text stayed on screen")
        + stat(n ? `${(ms / 1000).toFixed(1)}s` : "—", "average run", "From the moment to verified text")
        + stat(tools, "tool calls", "Times an agent fetched live stats with a tool");
    $("agent-engine").innerHTML = aiEngine ? `Built with <strong>Microsoft Agent Framework</strong> · running on <strong>Microsoft Foundry</strong> (${esc(aiEngine)}).`
        : aiEngine === undefined ? "Built with <strong>Microsoft Agent Framework</strong> on <strong>Microsoft Foundry</strong>. Connects when the match starts."
        : "The agents are off: no Microsoft Foundry keys are set, so everything comes from the instant template engine.";
    $("agent-count").innerText = `${n} run${n === 1 ? "" : "s"}`;
    $("agent-runs").innerHTML = agentRuns.slice(0, 30).map(r => `<li class="run-${r.p.status}">
        <div class="ar-head"><span class="time-tag">${esc(r.clock)}</span><strong>${RUN_KIND[r.kind] || r.kind}</strong>
            <span class="ar-status">${RUN_STATUS[r.p.status] || r.p.status}</span><span class="text-muted">${(r.p.ms / 1000).toFixed(1)}s</span></div>
        <div class="agent-trail">${trailHtml(r.p)}</div>
        ${r.p.steps.filter(s => s.detail && (s.agent !== "Fact-checker" || s.status !== "passed")).map(s => `<div class="ar-detail">${stepIcon(s)} ${esc(s.agent)}: ${esc(s.detail)}</div>`).join("")}
    </li>`).join("") || `<li class="text-muted">${aiEngine === null ? "No runs: the agents need Microsoft Foundry keys." : "Start the match: runs appear here at each impact moment, key event and report."}</li>`;
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
    aiEngine = msg.ai_configured ? msg.deployment : null;
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
        else if (msg.type === "agent_run") onAgentRun(msg);
        else if (msg.type === "recap") onRecap(msg);
        else if (msg.type === "catchup") onCatchup(msg);
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
    switchMatchLanguage();
    applyChrome();
    applyFav();
    sendConfig();
});

function applyFav() {
    for (const t of TEAMS) $(`team-col-${t}`).classList.toggle("fav", fav() === t);
    // moments already on screen follow the new club too, not only the ones still to come
    const bySeq = new Map(matchEntries().map(e => [e.event.seq, e]));
    for (const el of [...Array.from($("key-events-list").children), ...Array.from($("event-log-container").children)]) {
        const e = bySeq.get(+el.dataset.seq);
        if (!e) continue;
        el.classList.toggle("fav", !!fav() && e.event.team === fav());
        if (el.classList.contains("event-item")) el.innerHTML = logItemHtml(e.event);  // the ★
    }
    // the filter needs a club: without one it would hide every club's moments
    const box = $("ke-fav-only");
    box.disabled = !fav();
    if (!fav()) { box.checked = false; $("key-events-list").classList.remove("fav-only"); }
    $("ke-fav-label").innerText = fav() ? ct("fav_only", { t: teamName(fav()) }) : ct("fav_any");
    $("ke-fav-toggle").title = fav() ? "Hide the other club's moments; recaps and reports stay"
        : "Pick your club with ★ at the top first";
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
        opt.innerText = `${p.num}. ${p.name} (${p.pos})${p.captain ? " · captain" : ""}${p.starter ? "" : " · bench"}`;
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
    if (anim.entry) showCommentary(cardEntry());  // all three personas are already here: switch instantly
    renderModePanel();
    sendConfig();
}
document.querySelectorAll(".mode-btn").forEach(btn => btn.addEventListener("click", () => setMode(btn.dataset.mode)));

/* ---------- GUIDE ---------- */
function openGuide() {
    $("guide").hidden = false;
    $("guide").querySelector(".guide-card").scrollTop = 0;
    $("guide-ok").focus({ preventScroll: true });
}
function closeGuide() {
    $("guide").hidden = true;
    try { localStorage.setItem("secondtouch-guide-seen", "1"); } catch (e) { /* storage blocked: it just shows again next time */ }
}
$("guide-btn").addEventListener("click", openGuide);
$("guide-close").addEventListener("click", closeGuide);
$("guide-ok").addEventListener("click", closeGuide);
$("guide").addEventListener("click", e => { if (e.target === $("guide")) closeGuide(); });
function guideSeen() {
    try { return localStorage.getItem("secondtouch-guide-seen") === "1"; } catch (e) { return false; }
}

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
applyChrome();
applyFav();
if (!guideSeen()) openGuide();
window.addEventListener("resize", resize);
// tell the server when the tab is hidden, so the AI pauses instead of writing for nobody
document.addEventListener("visibilitychange", () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "config", visible: !document.hidden }));
    if (document.hidden) { awayFrom = { seq: lastSeq(), key: matchKey }; return; }
    // back after missing part of the match: ask for a catch-up
    if (awayFrom && awayFrom.key === matchKey && live && lastSeq() - awayFrom.seq >= 6) requestCatchup(awayFrom.seq);
    awayFrom = null;
});
/* Scrollbars stay hidden until used: mark whatever is scrolling for a moment so its thumb shows. */
const scrollTimers = new WeakMap();
document.addEventListener("scroll", e => {
    const el = e.target === document ? document.documentElement : e.target;
    if (!el.classList) return;
    el.classList.add("is-scrolling");
    clearTimeout(scrollTimers.get(el));
    scrollTimers.set(el, setTimeout(() => el.classList.remove("is-scrolling"), 900));
}, true);
// the pitch also changes size when the layout around it does (sidebar, header wrapping), not only the window
if (window.ResizeObserver) new window.ResizeObserver(resize).observe(canvas.parentElement);
resize();
requestAnimationFrame(frame);
