import os
import json
import codecs
import math
import pandas as pd
from collections import defaultdict

# === SETTINGS ===
DATA_DIR = "./"
EVENTS_DIR = os.path.join(DATA_DIR, "events")
PLAYERS_FILE = os.path.join(DATA_DIR, "data/players.json")
PRIMARY_POS_FILE = os.path.join(DATA_DIR, "positions/player_primary_positions.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "ratings/player_passing_ratings.csv")

PASS_TAG_ID = 1801
THROUGH_PASS_TAG_ID = 901
ASSIST_TAG_ID = 302
FREE_KICK_TAG_ID = 801

WEIGHTS = {
    "passing_accuracy": 0.45,
    "avg_passes_per_game": 0.2,
    "through_pass_accuracy": 0.06,
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
    "through_pass_acc": (0.55, 15),
}

def smooth_ratio(success, total, prior_mean, prior_weight):
    return (success + prior_mean * prior_weight) / (total + prior_weight)

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

def csv_escape(s):
    s = str(s)
    return f'"{s.replace("\"", "\"\"")}"' if "," in s or '"' in s else s

# === Load players ===
print("Loading players...")
with open(PLAYERS_FILE, encoding="utf-8") as f:
    players_raw = json.load(f)

players = {}
for p in players_raw:
    pid = p["wyId"]
    name = p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "")}'.strip()
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except Exception:
            pass
    players[pid] = name

print("Loading primary positions...")
position_df = pd.read_csv(PRIMARY_POS_FILE)
primary_position = dict(zip(position_df.playerId, position_df.best_fit_role))

# === Initialize stats ===
stats = defaultdict(lambda: {
    "pass_total": 0,
    "pass_success": 0,
    "through_pass_total": 0,
    "through_pass_success": 0,
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

        if THROUGH_PASS_TAG_ID in tags:
            s["through_pass_total"] += 1
            if PASS_TAG_ID in tags:
                s["through_pass_success"] += 1

        if FREE_KICK_TAG_ID in tags:
            s["freekick_pass_total"] += 1
            if PASS_TAG_ID in tags:
                s["freekick_pass_success"] += 1

        if ASSIST_TAG_ID in tags:
            s["assist_total"] += 1

print(f"Processed {total_events} events.")

# === Compute normalization baselines ===
max_avg_pg = 0
max_assists_pg = 0

for pid, s in stats.items():
    games = len(s["matches"])
    if games == 0:
        continue
    avg_pg = s["pass_total"] / games
    assists_pg = s["assist_total"] / games
    max_avg_pg = max(max_avg_pg, avg_pg)
    max_assists_pg = max(max_assists_pg, assists_pg)

# === Rating calculation ===
print("Calculating ratings...")
output_lines = ["Player,PrimaryPosition,Games,PassAcc,AvgPassGame,throughPassAcc,FreeKickAcc,AssistsPerGame,Consistency,TurnoverRate,Rating"]
player_data = []

for pid, s in stats.items():
    name = players.get(pid, f"Player {pid}")
    pos = primary_position.get(pid, "Unknown")
    games_played = len(s["matches"])
    if games_played == 0:
        continue

    pass_acc = smooth_ratio(s["pass_success"], s["pass_total"], *SMOOTH_PRIORS["pass_acc"])
    through_acc = smooth_ratio(s["through_pass_success"], s["through_pass_total"], *SMOOTH_PRIORS["through_pass_acc"])
    freekick_acc = smooth_ratio(s["freekick_pass_success"], s["freekick_pass_total"], *SMOOTH_PRIORS["freekick_acc"])
    turnover_rate = 1 - pass_acc
    avg_pg = s["pass_total"] / games_played
    assists_pg = s["assist_total"] / games_played
    consistency = calculate_consistency(s["pass_attempts_per_match"], s["pass_success_per_match"])
    norm_avg_pg = avg_pg / max_avg_pg if max_avg_pg else 0
    norm_assists = assists_pg / max_assists_pg if max_assists_pg else 0

    rating = (
        WEIGHTS["passing_accuracy"] * pass_acc +
        WEIGHTS["avg_passes_per_game"] * norm_avg_pg +
        WEIGHTS["through_pass_accuracy"] * through_acc +
        WEIGHTS["freekick_accuracy"] * freekick_acc +
        WEIGHTS["assists_per_game"] * norm_assists +
        WEIGHTS["passing_consistency"] * consistency +
        WEIGHTS["turnover_rate"] * turnover_rate
    )

    if games_played < 5:
        game_bonus = MIN_GAME_PENALTY
    elif games_played >= GAMES_FOR_MAX_EFFECT:
        game_bonus = MAX_GAME_BONUS
    else:
        game_bonus = MAX_GAME_BONUS * (games_played / GAMES_FOR_MAX_EFFECT)

    rating += WEIGHTS["games_played_bonus"] * game_bonus
    scaled_rating = min(100.0, max(0.0, rating * 100))

    output_lines.append(",".join([
        csv_escape(name),
        pos,
        str(games_played),
        f"{pass_acc:.3f}",
        f"{avg_pg:.2f}",
        f"{through_acc:.3f}",
        f"{freekick_acc:.3f}",
        f"{assists_pg:.3f}",
        f"{consistency:.3f}",
        f"{turnover_rate:.3f}",
        f"{scaled_rating:.1f}"
    ]))

print(f"Writing output to {OUTPUT_FILE} ...")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for line in output_lines:
        f.write(line + "\n")

print("Done.")
