"""Stage 3 - persona router and localization.

Turns one event into the three viewer styles (analyst, casual, player_cam) in
English, Spanish or Japanese, and writes the other on-screen text: milestone
and threshold alerts, the story behind each key event, and the half-time and
full-time reports. These templates are the instant first render and the
fallback whenever Azure OpenAI is unavailable; AI text replaces them later.
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
        "pass_ok": "{p} finds {r} with a {len}m pass ({diff}/100 difficulty, {pr} pressure), gaining {gain}m and bypassing {byp} opponents.",
        "pass_short": "{p} plays a {len}m pass to {r} ({diff}/100 difficulty, {pr} pressure), recycling possession.",
        "pass_int": "{o} reads {p}'s {len}m pass and intercepts in {zone}; difficulty was {diff}/100 under {pr} pressure.",
        "drib": "{p} carries {len}m at {spd} km/h through {zone}, nearest defender {nd}m away.",
        "tackle_won": "{p} wins the ball from {o} in {zone} (pressure index {pi}).",
        "foul": "{p} fouls {o} in {zone}.",
        "card_y": " Yellow card.", "card_r": " Red card, {t} are down to ten.",
        "shot": "{p} shoots from {len}m: {xg} xG under {pr} pressure. {res}",
        "res": {"GOAL": "Scored, {score}.", "SAVED": "Saved by {o}.", "MISS": "Off target.", "BLOCKED": "Blocked by {o}."},
        "why_line": " Why it matters: {byp} defenders are taken out and {r} can run at the back line.",
        "why_press": " Why it matters: {ot}'s press forced the turnover {gd}m from goal.",
        "why_recover": " Why it matters: winning it cleanly under heavy pressure lets {ot} break from deep.",
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
        "fan_goal_for": "YES! ", "fan_goal_against": "Oh no... ",
        "fan_save_for": " What a save for us!", "fan_chance_against": " That was close for us...",
        "fan_card_for": " Harsh on us!", "fan_chance_for": " So close for us!", "fan_good": " Come on {t}!",
        "on_ball": "On the ball: ", "stat_line": " ({touches} touches, {sprints} sprints, {pc}/{pa} passes)",
        "off_ball": "{fp}: {d}m from the ball, in {zone}. {touches} touches, {sprints} sprints, {km} km covered, rating {rating}.",
        "not_on": "{fp} is not on the pitch.",
        # alerts and milestones
        "a_speed": "{p} hits {v} km/h!",
        "a_distance": "{p} has covered {v} km.",
        "a_top_speed": "Fastest sprint of the match: {p}, {v} km/h.",
        "a_first_goal": "First goal of the match: {p}.",
        "a_brace": "{p} has a brace!", "a_hat_trick": "HAT-TRICK for {p}!",
        "a_touches": "{p} reaches {v} touches.", "a_passes_completed": "{p} has completed {v} passes.",
        "a_team_passes": "{t}: {v} completed passes.", "a_tackles_won": "{p} has won {v} tackles.",
        "a_saves": "{p} makes save number {v}.",
        "a_spell": "{t}'s longest spell on the ball yet: {v} actions in a row.",
        "a_chaos": "The game has turned chaotic: {v}% of recent actions changed possession.",
        "a_control": "{t} are in control: {v}% of recent play, with few turnovers.",
        "a_press_up": "{t}'s press has intensified: pressure index {v} on the ball, up from {w}.",
        # stories
        "s_buildup": "Build-up",
        "b_won_tackle": "{p} won the ball from {o}", "b_won_int": "{p} intercepted {o}'s pass",
        "b_pass": "{p} found {r}", "b_pass_lb": "{p} split the lines to find {r}", "b_drib": "{p} drove forward",
        "s_goal": "{p} scored from {len}m ({xg} xG).", "s_lead": "{t} take the lead, {score}.",
        "s_level": "It's level, {score}.", "s_extend": "{t} extend the lead, {score}.", "s_back": "{t} pull one back, {score}.",
        "s_assist": "Assist: {a}.", "s_ctx_goal": "{p}'s {nth} goal of the match (shots: {shots}, touches: {touches}).",
        "nth": ["first", "second", "third", "fourth", "fifth"],
        "s_save": "{o} saved {p}'s {xg} xG shot from {len}m.", "s_ctx_save": "{o}'s save number {n} today.",
        "s_miss": "{p} missed a {xg} xG chance from {len}m.", "s_block": "{o} blocked {p}'s {xg} xG chance from {len}m.",
        "s_card_y": "{p} was booked for a foul on {o} in {zone}.", "s_ctx_card_y": "{p} has to be careful now: a second yellow means a red.",
        "s_card_r": "{p} was sent off for a foul on {o}.", "s_ctx_card_r": "{t} must play on with ten men.",
        "s_sub": "{p} replaced {o}.", "s_ctx_sub": "{o} leaves after {min} minutes: rating {rating}, {touches} touches, {km} km covered.",
        # reports
        "r_head": {"HALF_TIME": "Half-time: {score}.", "FULL_TIME": "Full-time: {score}."},
        "r_numbers": "xG {hx}-{ax}, shots {hs}-{as} ({hot}-{aot} on target), possession {hp}-{ap}%.",
        "r_deserved": "{t} deserve their lead on the chances created.",
        "r_lucky": "{t} lead despite creating less ({txg} xG to {oxg}).",
        "r_draw_better": "Level, but {t} have had the better chances.",
        "r_draw_even": "An even contest on the chances.",
        "r_control": "{t} controlled the ball for long spells ({v}% of controlled phases).",
        "r_chaos": "It has been scrappy: {v}% of phases were chaotic, with frequent turnovers.",
        "r_press": "{t}'s press won more ball in the opponent half ({v} to {w}).",
        "r_mom": {"HALF_TIME": "{t} finished the half on top.", "FULL_TIME": "{t} were the stronger side after the break."},
        "r_best": "Best player: {name} ({t}), rating {r}: {items}.",
        "items": {"goals": "{n} goals", "assists": "{n} assists", "shots": "{n} shots", "tackles_won": "{n} tackles won", "interceptions": "{n} interceptions", "passes_completed": "{n} completed passes", "touches": "{n} touches"},
    },
    "es": {
        "pressure": {"LOW": "baja", "MEDIUM": "media", "HIGH": "alta"},
        "third": {"defensive": "tercio defensivo", "middle": "tercio medio", "final": "último tercio"},
        "channel": {"left": "la izquierda", "central": "el centro", "right": "la derecha"},
        "zone": "{channel} del {third}",
        "pass_ok": "{p} encuentra a {r} con un pase de {len} m (dificultad {diff}/100, presión {pr}), gana {gain} m y supera a {byp} rivales.",
        "pass_short": "{p} juega un pase de {len} m a {r} (dificultad {diff}/100, presión {pr}) para mantener la posesión.",
        "pass_int": "{o} lee el pase de {len} m de {p} y lo intercepta en {zone}; dificultad {diff}/100 con presión {pr}.",
        "drib": "{p} conduce {len} m a {spd} km/h por {zone}, con el defensor más cercano a {nd} m.",
        "tackle_won": "{p} le roba el balón a {o} en {zone} (índice de presión {pi}).",
        "foul": "Falta de {p} sobre {o} en {zone}.",
        "card_y": " Tarjeta amarilla.", "card_r": " Tarjeta roja: {t} se queda con diez.",
        "shot": "{p} dispara desde {len} m: {xg} xG con presión {pr}. {res}",
        "res": {"GOAL": "¡Gol! {score}.", "SAVED": "Lo para {o}.", "MISS": "Se va fuera.", "BLOCKED": "Lo bloquea {o}."},
        "why_line": " Por qué importa: deja atrás a {byp} rivales y {r} puede encarar a la defensa.",
        "why_press": " Por qué importa: la presión de {ot} provoca la pérdida a {gd} m de la portería.",
        "why_recover": " Por qué importa: recuperar limpio bajo tanta presión permite a {ot} salir a la contra desde atrás.",
        "why_big": " Por qué importa: una ocasión del {pct}%, de las más claras del partido.",
        "why_shot": " Por qué importa: {t} suma {txg} xG en el partido (disparos: {ts}).",
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
        "fan_goal_for": "¡SÍ! ", "fan_goal_against": "Oh no... ",
        "fan_save_for": " ¡Qué parada para nosotros!", "fan_chance_against": " Uf, eso estuvo cerca...",
        "fan_card_for": " ¡Muy duro con nosotros!", "fan_chance_for": " ¡Uy, casi!", "fan_good": " ¡Vamos {t}!",
        "on_ball": "Con el balón: ", "stat_line": " ({touches} toques, {sprints} sprints, {pc}/{pa} pases)",
        "off_ball": "{fp}: a {d} m del balón, en {zone}. {touches} toques, {sprints} sprints, {km} km recorridos, nota {rating}.",
        "not_on": "{fp} no está en el campo.",
        "a_speed": "¡{p} alcanza {v} km/h!",
        "a_distance": "{p} ya ha recorrido {v} km.",
        "a_top_speed": "Sprint más rápido del partido: {p}, {v} km/h.",
        "a_first_goal": "Primer gol del partido: {p}.",
        "a_brace": "¡Doblete de {p}!", "a_hat_trick": "¡HAT-TRICK de {p}!",
        "a_touches": "{p} llega a {v} toques.", "a_passes_completed": "{p} ya completa {v} pases.",
        "a_team_passes": "{t}: {v} pases completados.", "a_tackles_won": "{p} ya gana {v} entradas.",
        "a_saves": "{p} hace su parada número {v}.",
        "a_spell": "La posesión más larga de {t}: {v} acciones seguidas.",
        "a_chaos": "El partido se vuelve caótico: el {v}% de las acciones recientes cambió la posesión.",
        "a_control": "{t} tiene el control: {v}% del juego reciente, con pocas pérdidas.",
        "a_press_up": "La presión de {t} se intensifica: índice {v} sobre el balón, antes {w}.",
        "s_buildup": "Jugada",
        "b_won_tackle": "{p} le robó el balón a {o}", "b_won_int": "{p} interceptó el pase de {o}",
        "b_pass": "{p} encontró a {r}", "b_pass_lb": "{p} rompió líneas para encontrar a {r}", "b_drib": "{p} condujo hacia adelante",
        "s_goal": "{p} marcó desde {len} m ({xg} xG).", "s_lead": "{t} se adelanta, {score}.",
        "s_level": "Empate, {score}.", "s_extend": "{t} amplía la ventaja, {score}.", "s_back": "{t} recorta, {score}.",
        "s_assist": "Asistencia: {a}.", "s_ctx_goal": "{nth} gol de {p} en el partido (disparos: {shots}, toques: {touches}).",
        "nth": ["Primer", "Segundo", "Tercer", "Cuarto", "Quinto"],
        "s_save": "{o} detuvo el disparo de {p} ({xg} xG) desde {len} m.", "s_ctx_save": "Parada número {n} de {o} hoy.",
        "s_miss": "{p} falló una ocasión de {xg} xG desde {len} m.", "s_block": "{o} bloqueó la ocasión de {p} ({xg} xG) desde {len} m.",
        "s_card_y": "{p} vio la amarilla por una falta sobre {o} en {zone}.", "s_ctx_card_y": "{p} debe tener cuidado: otra amarilla sería la roja.",
        "s_card_r": "{p} fue expulsado por una falta sobre {o}.", "s_ctx_card_r": "{t} tendrá que jugar con diez.",
        "s_sub": "{p} sustituyó a {o}.", "s_ctx_sub": "{o} se va tras {min} minutos: nota {rating}, {touches} toques, {km} km.",
        "r_head": {"HALF_TIME": "Descanso: {score}.", "FULL_TIME": "Final: {score}."},
        "r_numbers": "xG {hx}-{ax}, disparos {hs}-{as} ({hot}-{aot} a puerta), posesión {hp}-{ap}%.",
        "r_deserved": "{t} merece ir por delante por las ocasiones creadas.",
        "r_lucky": "{t} gana pese a generar menos ({txg} xG contra {oxg}).",
        "r_draw_better": "Empate, pero {t} ha tenido las mejores ocasiones.",
        "r_draw_even": "Un partido igualado en ocasiones.",
        "r_control": "{t} controló el balón en fases largas ({v}% de las fases de control).",
        "r_chaos": "Partido trabado: el {v}% de las fases fue caótico, con muchas pérdidas.",
        "r_press": "La presión de {t} recuperó más balones en campo rival ({v} contra {w}).",
        "r_mom": {"HALF_TIME": "{t} terminó la primera parte por encima.", "FULL_TIME": "{t} fue mejor tras el descanso."},
        "r_best": "Mejor jugador: {name} ({t}), nota {r}: {items}.",
        "items": {"goals": "{n} goles", "assists": "{n} asistencias", "shots": "{n} disparos", "tackles_won": "{n} entradas ganadas", "interceptions": "{n} intercepciones", "passes_completed": "{n} pases completados", "touches": "{n} toques"},
    },
    "ja": {
        "pressure": {"LOW": "低", "MEDIUM": "中", "HIGH": "高"},
        "third": {"defensive": "自陣", "middle": "中盤", "final": "ファイナルサード"},
        "channel": {"left": "左", "central": "中央", "right": "右"},
        "zone": "{third}の{channel}",
        "pass_ok": "{p}が{len}mのパスで{r}へ（難易度{diff}/100、プレッシャー{pr}）。{gain}m前進し、{byp}人を突破。",
        "pass_short": "{p}が{len}mのパスで{r}へつなぐ（難易度{diff}/100、プレッシャー{pr}）。ポゼッションを維持。",
        "pass_int": "{o}が{p}の{len}mのパスを{zone}でインターセプト。難易度{diff}/100、プレッシャー{pr}。",
        "drib": "{p}が{zone}を{len}mドリブル（時速{spd}km）。最も近い守備者まで{nd}m。",
        "tackle_won": "{p}が{zone}で{o}からボールを奪取（プレッシャー指数{pi}）。",
        "foul": "{p}が{zone}で{o}にファウル。",
        "card_y": "イエローカード。", "card_r": "レッドカード、{t}は10人に。",
        "shot": "{p}が{len}mからシュート：xG {xg}、プレッシャー{pr}。{res}",
        "res": {"GOAL": "ゴール！{score}。", "SAVED": "{o}がセーブ。", "MISS": "枠外。", "BLOCKED": "{o}がブロック。"},
        "why_line": "なぜ重要か：{byp}人の守備者を置き去りにし、{r}が最終ラインに仕掛けられる。",
        "why_press": "なぜ重要か：{ot}のプレスがゴールまで{gd}mの位置でボールを奪った。",
        "why_recover": "なぜ重要か：強いプレッシャーの中で奪い切り、{ot}は自陣からカウンターに出られる。",
        "why_big": "なぜ重要か：得点確率{pct}%の決定機だった。",
        "why_shot": "なぜ重要か：{t}の試合合計xGは{txg}（シュート{ts}本）。",
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
        "fan_goal_for": "やった！", "fan_goal_against": "ああ…",
        "fan_save_for": "助かった、ナイスセーブ！", "fan_chance_against": "危なかった…",
        "fan_card_for": "厳しい判定だ！", "fan_chance_for": "惜しい！", "fan_good": "いけ、{t}！",
        "on_ball": "ボール保持：", "stat_line": "（タッチ{touches}回、スプリント{sprints}回、パス{pc}/{pa}）",
        "off_ball": "{fp}：ボールまで{d}m、{zone}。タッチ{touches}回、スプリント{sprints}回、走行距離{km}km、評価{rating}。",
        "not_on": "{fp}は現在ピッチにいません。",
        "a_speed": "{p}が時速{v}kmを記録！",
        "a_distance": "{p}の走行距離が{v}kmに到達。",
        "a_top_speed": "この試合最速のスプリント：{p}、時速{v}km。",
        "a_first_goal": "この試合の先制点：{p}。",
        "a_brace": "{p}が2点目！", "a_hat_trick": "{p}がハットトリック！",
        "a_touches": "{p}のタッチ数が{v}回に到達。", "a_passes_completed": "{p}のパス成功が{v}本に。",
        "a_team_passes": "{t}のパス成功が{v}本に。", "a_tackles_won": "{p}のタックル成功が{v}回に。",
        "a_saves": "{p}が{v}本目のセーブ。",
        "a_spell": "{t}のこの試合最長のポゼッション：{v}プレー連続。",
        "a_chaos": "試合が混戦模様に：直近のプレーの{v}%でボールが入れ替わった。",
        "a_control": "{t}が主導権を握る：直近のプレーの{v}%、ボールロストも少ない。",
        "a_press_up": "{t}のプレスが強まった：プレッシャー指数{v}（以前は{w}）。",
        "s_buildup": "攻撃の流れ",
        "b_won_tackle": "{p}が{o}からボールを奪う", "b_won_int": "{p}が{o}のパスをカット",
        "b_pass": "{p}から{r}へ", "b_pass_lb": "{p}がライン間を通して{r}へ", "b_drib": "{p}が持ち上がる",
        "s_goal": "{p}が{len}mから決めた（xG {xg}）。", "s_lead": "{t}が先行、{score}。",
        "s_level": "同点、{score}。", "s_extend": "{t}がリードを広げる、{score}。", "s_back": "{t}が1点を返す、{score}。",
        "s_assist": "アシスト：{a}。", "s_ctx_goal": "{p}はこの試合{nth}（シュート{shots}本、タッチ{touches}回）。",
        "nth": ["1点目", "2点目", "3点目", "4点目", "5点目"],
        "s_save": "{o}が{p}の{len}mのシュート（xG {xg}）をセーブ。", "s_ctx_save": "{o}はこの試合{n}本目のセーブ。",
        "s_miss": "{p}が{len}mからの決定機（xG {xg}）を外した。", "s_block": "{o}が{p}の{len}mのシュート（xG {xg}）をブロック。",
        "s_card_y": "{p}が{zone}で{o}へのファウルにより警告。", "s_ctx_card_y": "{p}はもう1枚で退場、慎重なプレーが求められる。",
        "s_card_r": "{p}が{o}へのファウルで退場。", "s_ctx_card_r": "{t}は10人で戦うことに。",
        "s_sub": "{o}に代わって{p}が入る。", "s_ctx_sub": "{o}は{min}分間で評価{rating}、タッチ{touches}回、走行距離{km}km。",
        "r_head": {"HALF_TIME": "ハーフタイム：{score}。", "FULL_TIME": "試合終了：{score}。"},
        "r_numbers": "xG {hx}-{ax}、シュート{hs}-{as}（枠内{hot}-{aot}）、ポゼッション{hp}-{ap}%。",
        "r_deserved": "チャンスの数を見ても{t}のリードは妥当。",
        "r_lucky": "{t}はチャンスで劣りながらもリード（xG {txg}対{oxg}）。",
        "r_draw_better": "同点だが、より良いチャンスを作ったのは{t}。",
        "r_draw_even": "チャンスの面では互角の展開。",
        "r_control": "{t}が長い時間ボールを支配（主導権のある時間帯の{v}%）。",
        "r_chaos": "落ち着かない展開：{v}%の時間帯でボールが頻繁に入れ替わった。",
        "r_press": "{t}のプレスが敵陣でより多くボールを奪った（{v}対{w}）。",
        "r_mom": {"HALF_TIME": "前半は{t}が優勢に終えた。", "FULL_TIME": "後半は{t}が優勢だった。"},
        "r_best": "ベストプレーヤー：{name}（{t}）、評価{r}：{items}。",
        "items": {"goals": "ゴール{n}", "assists": "アシスト{n}", "shots": "シュート{n}本", "tackles_won": "タックル成功{n}回", "interceptions": "インターセプト{n}回", "passes_completed": "パス成功{n}本", "touches": "タッチ{n}回"},
    },
}


class Context:
    """Everything beyond the event itself that the personas may mention."""

    def __init__(self, home, away, summary, positions, focus_team, focus_player, focus_line, team_xg_shots,
                 right_team=None, fav_team=None):
        self.home, self.away = home, away
        self.summary = summary
        self.positions = positions
        self.focus_team, self.focus_player = focus_team, focus_player
        self.focus_line = focus_line
        self.team_xg_shots = team_xg_shots  # team -> (xg, shots)
        self.right_team = right_team or home
        self.fav_team = fav_team


def _L(lang):
    return T.get(lang, T["en"])


def _names(lang):
    return TEAM_NAMES.get(lang, TEAM_NAMES["en"])


def _zone(L, team, right_team, x, y):
    u, v = attack_frame(team, right_team, x, y)
    third, channel = zone_of(u, v)
    return L["zone"].format(third=L["third"][third], channel=L["channel"][channel])


def _score_text(lang, score, home, away):
    n = _names(lang)
    return f"{n[home]} {score['home']}-{score['away']} {n[away]}"


def render(ev, ctx, lang="en"):
    """Return {"analyst", "casual", "player_cam"} for one event."""
    L, names = _L(lang), _names(lang)
    t, o = ev["event_type"], ev["outcome"]
    m, loc = ev["metrics"], ev["location"]
    score = _score_text(lang, ev["score"], ctx.home, ctx.away)

    if t in ("HALF_TIME", "FULL_TIME"):
        xg = f"{ctx.summary['xg'][0]:.2f}-{ctx.summary['xg'][1]:.2f}"
        line = L["ht" if t == "HALF_TIME" else "ft"].format(score=score, xg=xg)
        return {"analyst": line, "casual": line, "player_cam": _player_cam(L, ev, ctx, line)}

    team = ev["team"]
    opp_team = ctx.away if team == ctx.home else ctx.home
    f = {
        "p": ev["player"], "r": ev["receiver"], "o": ev["opponent"] or ev["player_off"],
        "t": names[team], "ot": names[opp_team], "len": ev["length_m"],
        "diff": m["pass_difficulty"], "pr": L["pressure"].get(m["pressure"], ""),
        "gain": m["forward_gain_m"], "byp": m["players_bypassed"], "spd": m["sprint_speed_kmh"],
        "nd": m["nearest_defender_m"], "pi": m["pressure_index"],
        "xg": f"{m['xg']:.2f}" if m["xg"] is not None else "", "pct": round((m["xg"] or 0) * 100),
        "zone": _zone(L, team, ctx.right_team, loc["start_x"], loc["start_y"]),
        "score": score, "min": int(ev["minute"]),
    }
    reasons = ev["impact_reasons"]

    if t == "SUBSTITUTION":
        line = L["sub"].format(**f)
        return {"analyst": line, "casual": line, "player_cam": _player_cam(L, ev, ctx, line)}

    if t == "PASS" and o == "COMPLETE":
        forward = (m["forward_gain_m"] or 0) >= 5 and (m["players_bypassed"] or 0) > 0
        analyst = L["pass_ok" if forward else "pass_short"].format(**f)
        if "line_breaking_pass" in reasons:
            analyst += L["why_line"].format(**f)
            casual = L["c_pass_lb"].format(**f)
        else:
            casual = L["c_pass_good" if (m["pass_difficulty"] or 0) >= 60 else "c_pass"].format(**f)
    elif t == "PASS":
        f["zone"] = _zone(L, team, ctx.right_team, loc["end_x"], loc["end_y"])
        analyst = L["pass_int"].format(**f)
        casual = L["c_int"].format(**f)
        if "high_press_turnover" in reasons:
            f["gd"] = _goal_distance(opp_team, ctx.right_team, loc["end_x"], loc["end_y"])
            analyst += L["why_press" if f["gd"] <= 45 else "why_recover"].format(**f)
    elif t == "DRIBBLE":
        analyst = L["drib"].format(**f)
        casual = L["c_drib_hp" if m["pressure"] == "HIGH" else "c_drib"].format(**f)
    elif t == "TACKLE":
        # the actor is the tackler; describe from their side
        if o == "WON":
            analyst = L["tackle_won"].format(**f)
            casual = L["c_tackle"].format(**f)
            if "high_press_turnover" in reasons:
                f["gd"] = _goal_distance(team, ctx.right_team, loc["end_x"], loc["end_y"])
                f["ot"] = names[team]
                analyst += L["why_press" if f["gd"] <= 45 else "why_recover"].format(**f)
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

    casual = _fan_voice(L, ev, ctx, casual, names)
    mom = ctx.summary["momentum"]
    if abs(mom) >= 45 and t in ("PASS", "DRIBBLE", "SHOT") and not ctx.fav_team:
        leader = ctx.home if mom > 0 else ctx.away
        if leader == team:
            casual += L["c_mom"].format(t=names[leader])

    return {"analyst": analyst, "casual": casual, "player_cam": _player_cam(L, ev, ctx, analyst)}


def _fan_voice(L, ev, ctx, casual, names):
    """Casual commentary from the favourite club's side of the stands."""
    fav = ctx.fav_team
    if not fav or not ev.get("team"):
        return casual
    t, o, ours = ev["event_type"], ev["outcome"], ev["team"] == fav
    if t == "SHOT" and o == "GOAL":
        return (L["fan_goal_for"] if ours else L["fan_goal_against"]) + casual
    if t == "SHOT" and o in ("SAVED", "BLOCKED", "MISS"):
        if ours:
            return casual + L["fan_chance_for"]
        return casual + (L["fan_save_for"] if o == "SAVED" else L["fan_chance_against"])
    if ev.get("card") and ours:
        return casual + L["fan_card_for"]
    if ours and ev["is_impact_moment"]:
        return casual + L["fan_good"].format(t=names[fav])
    return casual


