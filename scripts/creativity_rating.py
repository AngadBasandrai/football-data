import os
import json
import math
import codecs
import pandas as pd
from collections import defaultdict
from statistics import mean, stdev

# === SETTINGS ===
DATA_DIR = "./"
EVENTS_DIR = os.path.join(DATA_DIR, "events")
PLAYERS_FILE = os.path.join(DATA_DIR, "data/players.json")
PRIMARY_POS_FILE = os.path.join(DATA_DIR, "positions/player_primary_positions.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "ratings/player_creativity_rating.csv")

# === TAG IDs ===
GOAL_TAG = 101
ASSIST_TAG = 301
KEY_PASS_TAG = 302
COUNTERATTACK_TAG = 1901
OPPORTUNITY_TAG = 201
FEINT_TAG = 1301
ANTICIPATED_TAG = 601

# === RATING WEIGHTS (tunable) ===
WEIGHTS = {
    "acceleration_pg": 0.04,
    "acceleration_acc": 0.04,
    "launch_pg": 0.02,
    "launch_acc": 0.02,
    "smartpass_pg": 0.10,
    "smartpass_acc": 0.08,
    "throughball_pg": 0.08,
    "throughball_acc": 0.07,
    "shots_pg": 0.08,
    "goals_pg": 0.10,
    "assists_pg": 0.11,
    "keypasses_pg": 0.09,
    "counterattacks_pg": 0.05,
    "opportunities_pg": 0.05,
    "feints_pg": 0.07,
    "anticipated_rate": -0.06,
    "consistency": 0.02
}

SUCCESS_TAG_ID = 1801
DUEL_EVENTS = {
    "Ground attacking duel",
    "Ground defending duel",
    "Ground loose ball duel",
    "Air duel",
}

# === UTILS ===
def smooth_ratio(success, total, prior_mean=0.4, prior_weight=20):
    return (success + prior_mean * prior_weight) / (total + prior_weight)

def calculate_consistency(metric_per_match):
    values = list(metric_per_match.values())
    if len(values) < 2:
        return 1.0
    avg = mean(values)
    stddev = stdev(values)
    return max(0.0, 1 - stddev / avg) if avg else 0.0

def csv_escape(s):
    s = str(s)
    return f'"{s.replace("\"", "\"\"")}"' if "," in s or '"' in s else s

# === Load Players ===
print("Loading players...")
with open(PLAYERS_FILE, encoding="utf-8") as f:
    players_raw = json.load(f)

players = {}
for p in players_raw:
    pid = p["wyId"]
    name = p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "")}'
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except Exception:
            pass
    players[pid] = name

print(f"Loaded {len(players)} players.")

# === Load Positions ===
print("Loading primary positions...")
position_df = pd.read_csv(PRIMARY_POS_FILE)
primary_position = dict(zip(position_df.playerId, position_df.best_fit_role))

# === Initialize Stats ===
print("Processing event files...")
stats = defaultdict(lambda: {
    "matches": set(),
    "acceleration_total": 0,
    "acceleration_success": 0,
    "launch_total": 0,
    "launch_success": 0,
    "smartpass_total": 0,
    "smartpass_success": 0,
    "throughball_total": 0,
    "throughball_success": 0,
    "shots": 0,
    "goals": 0,
    "assists": 0,
    "keypasses": 0,
    "counterattacks": 0,
    "opportunities": 0,
    "feints": 0,
    "anticipated": 0,
    "duels_total": 0,
    "per_match_metrics": defaultdict(lambda: defaultdict(int)),
})

event_files = [f for f in os.listdir(EVENTS_DIR) if f.startswith("events_") and f.endswith(".json")]

