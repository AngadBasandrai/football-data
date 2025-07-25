import os
import json
import codecs
import math
import pandas as pd
from collections import defaultdict
from statistics import mean, stdev

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
    "passing_accuracy": 0.55,
    "avg_passes_per_game": 0.32,
    "through_pass_accuracy": 0.06,
    "freekick_accuracy": 0.04,
    "assists_per_game": 0.18,
    "passing_consistency": 0.10,
    "turnover_rate": -0.01,
}

PRIOR_GAMES = 20

def calculate_consistency(attempts_per_match, success_per_match):
    accs = []
    for mid in attempts_per_match:
        att = attempts_per_match[mid]
        suc = success_per_match.get(mid, 0)
        if att > 0:
            accs.append(suc / att)
    if len(accs) < 2:
        return 1.0
    mean_acc = sum(accs) / len(accs)
    variance = sum((a - mean_acc) ** 2 for a in accs) / (len(accs) - 1)
    stddev = math.sqrt(variance)
    return max(0.0, 1.0 - stddev / mean_acc if mean_acc else 0.0)

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
    name = p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "").strip()}'
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

# === Collect raw component values ===
print("Calculating ratings...")
component_values = defaultdict(list)
player_components = {}

for pid, s in stats.items():
    games_played = len(s["matches"])
    if games_played == 0:
        continue

    raw_pass_acc = s["pass_success"] / s["pass_total"] if s["pass_total"] > 0 else 0
    raw_through_acc = s["through_pass_success"] / s["through_pass_total"] if s["through_pass_total"] > 0 else 0
    raw_freekick_acc = s["freekick_pass_success"] / s["freekick_pass_total"] if s["freekick_pass_total"] > 0 else 0
    raw_assists_pg = s["assist_total"] / games_played
    raw_avg_pg = s["pass_total"] / games_played
    raw_consistency = calculate_consistency(s["pass_attempts_per_match"], s["pass_success_per_match"])
    raw_turnover_rate = 1 - raw_pass_acc

    components = {
        "pass_acc": raw_pass_acc,
        "through_acc": raw_through_acc,
        "freekick_acc": raw_freekick_acc,
        "assists_pg": raw_assists_pg,
        "avg_pg": raw_avg_pg,
        "consistency": raw_consistency,
        "turnover_rate": raw_turnover_rate,
    }

    for k, v in components.items():
        component_values[k].append(v)
    player_components[pid] = (components, games_played)

component_means = {k: mean(v) for k, v in component_values.items()}
component_stdevs = {k: stdev(v) if len(v) > 1 else 1.0 for k, v in component_values.items()}

key_mapping = {
    "pass_acc": "passing_accuracy",
    "avg_pg": "avg_passes_per_game",
    "through_acc": "through_pass_accuracy",
    "freekick_acc": "freekick_accuracy",
    "assists_pg": "assists_per_game",
    "consistency": "passing_consistency",
    "turnover_rate": "turnover_rate",
}

output_lines = ["Player,PrimaryPosition,Games," + ",".join(component_values.keys()) + ",Rating"]

for pid, (components, games_played) in player_components.items():
    shrinkage = games_played / (games_played + PRIOR_GAMES)
    z_components = {
        k: ((components[k] - component_means[k]) / (component_stdevs[k] or 1.0)) * shrinkage
        for k in components
    }

    score = sum(WEIGHTS.get(key_mapping.get(k, k), 0) * z_components[k] for k in z_components)
    scaled_rating = min(100.0, max(0.0, 80 + score * 10))

    output_lines.append(",".join([
        csv_escape(players.get(pid, f"Player {pid}")),
        primary_position.get(pid, "Unknown"),
        str(games_played),
    ] + [f"{components[k]:.3f}" for k in component_values] + [f"{scaled_rating:.2f}"]))

print(f"Writing output to {OUTPUT_FILE} ...")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print("Done.")