def _goal_distance(team, right_team, x, y):
    """Metres from the goal `team` attacks to an absolute point."""
    u, v = attack_frame(team, right_team, x, y)
    return round(metres(100 - u, 50 - v))


def _player_cam(L, ev, ctx, analyst):
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
    zone = _zone(L, ft, ctx.right_team, pos[0], pos[1])
    rating = s["rating"] if s["rating"] is not None else "-"
    return L["off_ball"].format(fp=fp, d=d, zone=zone, touches=s["touches"], sprints=s["sprints"],
                                km=s["distance_km"], rating=rating)


# ---- alerts, stories, reports ---------------------------------------------
def alert_text(a, lang="en"):
    L, names = _L(lang), _names(lang)
    v = a["value"]
    if isinstance(v, float):
        v = f"{v:.1f}"
    return L["a_" + a["key"]].format(p=a["player"], t=names.get(a["team"], ""), v=v, w=a["value2"])


def _buildup_phrase(L, e):
    t, o = e["event_type"], e["outcome"]
    if t == "TACKLE" and o == "WON":
        return L["b_won_tackle"].format(p=e["player"], o=e["opponent"])
    if t == "PASS" and o == "INTERCEPTED":
        return L["b_won_int"].format(p=e["opponent"], o=e["player"])
    if t == "PASS" and o == "COMPLETE":
        key = "b_pass_lb" if "line_breaking_pass" in e["impact_reasons"] else "b_pass"
        return L[key].format(p=e["player"], r=e["receiver"])
    if t == "DRIBBLE":
        return L["b_drib"].format(p=e["player"])
    return None


