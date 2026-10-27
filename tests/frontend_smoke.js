// Frontend smoke test: runs frontend/app.js against recorded server messages with a stand-in DOM and
// fails on any runtime error in the render paths (pitch frames, event log, key events, every mode,
// every tab, charts, report card, replay).
//
//   node tests/frontend_smoke.js frontend/app.js messages.json
//
// tests/test_frontend_smoke.py records a match and runs this when Node.js is installed.
const fs = require("fs");
const vm = require("vm");

/* An object that accepts any property read, write or call, so DOM and canvas calls are no-ops. */
function stub() {
    const store = {};
    const f = function () { return stub(); };
    return new Proxy(f, {
        get(t, p) {
            if (p === Symbol.toPrimitive) return () => 0;
            if (p === "then") return undefined;
            if (p in store) return store[p];
            if (p === "toString" || p === "valueOf") return () => "";
            if (p === "length") return 0;
            if (p === "children") return { length: 0 };
            return stub();
        },
        set(t, p, v) { store[p] = v; return true; },
        apply() { return stub(); },
        construct() { return stub(); },
    });
}

let now = 1000;
const elements = {};
const documentStub = stub();
const g = {
    console, Math, JSON, Date, Object, Array, Set, Map, Number, String, Promise, Symbol, Proxy, Error,
    parseInt, parseFloat, isNaN, Blob: function () {},
    URL: { createObjectURL: () => "", revokeObjectURL: () => {} },
    performance: { now: () => now },
    requestAnimationFrame: () => 0,
    setTimeout: () => 0, clearTimeout: () => {},
    fetch: () => new Promise(() => {}),
    localStorage: { getItem: () => null, setItem: () => {} },
    location: { protocol: "http:", host: "localhost" },
    WebSocket: Object.assign(function () { return stub(); }, { OPEN: 1 }),
    Image: function () { return stub(); },
    window: stub(),
    document: new Proxy({}, {
        get(t, p) {
            if (p === "getElementById") return id => (elements[id] = elements[id] || stub());
            return documentStub[p];
        },
    }),
};
vm.createContext(g);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), g, { filename: "app.js" });

const msgs = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const errors = [];
const run = (label, fn) => {
    try { fn(); } catch (e) { errors.push(`${label}: ${e.stack.split("\n").slice(0, 3).join(" | ")}`); }
};
const HANDLER = { hello: "onHello", match_start: "onMatchStart", event: "onEvent", commentary: "onCommentary",
                  story: "onStory", report: "onReport", answer: "onAnswer", agent_run: "onAgentRun",
                  recap: "onRecap", catchup: "onCatchup" };
let n = 0;
for (const msg of msgs) {
    n++;
    if (!HANDLER[msg.type]) continue;
    const what = msg.event ? `${msg.event.event_type}/${msg.event.outcome}` : msg.type;
    run(`${HANDLER[msg.type]} #${n} ${what}`, () => g[HANDLER[msg.type]](msg));
    if (msg.type !== "event") continue;
    for (const dt of [0, 300, 900, 2000]) { now += dt; run(`frame #${n} ${what}`, () => g.frame(now)); }
    run(`logLabel #${n} ${what}`, () => g.logLabel(msg.event));
    if (g.isKeyEvent(msg.event)) run(`keyEventText #${n} ${what}`, () => g.keyEventText(msg.event));
    if (n % 25 === 0) {
        for (const mode of ["ANALYST", "CASUAL", "PLAYER_CAM"]) run(`setMode ${mode} #${n}`, () => g.setMode(mode));
        for (const tab of ["renderStats", "renderTactics", "renderAnalysis", "renderData"]) run(`${tab} #${n}`, () => g[tab]());
    }
    if (n % 60 === 0) run(`replay #${n}`, () => { g.replayBuildUp(msg.event.seq); g.stepReplay(); g.goLive(); });
}

