import os
import json
import math
import codecs
import pandas as pd
from collections import defaultdict

# === SETTINGS ===
DATA_DIR = "./"
EVENTS_DIR = os.path.join(DATA_DIR, "events")
PLAYERS_FILE = os.path.join(DATA_DIR, "data/players.json")
PRIMARY_POS_FILE = os.path.join(DATA_DIR, "positions/player_primary_positions.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "ratings/player_long_passing_rating.csv")

LONG_PASS_THRESHOLD_YARDS = 25
FIELD_SCALE_X = 1.2  # x: 100 → 120 yards
FIELD_SCALE_Y = 0.8  # y: 100 → 80 yards

PASS_TAG_ID = 1801
THROUGH_PASS_TAG_ID = 901
ASSIST_TAG_ID = 302
FREE_KICK_TAG_ID = 801

WEIGHTS = {
    "long_pass_accuracy": 0.6,
    "long_THROUGH_PASS_accuracy": 0.35,
    "long_pass_assists": 0.2,
    "freekick_accuracy": 0.05,
    "consistency": 0.15,
    "turnover_rate": -0.03,
    "games_played_bonus": 0.3,
}

MAX_GAME_BONUS = 0.25
MIN_GAME_PENALTY = -0.2
GAMES_FOR_MAX_EFFECT = 30
PRIOR_WEIGHT_K = 20  # For Bayesian shrinkage on final rating

SMOOTH_PRIORS = {
    "long_pass_acc": (0.6, 20),
    "freekick_acc": (0.7, 10),
    "long_THROUGH_PASS_acc": (0.5, 10),
}

def smooth_ratio(success, total, prior_mean, prior_weight):
    return (success + prior_mean * prior_weight) / (total + prior_weight)

def calculate_distance(x1, y1, x2, y2):
    dx = (x2 - x1) * FIELD_SCALE_X
    dy = (y2 - y1) * FIELD_SCALE_Y
    return math.sqrt(dx**2 + dy**2)

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
    stddev = math.sqrt(sum((a - mean) ** 2 for a in accs) / (len(accs) - 1))
    return max(0.0, 1.0 - stddev / mean) if mean else 0.0

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
    "matches": set(),
    "long_total": 0,
    "long_success": 0,
    "long_assists": 0,
    "long_through_total": 0,
    "long_through_success": 0,
    "freekick_total": 0,
    "freekick_success": 0,
    "long_pass_attempts_per_match": defaultdict(int),
    "long_pass_success_per_match": defaultdict(int),
})

# === Parse events ===
print("Processing event files...")
event_files = [f for f in os.listdir(EVENTS_DIR) if f.startswith("events_") and f.endswith(".json")]

for ef in event_files:
    with open(os.path.join(EVENTS_DIR, ef), encoding="utf-8") as f:
        events = json.load(f)

    for e in events:
        if e.get("eventName") != "Pass":
            continue

        pid = e.get("playerId")
        mid = e.get("matchId")
        if pid not in players or not mid:
            continue

        positions = e.get("positions", [])
        if len(positions) < 2:
            continue
        x1, y1 = positions[0].get("x", 0), positions[0].get("y", 0)
        x2, y2 = positions[1].get("x", 0), positions[1].get("y", 0)
        dist = calculate_distance(x1, y1, x2, y2)

        tags = [t.get("id") for t in e.get("tags", [])]
        success = PASS_TAG_ID in tags
        is_freekick = FREE_KICK_TAG_ID in tags
        is_through = THROUGH_PASS_TAG_ID in tags
        is_assist = ASSIST_TAG_ID in tags

        s = stats[pid]
        s["matches"].add(mid)

        if is_freekick:
            s["freekick_total"] += 1
            if success:
                s["freekick_success"] += 1

        if dist >= LONG_PASS_THRESHOLD_YARDS:
            s["long_total"] += 1
            s["long_pass_attempts_per_match"][mid] += 1
            if success:
                s["long_success"] += 1
                s["long_pass_success_per_match"][mid] += 1

            if is_through:
                s["long_through_total"] += 1
                if success:
                    s["long_through_success"] += 1

            if is_assist:
                s["long_assists"] += 1

# === Calculate raw ratings ===
print("Calculating long pass ratings...")
raw_ratings = {}
games_played = {}

for pid, s in stats.items():
    games = len(s["matches"])
    if games == 0 or s["long_total"] == 0:
        continue

    long_acc = smooth_ratio(s["long_success"], s["long_total"], *SMOOTH_PRIORS["long_pass_acc"])
    through_acc = smooth_ratio(s["long_through_success"], s["long_through_total"], *SMOOTH_PRIORS["long_THROUGH_PASS_acc"])
    freekick_acc = smooth_ratio(s["freekick_success"], s["freekick_total"], *SMOOTH_PRIORS["freekick_acc"])
    assists_pg = s["long_assists"] / games
    turnover = 1 - long_acc
    consistency = calculate_consistency(s["long_pass_attempts_per_match"], s["long_pass_success_per_match"])

    game_bonus = (
        MAX_GAME_BONUS if games >= GAMES_FOR_MAX_EFFECT
        else MIN_GAME_PENALTY if games < 5
        else MAX_GAME_BONUS * (games / GAMES_FOR_MAX_EFFECT)
    )

    rating = (
        WEIGHTS["long_pass_accuracy"] * long_acc +
        WEIGHTS["long_THROUGH_PASS_accuracy"] * through_acc +
        WEIGHTS["long_pass_assists"] * assists_pg +
        WEIGHTS["freekick_accuracy"] * freekick_acc +
        WEIGHTS["consistency"] * consistency +
        WEIGHTS["turnover_rate"] * turnover +
        WEIGHTS["games_played_bonus"] * game_bonus
    )

    raw_ratings[pid] = rating
    games_played[pid] = games

# === Apply Bayesian smoothing and write output ===
mean_rating = sum(raw_ratings.values()) / len(raw_ratings) if raw_ratings else 0
output_lines = ["Player,PrimaryPosition,Games,LongPassAcc,LongthroughPassAcc,LongPassAssistsPerGame,FreeKickAcc,Consistency,TurnoverRate,Rating"]

for pid, raw in raw_ratings.items():
    s = stats[pid]
    name = players[pid]
    pos = primary_position.get(pid, "Unknown")
    games = games_played[pid]

    long_acc = smooth_ratio(s["long_success"], s["long_total"], *SMOOTH_PRIORS["long_pass_acc"])
    through_acc = smooth_ratio(s["long_through_success"], s["long_through_total"], *SMOOTH_PRIORS["long_THROUGH_PASS_acc"])
    freekick_acc = smooth_ratio(s["freekick_success"], s["freekick_total"], *SMOOTH_PRIORS["freekick_acc"])
    assists_pg = s["long_assists"] / games if games else 0
    turnover = 1 - long_acc
    consistency = calculate_consistency(s["long_pass_attempts_per_match"], s["long_pass_success_per_match"])

    smoothed_rating = (games * raw + PRIOR_WEIGHT_K * mean_rating) / (games + PRIOR_WEIGHT_K)
    smoothed_rating = min(100.000, max(0.000, smoothed_rating * 100))

    output_lines.append(",".join([
        csv_escape(name), pos, str(games),
        f"{long_acc:.3f}",
        f"{through_acc:.3f}",
        f"{assists_pg:.3f}",
        f"{freekick_acc:.3f}",
        f"{consistency:.3f}",
        f"{turnover:.3f}",
        f"{smoothed_rating:.3f}"
    ]))

print(f"Writing output to {OUTPUT_FILE} ...")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print("Done.")
