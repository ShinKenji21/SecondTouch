"""Stage 3 - persona router and localization.

Turns one event into the three viewer styles (analyst, casual, player_cam) in
English, Spanish or Japanese. These templates are the instant first render for
every event and the fallback whenever Azure OpenAI is unavailable; the AI text
for impact moments replaces them a moment later.
"""
from analytics import attack_frame, metres, zone_of

TEAM_NAMES = {
    "en": {"Arsenal": "Arsenal", "ManCity": "Man City"},
    "es": {"Arsenal": "Arsenal", "ManCity": "Man City"},
    "ja": {"Arsenal": "アーセナル", "ManCity": "マンチェスター・シティ"},
}
LANG_NAMES = {"en": "English", "es": "Spanish", "ja": "Japanese"}

T = {
    "en": {
        "pressure": {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"},
        "third": {"defensive": "defensive third", "middle": "middle third", "final": "final third"},
        "channel": {"left": "left", "central": "centre", "right": "right"},
        "zone": "the {channel} of the {third}",
        "pass_short": "{p} plays a {len}m pass to {r} ({diff}/100 difficulty, {pr} pressure), recycling possession.",
        "pass_ok": "{p} finds {r} with a {len}m pass ({diff}/100 difficulty, {pr} pressure), gaining {gain}m and bypassing {byp} opponents.",
        "pass_int": "{o} reads {p}'s {len}m pass and intercepts in {zone}; difficulty was {diff}/100 under {pr} pressure.",
        "drib": "{p} carries {len}m at {spd} km/h through {zone}, nearest defender {nd}m away.",
        "tackle_won": "{p} wins the ball from {o} in {zone} (pressure index {pi}).",
        "foul": "{p} fouls {o} in {zone}.",
        "card_y": " Yellow card.", "card_r": " Red card, {t} are down to ten.",
        "shot": "{p} shoots from {len}m: {xg} xG under {pr} pressure. {res}",
        "res": {"GOAL": "Scored, {score}.", "SAVED": "Saved by {o}.", "MISS": "Off target.", "BLOCKED": "Blocked by {o}."},
        "why_line": " Why it matters: {byp} defenders are taken out and {r} can run at the back line.",
        "why_press": " Why it matters: {ot}'s press forced the turnover {gd}m from goal.",
        "why_big": " Why it matters: a {pct}% chance, one of the clearest of the match.",
        "why_shot": " Why it matters: {t} are now on {txg} xG for the match (shots: {ts}).",
        "sub": "{t} change: {p} on for {o} ({min}').",
        "ht": "Half-time: {score}. xG {xg}.", "ft": "Full-time: {score}. xG {xg}.",
        "c_pass_lb": "WHAT A BALL from {p}! {r} is through!", "c_pass_good": "Lovely pass from {p} to {r}.",
        "c_pass": "{p} keeps it moving to {r}.", "c_int": "{o} reads it and steals the ball!",
        "c_drib": "{p} drives forward!", "c_drib_hp": "{p} wriggles free of a tight marker!",
        "c_tackle": "Great tackle by {p}!", "c_foul": "{p} brings down {o}.",
        "c_card_y": " Into the book!", "c_card_r": " RED CARD!",
        "c_res": {"GOAL": "GOAL! {p} scores! {score}", "SAVED": "Big save from {o}!",
                  "MISS": "{p} fires wide!", "BLOCKED": "Blocked by {o}!"},
        "c_mom": " {t} are all over them right now!",
        "on_ball": "On the ball: ", "stat_line": " ({touches} touches, {sprints} sprints, {pc}/{pa} passes)",
        "off_ball": "{fp}: {d}m from the ball, in {zone}. {touches} touches, {sprints} sprints, rating {rating}.",
        "not_on": "{fp} is not on the pitch.",
    },
    "es": {
        "pressure": {"LOW": "baja", "MEDIUM": "media", "HIGH": "alta"},
        "third": {"defensive": "tercio defensivo", "middle": "tercio medio", "final": "último tercio"},
        "channel": {"left": "la izquierda", "central": "el centro", "right": "la derecha"},
        "zone": "{channel} del {third}",
        "pass_short": "{p} juega un pase de {len} m a {r} (dificultad {diff}/100, presión {pr}) para mantener la posesión.",
        "pass_ok": "{p} encuentra a {r} con un pase de {len} m (dificultad {diff}/100, presión {pr}), gana {gain} m y supera a {byp} rivales.",
        "pass_int": "{o} lee el pase de {len} m de {p} y lo intercepta en {zone}; dificultad {diff}/100 con presión {pr}.",
        "drib": "{p} conduce {len} m a {spd} km/h por {zone}, con el defensor más cercano a {nd} m.",
        "tackle_won": "{p} le roba el balón a {o} en {zone} (índice de presión {pi}).",
        "foul": "Falta de {p} sobre {o} en {zone}.",
        "card_y": " Tarjeta amarilla.", "card_r": " Tarjeta roja: {t} se queda con diez.",
        "shot": "{p} dispara desde {len} m: {xg} xG con presión {pr}. {res}",
        "res": {"GOAL": "¡Gol! {score}.", "SAVED": "Lo para {o}.", "MISS": "Se va fuera.", "BLOCKED": "Lo bloquea {o}."},
        "why_line": " Por qué importa: deja atrás a {byp} rivales y {r} puede encarar a la defensa.",
        "why_press": " Por qué importa: la presión de {ot} provoca la pérdida a {gd} m de la portería.",
        "why_big": " Por qué importa: una ocasión del {pct}%, de las más claras del partido.",
        "why_shot": " Por qué importa: {t} suma {txg} xG en {ts} disparos.",
        "sub": "Cambio en {t}: entra {p} por {o} ({min}').",
        "ht": "Descanso: {score}. xG {xg}.", "ft": "Final: {score}. xG {xg}.",
        "c_pass_lb": "¡QUÉ PASE de {p}! ¡{r} se queda solo!", "c_pass_good": "Buen pase de {p} para {r}.",
        "c_pass": "{p} mueve el balón hacia {r}.", "c_int": "¡{o} lo lee y roba el balón!",
        "c_drib": "¡{p} arranca hacia adelante!", "c_drib_hp": "¡{p} se escapa de la marca!",
        "c_tackle": "¡Gran entrada de {p}!", "c_foul": "{p} derriba a {o}.",
        "c_card_y": " ¡Amarilla!", "c_card_r": " ¡ROJA!",
        "c_res": {"GOAL": "¡GOOOL! ¡Marca {p}! {score}", "SAVED": "¡Paradón de {o}!",
                  "MISS": "¡{p} la manda fuera!", "BLOCKED": "¡Lo bloquea {o}!"},
        "c_mom": " ¡{t} aprieta ahora mismo!",
        "on_ball": "Con el balón: ", "stat_line": " ({touches} toques, {sprints} sprints, {pc}/{pa} pases)",
        "off_ball": "{fp}: a {d} m del balón, en {zone}. {touches} toques, {sprints} sprints, nota {rating}.",
        "not_on": "{fp} no está en el campo.",
    },
    "ja": {
        "pressure": {"LOW": "低", "MEDIUM": "中", "HIGH": "高"},
        "third": {"defensive": "自陣", "middle": "中盤", "final": "ファイナルサード"},
        "channel": {"left": "左", "central": "中央", "right": "右"},
        "zone": "{third}の{channel}",
        "pass_short": "{p}が{len}mのパスで{r}へつなぐ（難易度{diff}/100、プレッシャー{pr}）。ポゼッションを維持。",
        "pass_ok": "{p}が{len}mのパスで{r}へ（難易度{diff}/100、プレッシャー{pr}）。{gain}m前進し、{byp}人を突破。",
        "pass_int": "{o}が{p}の{len}mのパスを{zone}でインターセプト。難易度{diff}/100、プレッシャー{pr}。",
        "drib": "{p}が{zone}を{len}mドリブル（時速{spd}km）。最も近い守備者まで{nd}m。",
        "tackle_won": "{p}が{zone}で{o}からボールを奪取（プレッシャー指数{pi}）。",
        "foul": "{p}が{zone}で{o}にファウル。",
        "card_y": "イエローカード。", "card_r": "レッドカード、{t}は10人に。",
        "shot": "{p}が{len}mからシュート：xG {xg}、プレッシャー{pr}。{res}",
        "res": {"GOAL": "ゴール！{score}。", "SAVED": "{o}がセーブ。", "MISS": "枠外。", "BLOCKED": "{o}がブロック。"},
        "why_line": "なぜ重要か：{byp}人の守備者を置き去りにし、{r}が最終ラインに仕掛けられる。",
        "why_press": "なぜ重要か：{ot}のプレスがゴールまで{gd}mの位置でボールを奪った。",
        "why_big": "なぜ重要か：得点確率{pct}%の決定機だった。",
        "why_shot": "なぜ重要か：{t}は{ts}本のシュートでxG {txg}。",
        "sub": "{t}の交代：{o}に代わり{p}（{min}分）。",
        "ht": "ハーフタイム：{score}。xG {xg}。", "ft": "試合終了：{score}。xG {xg}。",
        "c_pass_lb": "{p}から見事なパス！{r}が抜け出した！", "c_pass_good": "{p}から{r}へ好パス。",
        "c_pass": "{p}が{r}へつなぐ。", "c_int": "{o}が読んでボールを奪った！",
        "c_drib": "{p}が前へ運ぶ！", "c_drib_hp": "{p}がマークを外した！",
        "c_tackle": "{p}の見事なタックル！", "c_foul": "{p}が{o}を倒してしまう。",
        "c_card_y": "イエローカード！", "c_card_r": "レッドカード！",
        "c_res": {"GOAL": "ゴール！{p}が決めた！{score}", "SAVED": "{o}のビッグセーブ！",
                  "MISS": "{p}のシュートは枠外！", "BLOCKED": "{o}がブロック！"},
        "c_mom": "今は{t}の時間帯だ！",
        "on_ball": "ボール保持：", "stat_line": "（タッチ{touches}回、スプリント{sprints}回、パス{pc}/{pa}）",
        "off_ball": "{fp}：ボールまで{d}m、{zone}。タッチ{touches}回、スプリント{sprints}回、評価{rating}。",
        "not_on": "{fp}は現在ピッチにいません。",
    },
}


class Context:
    """Everything beyond the event itself that the personas may mention."""

    def __init__(self, home, away, summary, positions, focus_team, focus_player, focus_line, team_xg_shots):
        self.home, self.away = home, away
        self.summary = summary
        self.positions = positions
        self.focus_team, self.focus_player = focus_team, focus_player
        self.focus_line = focus_line
        self.team_xg_shots = team_xg_shots  # team -> (xg, shots)


def _zone(L, team, home, x, y):
    u, v = attack_frame(team, home, x, y)
    third, channel = zone_of(u, v)
    return L["zone"].format(third=L["third"][third], channel=L["channel"][channel])


def _score(lang, ev, ctx):
    n = TEAM_NAMES[lang]
    return f"{n[ctx.home]} {ev['score']['home']}-{ev['score']['away']} {n[ctx.away]}"


def render(ev, ctx, lang="en"):
    """Return {"analyst", "casual", "player_cam"} for one event."""
    L = T.get(lang, T["en"])
    names = TEAM_NAMES.get(lang, TEAM_NAMES["en"])
    t, o = ev["event_type"], ev["outcome"]
    m, loc = ev["metrics"], ev["location"]

    if t in ("HALF_TIME", "FULL_TIME"):
        xg = f"{ctx.summary['xg'][0]:.2f}-{ctx.summary['xg'][1]:.2f}"
        line = L["ht" if t == "HALF_TIME" else "ft"].format(score=_score(lang, ev, ctx), xg=xg)
        return {"analyst": line, "casual": line, "player_cam": _player_cam(L, ev, ctx, line, lang)}

    team = ev["team"]
    opp_team = ctx.away if team == ctx.home else ctx.home
    f = {
        "p": ev["player"], "r": ev["receiver"], "o": ev["opponent"] or ev["player_off"],
        "t": names[team], "ot": names[opp_team], "len": ev["length_m"],
        "diff": m["pass_difficulty"], "pr": L["pressure"].get(m["pressure"], ""),
        "gain": m["forward_gain_m"], "byp": m["players_bypassed"], "spd": m["sprint_speed_kmh"],
        "nd": m["nearest_defender_m"], "pi": m["pressure_index"],
        "xg": f"{m['xg']:.2f}" if m["xg"] is not None else "", "pct": round((m["xg"] or 0) * 100),
        "zone": _zone(L, team, ctx.home, loc["start_x"], loc["start_y"]),
        "score": _score(lang, ev, ctx), "min": int(ev["minute"]),
    }
    reasons = ev["impact_reasons"]

    if t == "SUBSTITUTION":
        line = L["sub"].format(**f)
        return {"analyst": line, "casual": line, "player_cam": _player_cam(L, ev, ctx, line, lang)}

    if t == "PASS" and o == "COMPLETE":
        forward = (m["forward_gain_m"] or 0) >= 5 and (m["players_bypassed"] or 0) > 0
        analyst = L["pass_ok" if forward else "pass_short"].format(**f)
        if "line_breaking_pass" in reasons:
            analyst += L["why_line"].format(**f)
            casual = L["c_pass_lb"].format(**f)
        else:
            casual = L["c_pass_good" if (m["pass_difficulty"] or 0) >= 60 else "c_pass"].format(**f)
    elif t == "PASS":
        f["zone"] = _zone(L, team, ctx.home, loc["end_x"], loc["end_y"])
        analyst = L["pass_int"].format(**f)
        casual = L["c_int"].format(**f)
        if "high_press_turnover" in reasons:
            f["gd"] = _goal_distance(opp_team, ctx.home, loc["end_x"], loc["end_y"])
            analyst += L["why_press"].format(**f)
    elif t == "DRIBBLE":
        analyst = L["drib"].format(**f)
        casual = L["c_drib_hp" if m["pressure"] == "HIGH" else "c_drib"].format(**f)
    elif t == "TACKLE":
        # the actor is the tackler; describe from their side
        if o == "WON":
            analyst = L["tackle_won"].format(**f)
            casual = L["c_tackle"].format(**f)
            if "high_press_turnover" in reasons:
                f["gd"] = _goal_distance(team, ctx.home, loc["end_x"], loc["end_y"])
                f["ot"] = names[team]
                analyst += L["why_press"].format(**f)
        else:
            analyst = L["foul"].format(**f)
            casual = L["c_foul"].format(**f)
            if ev["card"] == "YELLOW":
                analyst += L["card_y"]; casual += L["c_card_y"]
            elif ev["card"] == "RED":
                analyst += L["card_r"].format(**f); casual += L["c_card_r"]
    else:  # SHOT
        f["res"] = L["res"][o].format(**f)
        analyst = L["shot"].format(**f)
        casual = L["c_res"][o].format(**f)
        if "big_chance" in reasons:
            analyst += L["why_big"].format(**f)
        else:
            txg, ts = ctx.team_xg_shots[team]
            analyst += L["why_shot"].format(txg=f"{txg:.2f}", ts=ts, t=f["t"])

    mom = ctx.summary["momentum"]
    if abs(mom) >= 45 and t in ("PASS", "DRIBBLE", "SHOT"):
        leader = ctx.home if mom > 0 else ctx.away
        if leader == team:
            casual += L["c_mom"].format(t=names[leader])

    return {"analyst": analyst, "casual": casual, "player_cam": _player_cam(L, ev, ctx, analyst, lang)}


def _goal_distance(team, home, x, y):
    """Metres from the goal `team` attacks to an absolute point."""
    u, v = attack_frame(team, home, x, y)
    return round(metres(100 - u, 50 - v))


def _player_cam(L, ev, ctx, analyst, lang):
    fp, ft = ctx.focus_player, ctx.focus_team
    s = ctx.focus_line
    pos = ctx.positions.get(ft, {}).get(fp)
    involved = ev.get("team") is not None and fp in (ev["player"], ev["receiver"], ev["opponent"], ev["player_off"])
    if involved and s:
        return L["on_ball"] + analyst + L["stat_line"].format(
            touches=s["touches"], sprints=s["sprints"], pc=s["passes_completed"], pa=s["passes"])
    if pos is None or s is None:
        return L["not_on"].format(fp=fp)
    bx, by = ev["location"]["end_x"], ev["location"]["end_y"]
    d = round(metres(pos[0] - bx, pos[1] - by))
    zone = _zone(L, ft, ctx.home, pos[0], pos[1])
    rating = s["rating"] if s["rating"] is not None else "-"
    return L["off_ball"].format(fp=fp, d=d, zone=zone, touches=s["touches"], sprints=s["sprints"], rating=rating)