def story(ev, buildup, ctx, lines, lang="en"):
    """The story behind a key event: build-up, the moment, and its context.

    `lines` maps (team, player) -> stats from MatchStats.player_line."""
    L, names = _L(lang), _names(lang)
    t, o, team = ev["event_type"], ev["outcome"], ev["team"]
    m = ev["metrics"]
    score = _score_text(lang, ev["score"], ctx.home, ctx.away)
    f = {"p": ev["player"], "o": ev["opponent"] or ev["player_off"], "t": names[team],
         "len": ev["length_m"], "xg": f"{m['xg']:.2f}" if m["xg"] is not None else "", "score": score,
         "zone": _zone(L, team, ctx.right_team, ev["location"]["start_x"], ev["location"]["start_y"])}
    parts = []
    chain = [x for x in (_buildup_phrase(L, e) for e in buildup) if x]
    if chain and t == "SHOT":
        parts.append(f"{L['s_buildup']}: " + " → ".join(chain) + ("。" if lang == "ja" else "."))
    me = lines.get((team, ev["player"])) or {}
    if t == "SHOT" and o == "GOAL":
        parts.append(L["s_goal"].format(**f))
        own = ev["score"]["home" if team == ctx.home else "away"]
        their = ev["score"]["away" if team == ctx.home else "home"]
        key = "s_level" if own == their else "s_lead" if own - their == 1 else "s_extend" if own > their else "s_back"
        parts.append(L[key].format(**f))
        last_pass = next((e for e in reversed(buildup) if e["event_type"] == "PASS" and e["outcome"] == "COMPLETE"), None)
        if last_pass and last_pass["receiver"] == ev["player"]:
            parts.append(L["s_assist"].format(a=last_pass["player"]))
        n = me.get("goals", 1)
        nth = L["nth"][n - 1] if 1 <= n <= len(L["nth"]) else str(n)
        parts.append(L["s_ctx_goal"].format(p=ev["player"], nth=nth, shots=me.get("shots", 1),
                                            touches=me.get("touches", 1)))
    elif t == "SHOT":
        if o == "SAVED":
            parts.append(L["s_save"].format(**f))
            keeper = lines.get((ctx.away if team == ctx.home else ctx.home, ev["opponent"])) or {}
            parts.append(L["s_ctx_save"].format(o=ev["opponent"], n=keeper.get("saves", 1)))
        elif o == "BLOCKED":
            parts.append(L["s_block"].format(**f))
        else:
            parts.append(L["s_miss"].format(**f))
    elif ev.get("card"):
        if ev["card"] == "YELLOW":
            parts += [L["s_card_y"].format(**f), L["s_ctx_card_y"].format(**f)]
        else:
            parts += [L["s_card_r"].format(**f), L["s_ctx_card_r"].format(**f)]
    elif t == "SUBSTITUTION":
        off = lines.get((team, ev["player_off"])) or {}
        parts.append(L["s_sub"].format(**f))
        parts.append(L["s_ctx_sub"].format(o=ev["player_off"], min=off.get("minutes", int(ev["minute"])),
                                           rating=off.get("rating") or "-", touches=off.get("touches", 0),
                                           km=off.get("distance_km", 0)))
    sep = "" if lang == "ja" else " "
    return sep.join(parts)


