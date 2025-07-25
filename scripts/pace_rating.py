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
OUTPUT_FILE = os.path.join(DATA_DIR, "ratings/player_pace_rating.csv")

# === ROLE MAP ===
ROLE_MAP = {
    "GK": "GK", "GKP": "GK",
    "DF": "DF", "DEF": "DF",
    "MD": "MD", "MID": "MD",
    "FW": "FW", "FWD": "FW",
}

# === RATING WEIGHTS ===
WEIGHTS = {
    "accelerations": 0.65,
    "long_carries": 0.39,
    "attacking_duels": 0.26,
    "wide_runs": 0.13,
    "distance_gained": 0.26,
    "counterattacks": 0.13,
}

CARRY_DISTANCE_THRESHOLD = 20.0  # meters

def boost(score, a=1):
    base = 100 * score / (score + 1.3)
    if score > 7:
        rating = base + math.log2(score - 6) * 3  # Stretch top
    else:
        rating = base
    return rating

# === Load players ===
print("Loading players...")
with open(PLAYERS_FILE, encoding="utf-8") as f:
    players_raw = json.load(f)

players = {}
player_roles = {}
for p in players_raw:
    pid = p["wyId"]
    name = p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "")}'
    try:
        name = codecs.decode(name, 'unicode_escape')
    except Exception:
        pass
    players[pid] = name
    role = p.get("role", {}).get("code3") or p.get("role", {}).get("code2") or "Unknown"
    player_roles[pid] = ROLE_MAP.get(role.upper(), "Unknown")

print(f"Loaded {len(players)} players.")

# === Load primary positions for display only ===
print("Loading primary positions...")
primary_position = {}
try:
    position_df = pd.read_csv(PRIMARY_POS_FILE)
    primary_position = dict(zip(position_df.playerId, position_df.best_fit_role))
except Exception as e:
    print("Warning: Could not load primary positions:", e)

# === Initialize stats ===
stats = defaultdict(lambda: {
    "matches": set(),
    "accelerations": 0,
    "attacking_duels": 0,
    "carries": 0,
    "long_carries": 0,
    "carry_distance": [],
    "wide_runs": 0,
    "counterattacks": 0,
})

# === Distance Function ===
def distance(x1, y1, x2, y2):
    dx = (x2 - x1) * 1.2  # pitch length
    dy = (y2 - y1) * 0.8  # pitch width
    return math.sqrt(dx ** 2 + dy ** 2)

# === Parse events ===
print("Processing event files...")
event_files = [f for f in os.listdir(EVENTS_DIR) if f.startswith("events_") and f.endswith(".json")]

for ef in event_files:
    with open(os.path.join(EVENTS_DIR, ef), encoding="utf-8") as f:
        events = json.load(f)

    for e in events:
        pid = e.get("playerId")
        mid = e.get("matchId")
        if pid not in players or not mid:
            continue

        stats[pid]["matches"].add(mid)
        event = e.get("eventName")
        sub = e.get("subEventName")
        tags = [t.get("id") for t in e.get("tags", [])]

        pos = e.get("positions", [])
        if len(pos) < 2:
            continue

        x1, y1 = pos[0].get("x", 0), pos[0].get("y", 0)
        x2, y2 = pos[-1].get("x", 0), pos[-1].get("y", 0)
        dist = distance(x1, y1, x2, y2)

        if event == "Others on the ball" and sub == "Acceleration":
            stats[pid]["accelerations"] += 1

        if event == "Duel" and sub == "Ground attacking duel":
            stats[pid]["attacking_duels"] += 1

        if event == "Others on the ball" and sub == "Touch":
            stats[pid]["carries"] += 1
            stats[pid]["carry_distance"].append(dist)
            if dist >= CARRY_DISTANCE_THRESHOLD:
                stats[pid]["long_carries"] += 1

            if y1 <= 20 or y1 >= 80:
                stats[pid]["wide_runs"] += 1

        if 1901 in tags:
            stats[pid]["counterattacks"] += 1

# === Calculate Ratings ===
print("Calculating pace ratings...")
ratings = []

for pid, s in stats.items():
    games = len(s["matches"])
    if games == 0:
        continue

    accels_pg = s["accelerations"] / games
    duels_pg = s["attacking_duels"] / games
    long_carries_pg = s["long_carries"] / games
    wide_runs_pg = s["wide_runs"] / games
    counter_pg = s["counterattacks"] / games
    avg_carry_dist = sum(s["carry_distance"]) / len(s["carry_distance"]) if s["carry_distance"] else 0

    raw_score = (
        WEIGHTS["accelerations"] * accels_pg +
        WEIGHTS["attacking_duels"] * duels_pg +
        WEIGHTS["long_carries"] * long_carries_pg +
        WEIGHTS["wide_runs"] * wide_runs_pg +
        WEIGHTS["counterattacks"] * counter_pg +
        WEIGHTS["distance_gained"] * (avg_carry_dist / 20)
    )

    raw_rating = boost(raw_score)
    raw_rating = min(100.000, max(30.000, raw_rating))

    ratings.append((pid, raw_rating, games, accels_pg, long_carries_pg, duels_pg, wide_runs_pg, counter_pg, avg_carry_dist))

# === Write Output ===
print("Writing output...")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("Player,PrimaryPosition,Games,Accelerations,LongCarries,Duels,WideRuns,CounterAttacks,AvgCarryDistance,RawRating\n")
    for pid, rating, g, a, lc, d, w, c, dist in ratings:
        name = players[pid].replace('"', "'")
        primary_pos = primary_position.get(pid, "Unknown")
        f.write(f"{name},{primary_pos},{g},{a:.2f},{lc:.2f},{d:.2f},{w:.2f},{c:.2f},{dist:.2f},{rating:.3f}\n")

print("Done.")
