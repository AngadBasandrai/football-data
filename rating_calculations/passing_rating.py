import os
import json
import codecs
from collections import defaultdict
import math

# === SETTINGS ===
DATA_DIR = "./"  # Set your dataset root directory here
EVENTS_DIR = os.path.join(DATA_DIR, "events")
PLAYERS_FILE = os.path.join(DATA_DIR, "data/players.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "ratings/player_passing_ratings.csv")

PASS_TAG_ID = 1801
SMART_PASS_TAG_ID = 901
ASSIST_TAG_ID = 302
FREE_KICK_TAG_ID = 801

ROLE_MAP = {
    "GK": "GK", "GKP": "GK",
    "DF": "DF", "DEF": "DF",
    "MD": "MD", "MID": "MD",
    "FW": "FW", "FWD": "FW",
}

WEIGHTS = {
    "passing_accuracy": 0.45,
    "avg_passes_per_game": 0.2,
    "smart_pass_accuracy": 0.06,
    "freekick_accuracy": 0.04,
    "assists_per_game": 0.1,
    "passing_consistency": 0.23,
    "turnover_rate": -0.05,
    "games_played_bonus": 0.3,
}

MAX_GAME_BONUS = 0.30
MIN_GAME_PENALTY = -0.25
GAMES_FOR_MAX_EFFECT = 30

SMOOTH_PRIORS = {
    "pass_acc": (0.75, 30),
    "freekick_acc": (0.7, 10),
    "smart_pass_acc": (0.55, 15),
}

def smooth_ratio(success, total, prior_mean, prior_weight):
    return (success + prior_mean * prior_weight) / (total + prior_weight)

print("Loading players...")
with open(PLAYERS_FILE, encoding="utf-8") as f:
    players_raw = json.load(f)

players = {}
player_roles = {}
for p in players_raw:
    pid = p["wyId"]
    name = p.get("shortName") or f'{p.get("firstName","")} {p.get("lastName","")}'
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except Exception:
            pass
    players[pid] = name
    role_code = p.get("role", {}).get("code3") or p.get("role", {}).get("code2") or "Unknown"
    role_code = role_code.upper()
    role_code = ROLE_MAP.get(role_code, "Unknown")
    player_roles[pid] = role_code

print(f"Loaded {len(players)} players.")

stats = defaultdict(lambda: {
    "pass_total": 0,
    "pass_success": 0,
    "smart_pass_total": 0,
    "smart_pass_success": 0,
    "freekick_pass_total": 0,
    "freekick_pass_success": 0,
    "assist_total": 0,
    "matches": set(),
    "pass_attempts_per_match": defaultdict(int),
    "pass_success_per_match": defaultdict(int),
})

print("Processing event files...")
event_files = [f for f in os.listdir(EVENTS_DIR) if f.startswith("events_") and f.endswith(".json")]
total_events = 0

for ef in event_files:
    path = os.path.join(EVENTS_DIR, ef)
    with open(path, encoding="utf-8") as f:
        events = json.load(f)

    for e in events:
        total_events += 1
        if e.get("eventName") != "Pass":
            continue

        pid = e.get("playerId")
        mid = e.get("matchId")
        if pid is None or mid is None or pid not in players:
            continue

        s = stats[pid]
        s["matches"].add(mid)
        s["pass_total"] += 1
        s["pass_attempts_per_match"][mid] += 1

        tags = [tag.get("id") for tag in e.get("tags", [])]

        if PASS_TAG_ID in tags:
            s["pass_success"] += 1
            s["pass_success_per_match"][mid] += 1

        if SMART_PASS_TAG_ID in tags:
            s["smart_pass_total"] += 1
            if PASS_TAG_ID in tags:
                s["smart_pass_success"] += 1

        if FREE_KICK_TAG_ID in tags:
            s["freekick_pass_total"] += 1
            if PASS_TAG_ID in tags:
                s["freekick_pass_success"] += 1

        if ASSIST_TAG_ID in tags:
            s["assist_total"] += 1

print(f"Processed {total_events} events.")

max_avg_pg = 0
max_assists_pg_by_role = defaultdict(lambda: 0)

for pid, s in stats.items():
    games = len(s["matches"])
    if games == 0:
        continue
    role = player_roles.get(pid, "Unknown")
    avg_pg = s["pass_total"] / games
    assists_pg = s["assist_total"] / games
    max_avg_pg = max(max_avg_pg, avg_pg)
    max_assists_pg_by_role[role] = max(max_assists_pg_by_role[role], assists_pg)

def calculate_consistency(attempts_per_match, success_per_match):
    accs = []
    for mid in attempts_per_match:
        att = attempts_per_match[mid]
        suc = success_per_match.get(mid, 0)
        if att > 0:
            accs.append(suc / att)
    if len(accs) < 2:
        return 1.0
    mean = sum(accs) / len(accs)
    variance = sum((a - mean) ** 2 for a in accs) / (len(accs) - 1)
    stddev = math.sqrt(variance)
    return max(0.0, 1.0 - stddev / mean if mean else 0.0)

print("Calculating ratings...")
output_lines = ["Player,Role,Games,PassAcc,AvgPassGame,SmartPassAcc,FreeKickAcc,AssistsPerGame,Consistency,TurnoverRate,Rating"]

player_data = []
max_rating = 0

for pid, s in stats.items():
    name = players.get(pid, f"Player {pid}")
    role = player_roles.get(pid, "Unknown")
    games_played = len(s["matches"])
    if games_played == 0:
        continue

    pass_acc = smooth_ratio(s["pass_success"], s["pass_total"], *SMOOTH_PRIORS["pass_acc"])
    smart_acc = smooth_ratio(s["smart_pass_success"], s["smart_pass_total"], *SMOOTH_PRIORS["smart_pass_acc"])
    freekick_acc = smooth_ratio(s["freekick_pass_success"], s["freekick_pass_total"], *SMOOTH_PRIORS["freekick_acc"])
    turnover_rate = 1 - pass_acc
    avg_pg = s["pass_total"] / games_played
    assists_pg = s["assist_total"] / games_played
    consistency = calculate_consistency(s["pass_attempts_per_match"], s["pass_success_per_match"])
    norm_avg_pg = avg_pg / max_avg_pg if max_avg_pg else 0
    max_assist_for_role = max_assists_pg_by_role[role] or 1
    norm_assists = assists_pg / max_assist_for_role

    rating = 0
    rating += WEIGHTS["passing_accuracy"] * pass_acc
    rating += WEIGHTS["avg_passes_per_game"] * norm_avg_pg
    rating += WEIGHTS["smart_pass_accuracy"] * smart_acc
    rating += WEIGHTS["freekick_accuracy"] * freekick_acc
    rating += WEIGHTS["assists_per_game"] * norm_assists
    rating += WEIGHTS["passing_consistency"] * consistency
    rating += WEIGHTS["turnover_rate"] * turnover_rate

    if games_played < 5:
        game_bonus = MIN_GAME_PENALTY
    elif games_played >= GAMES_FOR_MAX_EFFECT:
        game_bonus = MAX_GAME_BONUS
    else:
        game_bonus = MAX_GAME_BONUS * (games_played / GAMES_FOR_MAX_EFFECT)

    rating += WEIGHTS["games_played_bonus"] * game_bonus
    raw_rating = max(0, rating)  # Remove upper cap of 1.0 to preserve scaling
    max_rating = max(max_rating, raw_rating)

    player_data.append((name, role, games_played, pass_acc, avg_pg, smart_acc, freekick_acc, assists_pg, consistency, turnover_rate, raw_rating))

# Scale all ratings so best player is 99
for data in player_data:
    name, role, games, pa, apg, sa, fka, asp, cons, tor, raw = data
    scaled = min(100.000, max(0.000, raw * 100))
    def csv_escape(s):
        s = str(s)
        return f'"{s.replace("\"", "\"\"")}"' if "," in s or '"' in s else s
    output_lines.append(",".join([
        csv_escape(name),
        role,
        str(games),
        f"{pa:.3f}",
        f"{apg:.2f}",
        f"{sa:.3f}",
        f"{fka:.3f}",
        f"{asp:.3f}",
        f"{cons:.3f}",
        f"{tor:.3f}",
        f"{scaled:.1f}",
    ]))

print(f"Writing output to {OUTPUT_FILE} ...")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for line in output_lines:
        f.write(line + "\n")

print("Done.")
