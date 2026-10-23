"""Stage 3 - persona router and localization.

Turns one event into the three viewer styles (analyst, casual, player_cam) in
English, Spanish or Japanese, and writes the other on-screen text: milestone
and threshold alerts, the story behind each key event, and the half-time and
full-time reports. These templates are the instant first render and the
fallback whenever Azure OpenAI is unavailable; AI text replaces them later.
"""
from analytics import attack_frame, metres, zone_of

TEAM_NAMES = {
    "en": {"Brackenford": "Brackenford", "Kestermouth": "Kestermouth"},
    "es": {"Brackenford": "Brackenford", "Kestermouth": "Kestermouth"},
    "ja": {"Brackenford": "ブラッケンフォード", "Kestermouth": "ケスターマス"},
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
        "items1": {"goals": "1 goal", "assists": "1 assist", "shots": "1 shot", "tackles_won": "1 tackle won", "interceptions": "1 interception", "passes_completed": "1 completed pass", "touches": "1 touch"},
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
        "items1": {"goals": "1 gol", "assists": "1 asistencia", "shots": "1 disparo", "tackles_won": "1 entrada ganada", "interceptions": "1 intercepción", "passes_completed": "1 pase completado", "touches": "1 toque"},
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


# Set pieces, offside and the ball going out of play.
SET_PIECE_T = {
    "en": {
        "sp": {"FREE_KICK": "free kick", "CORNER": "corner", "THROW_IN": "throw-in", "PENALTY": "penalty", "GOAL_KICK": "goal kick"},
        "sp_r": {"FREE_KICK": "Free kick", "CORNER": "Corner", "THROW_IN": "Throw-in", "PENALTY": "Penalty", "GOAL_KICK": "Goal kick"},
        "restart": " {sp_r} to {rt}.",
        "sp_pass": "{p} takes the {sp}, {len}m to {r}.",
        "sp_cross": "{p} swings in the {sp} and {r} wins it in the air in {ezone} (delivery difficulty {diff}/100).",
        "sp_cleared": "{p}'s {sp} is dealt with by {o}.",
        "fk_shot": "{p} goes for goal with the free kick from {len}m, over the wall: {xg} xG. {res}",
        "pen_shot": "{p} takes the penalty ({xg} xG). {res}",
        "header": "{p} heads at goal from {len}m: {xg} xG. {res}",
        "out": "{p}'s {len}m pass runs out of play.",
        "offside": "{r} is caught offside from {p}'s pass.",
        "pass_int_out": "{o} cuts out {p}'s {len}m pass in {zone} but can only turn it behind.",
        "c_int_out": "{o} blocks it behind!",
        "pen_foul": "{p} brings down {o} inside the box: penalty to {ot}!",
        "c_sp_pass": {"THROW_IN": "{p} takes the throw to {r}.", "GOAL_KICK": "{p} restarts with a goal kick to {r}.",
                      "FREE_KICK": "{p} plays the free kick to {r}.", "CORNER": "{p} plays the corner short to {r}."},
        "c_cross": "{p} whips it in... {r} rises highest!", "c_cleared": "{o} heads it away.",
        "c_fk_shot": "{p} curls the free kick... ", "c_pen_shot": "{p} steps up... ", "c_header": "{p} gets a head on it! ",
        "c_out": "{p}'s pass runs out of play.", "c_offside": "Flag up! {r} is offside.",
        "c_restart": {"CORNER": " Corner!", "GOAL_KICK": " Goal kick.", "THROW_IN": " Throw-in.", "FREE_KICK": " Free kick.", "PENALTY": " PENALTY!"},
        "c_pen_foul": "PENALTY! {p} brings down {o}!",
        "fan_pen_for": " Penalty to us!", "fan_pen_against": " Oh no, a penalty against us...",
        "s_pen": "{p} brought down {o} inside the box and {ot} have a penalty.", "s_ctx_pen": "A penalty is worth about 0.76 xG.",
        "s_from": {"CORNER": "It came from a corner.", "FREE_KICK": "It came from a free kick.", "PENALTY": "From the penalty spot.",
                   "THROW_IN": "It started with a throw-in.", "GOAL_KICK": "It started with a goal kick."},
        "b_sp": "{p} took the {sp} to {r}", "s_head": "It was a header.",
        "r_set": "Set pieces: corners {hc}-{ac}, fouls {hf}-{af}.",
    },
    "es": {
        "sp": {"FREE_KICK": "tiro libre", "CORNER": "córner", "THROW_IN": "saque de banda", "PENALTY": "penalti", "GOAL_KICK": "saque de puerta"},
        "sp_r": {"FREE_KICK": "Tiro libre", "CORNER": "Córner", "THROW_IN": "Saque de banda", "PENALTY": "Penalti", "GOAL_KICK": "Saque de puerta"},
        "restart": " {sp_r} a favor de {rt}.",
        "sp_pass": "{p} pone el balón en juego ({sp}) con un pase de {len} m a {r}.",
        "sp_cross": "{p} centra a balón parado ({sp}) y {r} gana el balón aéreo en {ezone} (dificultad {diff}/100).",
        "sp_cleared": "{o} despeja el centro de {p} ({sp}).",
        "fk_shot": "{p} lanza el tiro libre directo desde {len} m por encima de la barrera: {xg} xG. {res}",
        "pen_shot": "{p} lanza el penalti ({xg} xG). {res}",
        "header": "{p} cabecea desde {len} m: {xg} xG. {res}",
        "out": "El pase de {len} m de {p} se va fuera.",
        "offside": "{r} cae en fuera de juego tras el pase de {p}.",
        "pass_int_out": "{o} corta el pase de {len} m de {p} en {zone}, pero el balón sale por la línea de fondo.",
        "c_int_out": "¡{o} la manda a córner!",
        "pen_foul": "{p} derriba a {o} dentro del área: ¡penalti a favor de {ot}!",
        "c_sp_pass": {"THROW_IN": "{p} saca de banda para {r}.", "GOAL_KICK": "{p} saca de puerta hacia {r}.",
                      "FREE_KICK": "{p} saca el tiro libre hacia {r}.", "CORNER": "{p} saca el córner en corto para {r}."},
        "c_cross": "{p} la cuelga... ¡{r} se eleva más que nadie!", "c_cleared": "{o} la despeja de cabeza.",
        "c_fk_shot": "{p} perfila el tiro libre... ", "c_pen_shot": "{p} se prepara... ", "c_header": "¡{p} remata de cabeza! ",
        "c_out": "El pase de {p} se va fuera.", "c_offside": "¡Bandera arriba! {r} está en fuera de juego.",
        "c_restart": {"CORNER": " ¡Córner!", "GOAL_KICK": " Saque de puerta.", "THROW_IN": " Saque de banda.", "FREE_KICK": " Tiro libre.", "PENALTY": " ¡PENALTI!"},
        "c_pen_foul": "¡PENALTI! {p} derriba a {o}.",
        "fan_pen_for": " ¡Penalti para nosotros!", "fan_pen_against": " Oh no, penalti en contra...",
        "s_pen": "{p} derribó a {o} dentro del área y {ot} tiene un penalti.", "s_ctx_pen": "Un penalti vale unos 0,76 xG.",
        "s_from": {"CORNER": "Llegó de un córner.", "FREE_KICK": "Llegó de un tiro libre.", "PENALTY": "Desde el punto de penalti.",
                   "THROW_IN": "Empezó con un saque de banda.", "GOAL_KICK": "Empezó con un saque de puerta."},
        "b_sp": "{p} puso en juego ({sp}) hacia {r}", "s_head": "Fue de cabeza.",
        "r_set": "Balón parado: córners {hc}-{ac}, faltas {hf}-{af}.",
    },
    "ja": {
        "sp": {"FREE_KICK": "フリーキック", "CORNER": "コーナーキック", "THROW_IN": "スローイン", "PENALTY": "PK", "GOAL_KICK": "ゴールキック"},
        "sp_r": {"FREE_KICK": "フリーキック", "CORNER": "コーナーキック", "THROW_IN": "スローイン", "PENALTY": "PK", "GOAL_KICK": "ゴールキック"},
        "restart": "{rt}の{sp_r}。",
        "sp_pass": "{p}が{sp}で{len}m先の{r}へ。",
        "sp_cross": "{p}の{sp}に{r}が{ezone}で競り勝つ（難易度{diff}/100）。",
        "sp_cleared": "{p}の{sp}は{o}がクリア。",
        "fk_shot": "{p}が{len}mの直接フリーキックで壁越しに狙う：xG {xg}。{res}",
        "pen_shot": "{p}がPKを蹴る（xG {xg}）。{res}",
        "header": "{p}が{len}mからヘディングシュート：xG {xg}。{res}",
        "out": "{p}の{len}mのパスはピッチの外へ。",
        "offside": "{p}のパスに抜け出した{r}はオフサイド。",
        "pass_int_out": "{o}が{zone}で{p}の{len}mのパスをカットするも、ボールはゴールラインを割る。",
        "c_int_out": "{o}がブロック、ボールはラインの外へ！",
        "pen_foul": "{p}がペナルティエリア内で{o}を倒す：{ot}にPK！",
        "c_sp_pass": {"THROW_IN": "{p}のスローインから{r}へ。", "GOAL_KICK": "{p}のゴールキックで{r}へ。",
                      "FREE_KICK": "{p}のフリーキックから{r}へ。", "CORNER": "{p}がショートコーナーで{r}へ。"},
        "c_cross": "{p}が蹴り込む…{r}が高い！", "c_cleared": "{o}が頭でクリア。",
        "c_fk_shot": "{p}が直接狙う…", "c_pen_shot": "{p}がPKのキッカーに…", "c_header": "{p}のヘディング！",
        "c_out": "{p}のパスはピッチの外へ。", "c_offside": "旗が上がった！{r}はオフサイド。",
        "c_restart": {"CORNER": "コーナーキック！", "GOAL_KICK": "ゴールキック。", "THROW_IN": "スローイン。", "FREE_KICK": "フリーキック。", "PENALTY": "PK！"},
        "c_pen_foul": "PK！{p}が{o}を倒した！",
        "fan_pen_for": "PKだ、大チャンス！", "fan_pen_against": "ああ、PKを与えてしまった…",
        "s_pen": "{p}がエリア内で{o}を倒し、{ot}にPKが与えられた。", "s_ctx_pen": "PKの期待値はおよそ0.76 xG。",
        "s_from": {"CORNER": "コーナーキックから生まれた。", "FREE_KICK": "フリーキックから生まれた。", "PENALTY": "PKによる得点機。",
                   "THROW_IN": "スローインから始まった。", "GOAL_KICK": "ゴールキックから始まった。"},
        "b_sp": "{p}の{sp}から{r}へ", "s_head": "ヘディングでの一撃。",
        "r_set": "セットプレー：コーナーキック{hc}-{ac}、ファウル{hf}-{af}。",
    },
}
for _lang, _extra in SET_PIECE_T.items():
    T[_lang].update(_extra)

# Match-day realism: woodwork, VAR, own goals, crosses, rebounds, injuries, why a change was made,
# added time and how a team changes its approach with the score.
MATCH_T = {
    "en": {
        "res": {"WOODWORK": "Off the woodwork!", "DISALLOWED": "In the net, but VAR rules it out for {why}."},
        "c_res": {"WOODWORK": "{p} hits the woodwork!", "DISALLOWED": "It's in... but VAR says NO!"},
        "var_reason": {"OFFSIDE": "offside", "FOUL": "a foul in the build-up", "HANDBALL": "handball"},
        "var_stands": " VAR checked it: the goal stands.", "c_var_stands": " (VAR checked it: the goal stands!)",
        "own_goal": "{o} turns {p}'s ball into their own net. {score}.",
        "c_own_goal": "OWN GOAL! {o} puts it past their own keeper! {score}",
        "cross_ok": "{p} crosses from {zone} and {r} attacks it in the box (delivery difficulty {diff}/100).",
        "cross_cleared": "{p}'s cross from {zone} is cleared by {o}.",
        "claimed": "{o} comes off the line and claims {p}'s ball into the box.",
        "c_cross_ok": "{p} whips in a cross... {r} is there!", "c_claimed": "{o} plucks it out of the air.",
        "rebound": "{p} reacts first to the loose ball, {len}m out: {xg} xG. {res}", "c_rebound": "Rebound! {p} pounces... ",
        "injury": "{p} is down injured and needs treatment.", "c_injury": "{p} is down and needs the physio.",
        "sub_why": {"injury": " A forced change: {o} could not continue."},
        "a_added_time": "The fourth official shows {v} minutes of added time.",
        "a_chasing": "{t} are pushing forward: a higher line, harder pressing and more direct balls.",
        "a_protecting": "{t} are sitting deeper now, dropping off and slowing the game down.",
        "s_own_goal": "{o} turned the ball into their own net from {p}'s delivery.",
        "s_var_no": "{p} had the ball in the net from {len}m, but VAR ruled it out for {why}.",
        "s_var_ok": "VAR checked it and the goal stood.",
        "s_woodwork": "{p} hit the woodwork from {len}m ({xg} xG).",
        "s_injury": "{p} went down injured and needed treatment.",
        "s_reshuffle": "{m} drops into the back line to cover.",
        "s_rebound": "It was a rebound.",
    },
    "es": {
        "res": {"WOODWORK": "¡Al palo!", "DISALLOWED": "Entra, pero el VAR lo anula por {why}."},
        "c_res": {"WOODWORK": "¡{p} estrella el balón en el palo!", "DISALLOWED": "¡Entra... pero el VAR dice NO!"},
        "var_reason": {"OFFSIDE": "fuera de juego", "FOUL": "falta en la jugada previa", "HANDBALL": "mano"},
        "var_stands": " El VAR lo revisa: el gol sube al marcador.", "c_var_stands": " (revisión del VAR: ¡gol válido!)",
        "own_goal": "{o} mete en su propia portería el balón de {p}. {score}.",
        "c_own_goal": "¡GOL EN PROPIA PUERTA! {o} bate a su propio portero. {score}",
        "cross_ok": "{p} centra desde {zone} y {r} lo ataca en el área (dificultad {diff}/100).",
        "cross_cleared": "{o} despeja el centro de {p} desde {zone}.",
        "claimed": "{o} sale y atrapa el balón de {p} al área.",
        "c_cross_ok": "{p} pone el centro... ¡ahí está {r}!", "c_claimed": "{o} la atrapa por alto.",
        "rebound": "{p} reacciona primero al rechace, a {len} m: {xg} xG. {res}", "c_rebound": "¡Rechace! {p} llega... ",
        "injury": "{p} está en el suelo lesionado y necesita asistencia.", "c_injury": "{p} está en el suelo, entran las asistencias.",
        "sub_why": {"injury": " Cambio obligado: {o} no puede seguir."},
        "a_added_time": "El cuarto árbitro indica {v} minutos de añadido.",
        "a_chasing": "{t} se lanza hacia arriba: adelanta líneas, presiona más y juega más directo.",
        "a_protecting": "{t} se repliega: retrocede y baja el ritmo del partido.",
        "s_own_goal": "{o} metió el balón en su propia portería tras el envío de {p}.",
        "s_var_no": "{p} marcó desde {len} m, pero el VAR lo anuló por {why}.",
        "s_var_ok": "El VAR lo revisó y el gol fue válido.",
        "s_woodwork": "{p} estrelló el balón en el palo desde {len} m ({xg} xG).",
        "s_injury": "{p} cayó lesionado y necesitó asistencia.",
        "s_reshuffle": "{m} retrocede a la línea defensiva para cubrir el hueco.",
        "s_rebound": "Fue a la segunda.",
    },
    "ja": {
        "res": {"WOODWORK": "ポストに当たった！", "DISALLOWED": "ネットを揺らすも、VARで{why}のため取り消し。"},
        "c_res": {"WOODWORK": "{p}のシュートはポストに！", "DISALLOWED": "入った…しかしVARでノーゴール！"},
        "var_reason": {"OFFSIDE": "オフサイド", "FOUL": "攻撃中のファウル", "HANDBALL": "ハンド"},
        "var_stands": "VARチェックの結果、ゴールは認められた。", "c_var_stands": "（VAR確認：ゴールは有効！）",
        "own_goal": "{p}のボールを{o}が自陣ゴールに入れてしまう。{score}。",
        "c_own_goal": "オウンゴール！{o}が自らのゴールに…{score}",
        "cross_ok": "{p}が{zone}からクロス、{r}がエリア内で合わせにいく（難易度{diff}/100）。",
        "cross_cleared": "{p}の{zone}からのクロスは{o}がクリア。",
        "claimed": "{o}が飛び出して{p}のボールをキャッチ。",
        "c_cross_ok": "{p}がクロス…{r}が待っている！", "c_claimed": "{o}が空中でがっちりキャッチ。",
        "rebound": "{p}がこぼれ球にいち早く反応、{len}mから：xG {xg}。{res}", "c_rebound": "こぼれ球！{p}が詰める…",
        "injury": "{p}が負傷で倒れ、治療を受ける。", "c_injury": "{p}が倒れている、メディカルスタッフが入る。",
        "sub_why": {"injury": "{o}はプレー続行不可能、やむを得ない交代。"},
        "a_added_time": "第4審判が{v}分のアディショナルタイムを表示。",
        "a_chasing": "{t}が前に出る：ラインを上げ、プレスを強め、より直線的に攻める。",
        "a_protecting": "{t}が引いて構える：ラインを下げてペースを落とす。",
        "s_own_goal": "{p}のボールを{o}が自陣ゴールへ入れてしまった。",
        "s_var_no": "{p}が{len}mから決めたが、VARで{why}のため取り消された。",
        "s_var_ok": "VARのチェックを経てゴールが認められた。",
        "s_woodwork": "{p}の{len}mからのシュート（xG {xg}）はポストを叩いた。",
        "s_injury": "{p}が負傷し、治療を受けた。",
        "s_reshuffle": "{m}が最終ラインに下がって穴を埋める。",
        "s_rebound": "こぼれ球からの一撃。",
    },
}
for _lang, _extra in MATCH_T.items():
    for _k, _v in _extra.items():
        if isinstance(_v, dict) and isinstance(T[_lang].get(_k), dict):
            T[_lang][_k].update(_v)
        else:
            T[_lang][_k] = _v


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
        "ezone": _zone(L, team, ctx.right_team, loc["end_x"], loc["end_y"]),
        "score": score, "min": int(ev["minute"]),
        "sp": L["sp"].get(ev.get("set_piece"), ""),
        "why": L["var_reason"].get((ev.get("var") or {}).get("reason"), ""),
    }
    reasons = ev["impact_reasons"]
    sp, restart = ev.get("set_piece"), ev.get("restart")
    tags = ev.get("tags") or []
    delivery = "delivery" in tags

    if t == "SUBSTITUTION":
        line = L["sub"].format(**f)
        why = next((L["sub_why"][x] for x in tags if x in L["sub_why"]), "")
        line += why.format(o=ev["player_off"])
        return {"analyst": line, "casual": line, "player_cam": _player_cam(L, ev, ctx, line)}
    if t == "INJURY":
        return {"analyst": L["injury"].format(**f), "casual": L["c_injury"].format(**f),
                "player_cam": _player_cam(L, ev, ctx, L["injury"].format(**f))}

    if t == "PASS" and o == "OWN_GOAL":
        analyst, casual = L["own_goal"].format(**f), L["c_own_goal"].format(**f)
    elif t == "PASS" and o == "COMPLETE" and delivery:
        analyst = L["sp_cross" if sp else "cross_ok"].format(**f)
        casual = L["c_cross" if sp else "c_cross_ok"].format(**f)
    elif t == "PASS" and delivery and "claimed" in tags:
        analyst, casual = L["claimed"].format(**f), L["c_claimed"].format(**f)
    elif t == "PASS" and delivery:
        analyst, casual = L["sp_cleared" if sp else "cross_cleared"].format(**f), L["c_cleared"].format(**f)
    elif t == "PASS" and o == "COMPLETE" and sp:
        analyst = L["sp_pass"].format(**f)
        casual = L["c_sp_pass"][sp].format(**f)
    elif t == "PASS" and o == "OUT":
        analyst, casual = L["out"].format(**f), L["c_out"].format(**f)
    elif t == "PASS" and o == "OFFSIDE":
        analyst, casual = L["offside"].format(**f), L["c_offside"].format(**f)
    elif t == "PASS" and o == "COMPLETE":
        forward = (m["forward_gain_m"] or 0) >= 5 and (m["players_bypassed"] or 0) > 0
        analyst = L["pass_ok" if forward else "pass_short"].format(**f)
        if "line_breaking_pass" in reasons:
            analyst += L["why_line"].format(**f)
            casual = L["c_pass_lb"].format(**f)
        else:
            casual = L["c_pass_good" if (m["pass_difficulty"] or 0) >= 60 else "c_pass"].format(**f)
    elif t == "PASS" and restart == "CORNER":
        f["zone"] = _zone(L, team, ctx.right_team, loc["end_x"], loc["end_y"])
        analyst, casual = L["pass_int_out"].format(**f), L["c_int_out"].format(**f)
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
            if "high_press_turnover" in reasons and not restart:
                f["gd"] = _goal_distance(team, ctx.right_team, loc["end_x"], loc["end_y"])
                f["ot"] = names[team]
                analyst += L["why_press" if f["gd"] <= 45 else "why_recover"].format(**f)
        else:
            analyst = L["pen_foul" if restart == "PENALTY" else "foul"].format(**f)
            casual = L["c_pen_foul" if restart == "PENALTY" else "c_foul"].format(**f)
            if ev["card"] == "YELLOW":
                analyst += L["card_y"]; casual += L["c_card_y"]
            elif ev["card"] == "RED":
                analyst += L["card_r"].format(**f); casual += L["c_card_r"]
    else:  # SHOT
        f["res"] = L["res"][o].format(**f)
        kind = ("pen_shot" if sp == "PENALTY" else "fk_shot" if sp == "FREE_KICK" else
                "header" if ev.get("body_part") == "HEAD" else "rebound" if "rebound" in tags else "shot")
        analyst = L[kind].format(**f)
        lead = {"pen_shot": "c_pen_shot", "fk_shot": "c_fk_shot", "header": "c_header", "rebound": "c_rebound"}.get(kind)
        casual = (L[lead].format(**f) if lead else "") + L["c_res"][o].format(**f)
        if (ev.get("var") or {}).get("decision") == "GOAL_STANDS":
            analyst += L["var_stands"]
            casual += L["c_var_stands"]
        if o == "DISALLOWED":
            pass
        elif "big_chance" in reasons:
            analyst += L["why_big"].format(**f)
        else:
            txg, ts = ctx.team_xg_shots[team]
            analyst += L["why_shot"].format(txg=f"{txg:.2f}", ts=ts, t=f["t"])

    if restart and restart != "PENALTY":
        analyst += L["restart"].format(sp_r=L["sp_r"][restart], rt=names[ev["restart_team"]])
        casual += L["c_restart"][restart]
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
    if ev.get("restart") == "PENALTY":
        return casual + (L["fan_pen_for"] if ev["restart_team"] == fav else L["fan_pen_against"])
    if t == "SHOT" and o == "GOAL":
        return (L["fan_goal_for"] if ours else L["fan_goal_against"]) + casual
    if o == "OWN_GOAL":
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
    if t == "PASS" and o == "COMPLETE" and e.get("set_piece"):
        return L["b_sp"].format(p=e["player"], r=e["receiver"], sp=L["sp"][e["set_piece"]])
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
    opp = ctx.away if team == ctx.home else ctx.home
    f = {"p": ev["player"], "o": ev["opponent"] or ev["player_off"], "t": names[team], "ot": names[opp],
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
    elif o == "OWN_GOAL":
        parts.append(L["s_own_goal"].format(**f))
        own = ev["score"]["home" if team == ctx.home else "away"]
        their = ev["score"]["away" if team == ctx.home else "home"]
        key = "s_level" if own == their else "s_lead" if own - their == 1 else "s_extend" if own > their else "s_back"
        parts.append(L[key].format(**f))
    elif t == "SHOT" and o == "DISALLOWED":
        parts.append(L["s_var_no"].format(**f, why=L["var_reason"][ev["var"]["reason"]]))
    elif t == "SHOT" and o == "WOODWORK":
        parts.append(L["s_woodwork"].format(**f))
    elif t == "INJURY":
        parts.append(L["s_injury"].format(**f))
    elif t == "SHOT":
        if o == "SAVED":
            parts.append(L["s_save"].format(**f))
            keeper = lines.get((ctx.away if team == ctx.home else ctx.home, ev["opponent"])) or {}
            parts.append(L["s_ctx_save"].format(o=ev["opponent"], n=keeper.get("saves", 1)))
        elif o == "BLOCKED":
            parts.append(L["s_block"].format(**f))
        else:
            parts.append(L["s_miss"].format(**f))
    if ev.get("restart") == "PENALTY":
        parts += [L["s_pen"].format(**f), L["s_ctx_pen"]]
    if ev.get("card"):
        if ev["card"] == "YELLOW":
            parts += [L["s_card_y"].format(**f), L["s_ctx_card_y"].format(**f)]
        else:
            parts += [L["s_card_r"].format(**f), L["s_ctx_card_r"].format(**f)]
            if ev.get("reshuffle"):
                parts.append(L["s_reshuffle"].format(m=ev["reshuffle"]["player"]))
    elif t == "SUBSTITUTION":
        off = lines.get((team, ev["player_off"])) or {}
        parts.append(L["s_sub"].format(**f))
        parts.append(L["s_ctx_sub"].format(o=ev["player_off"], min=off.get("minutes", int(ev["minute"])),
                                           rating=off.get("rating") or "-", touches=off.get("touches", 0),
                                           km=off.get("distance_km", 0)))
        why = next((L["sub_why"][x] for x in ev.get("tags") or [] if x in L["sub_why"]), "")
        if why:
            parts.append(why.strip().format(o=ev["player_off"]))
    if t == "SHOT":
        origin = ev.get("set_piece") or next((e["set_piece"] for e in reversed(buildup) if e.get("set_piece")), None)
        if origin:
            parts.append(L["s_from"][origin])
        if ev.get("body_part") == "HEAD":
            parts.append(L["s_head"])
        if "rebound" in (ev.get("tags") or []):
            parts.append(L["s_rebound"])
        if (ev.get("var") or {}).get("decision") == "GOAL_STANDS":
            parts.append(L["s_var_ok"])
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
    if th["corners"] + ta["corners"]:
        parts.append(L["r_set"].format(hc=th["corners"], ac=ta["corners"], hf=th["fouls"], af=ta["fouls"]))
    if abs(r["momentum_avg"]) >= 15:
        parts.append(L["r_mom"][r["kind"]].format(t=names[h if r["momentum_avg"] > 0 else a]))
    b = r["best_player"]
    if b:
        keys = [k for k in ("goals", "assists", "shots", "tackles_won", "interceptions", "passes_completed") if b.get(k)][:3]
        one = L.get("items1", {})  # singular forms, where the language has them
        items = ("、" if lang == "ja" else ", ").join(one[k] if b[k] == 1 and k in one else L["items"][k].format(n=b[k])
                                                     for k in keys)
        parts.append(L["r_best"].format(name=b["name"], t=names[b["team"]], r=b["rating"], items=items))
    sep = "" if lang == "ja" else " "
    return sep.join(parts)