// the match view in every commentary language: no crash, no untranslated gap
for (const lang of ["es", "ja", "en"]) {
    vm.runInContext(`settings.lang = "${lang}"`, g);
    for (const msg of msgs.filter(m => m.type === "event")) {
        const what = `${lang} ${msg.event.event_type}/${msg.event.outcome}`;
        run(`logLabel ${what}`, () => {
            const texts = [g.logLabel(msg.event)];
            if (g.isKeyEvent(msg.event)) texts.push(g.keyEventText(msg.event));
            if (texts.some(s => s.includes("undefined"))) throw new Error(`untranslated: ${texts.join(" / ")}`);
        });
    }
    run(`frame ${lang}`, () => g.frame(now += 300));
    const goal = vm.runInContext(`tr("goal")`, g);
    if (goal !== { es: "GOL", ja: "ゴール", en: "GOAL" }[lang]) errors.push(`the match view did not switch to ${lang}: ${goal}`);
}

// switching language rewrites what is already on screen, and the agents' text comes back on switching back
run("switch language", () => {
    const entry = vm.runInContext("matchEntries().find(e => e.story)", g);
    if (!entry) throw new Error("no key event with a story");
    entry.ai.en = { story: "Agent story in English." };
    vm.runInContext(`settings.lang = "ja"; switchMatchLanguage()`, g);
    if (entry.story !== (entry.local.ja.story || null) || entry.storySource !== "LOCAL ENGINE") throw new Error(`not Japanese: ${entry.story}`);
    if (entry.commentary.lang !== "ja") throw new Error("the commentary stayed in another language");
    vm.runInContext(`settings.lang = "en"; switchMatchLanguage()`, g);
    if (entry.story !== "Agent story in English." || entry.storySource !== "AZURE OPENAI") throw new Error("the agents' story was lost");
});

run("interface in Japanese", () => {
    vm.runInContext(`settings.lang = "ja"; applyChrome(); settings.lang = "en"; applyChrome()`, g);
    if (vm.runInContext(`ct("live")`, g) !== "LIVE") throw new Error("the interface did not switch back");
    for (const key of Object.keys(vm.runInContext("CHROME.en", g)))
        for (const lang of ["es", "ja"]) if (!vm.runInContext(`CHROME.${lang}`, g)[key]) throw new Error(`${key} missing in ${lang}`);
});

run("stats panels in Japanese", () => {
    vm.runInContext(`settings.lang = "ja"`, g);
    g.renderStats();
    for (const mode of ["ANALYST", "CASUAL"]) g.setMode(mode);
    const get = id => String((elements[id] && elements[id].innerHTML) || "");
    const stats = get("h2h-list"), tele = get("team-telemetry");
    vm.runInContext(`settings.lang = "en"`, g);
    g.renderStats();
    g.setMode("ANALYST");
    if (!stats.includes("ポゼッション") || stats.includes(">Possession<")) throw new Error("match stats stayed in English");
    if (!tele.includes("チームデータ") || / complete /.test(tele)) throw new Error("telemetry stayed in English");
});

run("pick a club mid-match", () => vm.runInContext(`settings.fav_team = AWAY; applyFav(); settings.fav_team = "NONE"; applyFav()`, g));

run("renderAgents", () => g.renderAgents());
run("setMode after AI", () => g.setMode("CASUAL"));

// it must actually have rendered, not just survived
const html = id => String((elements[id] && elements[id].innerHTML) || "");
if (!html("agent-runs").includes("Fact-checker")) errors.push("the agent runs were not rendered");
if (!String(elements["catchup-text"] && elements["catchup-text"].innerText).includes("While you were away")) errors.push("the catch-up was not shown");
if (!html("agent-stats").includes("verified first time")) errors.push("the agent stats were not rendered");
if (!html("h2h-list").includes("Corners")) errors.push("match stats were not rendered");
if (!html("player-table").includes("<tbody>")) errors.push("player table was not rendered");
if (!String(elements["match-clock"] && elements["match-clock"].innerText)) errors.push("clock was not set");

console.log(`messages: ${msgs.length}, errors: ${errors.length}`);
for (const e of [...new Set(errors)].slice(0, 25)) console.log(" -", e);
process.exit(errors.length ? 1 : 0);