for file in event_files:
    with open(os.path.join(EVENTS_DIR, file), encoding="utf-8") as f:
        events = json.load(f)

    for e in events:
        pid = e.get("playerId")
        mid = e.get("matchId")
        if pid not in players or not mid:
            continue

        ename = e.get("eventName")
        sname = e.get("subEventName")
        tags = {t["id"] for t in e.get("tags", [])}

        s = stats[pid]
        s["matches"].add(mid)
        pm = s["per_match_metrics"][mid]

        # === Acceleration ===
        if ename == "Others on the ball" and sname == "Acceleration":
            s["acceleration_total"] += 1
            pm["acceleration"] += 1
            if SUCCESS_TAG_ID in tags:
                s["acceleration_success"] += 1

        # === Launch ===
        if ename == "Pass" and sname == "Launch":
            s["launch_total"] += 1
            pm["launch"] += 1
            if SUCCESS_TAG_ID in tags:
                s["launch_success"] += 1

        # === Smart Pass ===
        if ename == "Pass" and sname == "Smart pass":
            s["smartpass_total"] += 1
            pm["smartpass"] += 1
            if SUCCESS_TAG_ID in tags:
                s["smartpass_success"] += 1

        # === Through Ball ===
        if 901 in tags:
            s["throughball_total"] += 1
            pm["throughball"] += 1
            if SUCCESS_TAG_ID in tags:
                s["throughball_success"] += 1

        # === Shot, Goal, Assist ===
        if ename == "Shot":
            s["shots"] += 1
            pm["shots"] += 1
            if GOAL_TAG in tags:
                s["goals"] += 1
                pm["goals"] += 1

        if ASSIST_TAG in tags:
            s["assists"] += 1
            pm["assists"] += 1

        if KEY_PASS_TAG in tags:
            s["keypasses"] += 1
            pm["keypasses"] += 1

        if COUNTERATTACK_TAG in tags:
            s["counterattacks"] += 1
            pm["counterattacks"] += 1

        if OPPORTUNITY_TAG in tags:
            s["opportunities"] += 1
            pm["opportunities"] += 1

        if FEINT_TAG in tags:
            s["feints"] += 1
            pm["feints"] += 1

        if ANTICIPATED_TAG in tags:
            s["anticipated"] += 1
            pm["anticipated"] += 1

        if sname in DUEL_EVENTS:
            s["duels_total"] += 1
            pm["duels"] += 1

# === Rating Calculation ===
print("Calculating creativity ratings...")
ratings = {}
output_lines = ["Player,PrimaryPosition,Games," + ",".join(WEIGHTS.keys()) + ",Rating"]

component_values = defaultdict(list)
player_components = {}

for pid, s in stats.items():
    games = len(s["matches"])
    if games < 3:
        continue

    acc_pg = s["acceleration_total"] / games
    acc_acc = smooth_ratio(s["acceleration_success"], s["acceleration_total"])
    launch_pg = s["launch_total"] / games
    launch_acc = smooth_ratio(s["launch_success"], s["launch_total"])
    smart_pg = s["smartpass_total"] / games
    smart_acc = smooth_ratio(s["smartpass_success"], s["smartpass_total"])
    through_pg = s["throughball_total"] / games
    through_acc = smooth_ratio(s["throughball_success"], s["throughball_total"])
    shots_pg = s["shots"] / games
    goals_pg = s["goals"] / games
    assists_pg = s["assists"] / games
    keypasses_pg = s["keypasses"] / games
    counter_pg = s["counterattacks"] / games
    opportunities_pg = s["opportunities"] / games
    feints_pg = s["feints"] / games
    anticipated_rate = (s["anticipated"] / s["duels_total"]) if s["duels_total"] > 0 else 0

    match_metric_totals = {m: sum(v.values()) for m, v in s["per_match_metrics"].items()}
    consistency = calculate_consistency(match_metric_totals)

    components = {
        "acceleration_pg": acc_pg,
        "acceleration_acc": acc_acc,
        "launch_pg": launch_pg,
        "launch_acc": launch_acc,
        "smartpass_pg": smart_pg,
        "smartpass_acc": smart_acc,
        "throughball_pg": through_pg,
        "throughball_acc": through_acc,
        "shots_pg": shots_pg,
        "goals_pg": goals_pg,
        "assists_pg": assists_pg,
        "keypasses_pg": keypasses_pg,
        "counterattacks_pg": counter_pg,
        "opportunities_pg": opportunities_pg,
        "feints_pg": feints_pg,
        "anticipated_rate": anticipated_rate,
        "consistency": consistency,
    }

    for k in components:
        component_values[k].append(components[k])
    player_components[pid] = (components, games)

# === Normalize and score ===
component_means = {k: mean(v) for k, v in component_values.items()}
component_stdevs = {k: stdev(v) if len(v) > 1 else 1 for k, v in component_values.items()}

for pid, (components, games) in player_components.items():
    prior_games = 15
    shrinkage = games / (games + prior_games)
    z_components = {
        k: ((components[k] - component_means[k]) / (component_stdevs[k] or 1)) * shrinkage
        for k in WEIGHTS
    }

    score = sum(WEIGHTS[k] * z_components[k] for k in WEIGHTS)
    score = max(0.0, min(100.0, 65 + score * 10))

    output_lines.append(",".join([
        csv_escape(players[pid]),
        primary_position.get(pid, "Unknown"),
        str(games),
    ] + [f"{components[k]:.3f}" for k in WEIGHTS] + [f"{score:.2f}"]))

# === Output ===
print("Writing to output...")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print("Done. Output saved to", OUTPUT_FILE)