def report_text(r, lang="en"):
    """A short written verdict for the half-time or full-time report."""
    L, names = _L(lang), _names(lang)
    h, a = r["home"], r["away"]
    th, ta = r["teams"][h], r["teams"][a]
    parts = [L["r_head"][r["kind"]].format(score=_score_text(lang, r["score"], h, a)),
             L["r_numbers"].format(hx=f"{th['xg']:.2f}", ax=f"{ta['xg']:.2f}", hs=th["shots"], **{"as": ta["shots"]},
                                   hot=th["on_target"], aot=ta["on_target"], hp=th["possession"], ap=ta["possession"])]
    gh, ga = r["score"]["home"], r["score"]["away"]
    xh, xa = th["xg"], ta["xg"]
    if gh != ga:
        lead, trail = (h, a) if gh > ga else (a, h)
        lx, tx = r["teams"][lead]["xg"], r["teams"][trail]["xg"]
        if lx >= tx:
            parts.append(L["r_deserved"].format(t=names[lead]))
        else:
            parts.append(L["r_lucky"].format(t=names[lead], txg=f"{lx:.2f}", oxg=f"{tx:.2f}"))
    elif abs(xh - xa) >= 0.5:
        parts.append(L["r_draw_better"].format(t=names[h if xh > xa else a]))
    else:
        parts.append(L["r_draw_even"])
    ctrl = r["control"]
    lead_ctrl = max(ctrl, key=ctrl.get)
    if ctrl[lead_ctrl] >= 20 and ctrl[lead_ctrl] >= r["chaos_pct"]:
        parts.append(L["r_control"].format(t=names[lead_ctrl], v=ctrl[lead_ctrl]))
    elif r["chaos_pct"] >= 25:
        parts.append(L["r_chaos"].format(v=r["chaos_pct"]))
    pw = {t: r["teams"][t]["press_wins"] for t in (h, a)}
    pl = max(pw, key=pw.get)
    if pw[pl] > pw[a if pl == h else h]:
        parts.append(L["r_press"].format(t=names[pl], v=pw[pl], w=pw[a if pl == h else h]))
    if abs(r["momentum_avg"]) >= 15:
        parts.append(L["r_mom"][r["kind"]].format(t=names[h if r["momentum_avg"] > 0 else a]))
    b = r["best_player"]
    if b:
        keys = [k for k in ("goals", "assists", "shots", "tackles_won", "interceptions", "passes_completed") if b.get(k)][:3]
        items = ("、" if lang == "ja" else ", ").join(L["items"][k].format(n=b[k]) for k in keys)
        parts.append(L["r_best"].format(name=b["name"], t=names[b["team"]], r=b["rating"], items=items))
    sep = "" if lang == "ja" else " "
    return sep.join(parts)
