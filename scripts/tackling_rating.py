import os
import json
import math
import codecs
from collections import defaultdict
from statistics import mean, stdev

DATA_DIR = "./"
EVENTS_DIR = os.path.join(DATA_DIR, "events")
PLAYERS_FILE = os.path.join(DATA_DIR, "data/players.json")
PRIMARY_POS_FILE = os.path.join(DATA_DIR, "positions/player_primary_positions.csv")
OUTPUT_FILE = os.path.join(DATA_DIR, "ratings/player_tackling_rating.csv")

SUCCESS_TAG = 1801
CLEARANCE_SUBEVENT = "Clearance"

WEIGHTS = {
    "ground_duel_acc": 0.75,
    "ground_duels_pg": 0.15,  # stronger emphasis on engagement volume
    "aerial_duel_acc": 0.15,
    "clearance_pg": 0.03,
    "sliding_tackles_pg": 0.06,
    "sliding_tackle_acc": 0.25,
    "interceptions_pg": 0.02,
    "anticipation_ratio": 0.04,
    "consistency": 0.15,  # reduced to avoid GK exploit
    "fouls_pg": -0.04,
}

PRIOR_WEIGHT_K = 15

# === Helper functions ===
def smooth_ratio(success, total, prior_mean=0.4, prior_weight=15):
    return (success + prior_mean * prior_weight) / (total + prior_weight)

def calculate_consistency(per_match_total, per_match_success):
    accs = []
    for mid in per_match_total:
        total = per_match_total[mid]
        success = per_match_success.get(mid, 0)
        if total > 0:
            accs.append(success / total)
    if len(accs) < 2:
        return 1.0
    mean_acc = mean(accs)
    stddev = stdev(accs)
    return max(0.0, 1.0 - stddev / mean_acc) if mean_acc else 0.0

def clamp_clearance_pg(val):
    return min(val, 6.0)

def csv_escape(s):
    s = str(s)
    return f'"{s.replace("\"", "\"\"")}"' if "," in s or '"' in s else s

# === Load players and primary positions ===
print("Loading players...")
with open(PLAYERS_FILE, encoding="utf-8") as f:
    players_raw = json.load(f)

players = {}
for p in players_raw:
    pid = p["wyId"]
    name = p.get("shortName") or f"{p.get('firstName', '')} {p.get('lastName', '')}".strip()
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except:
            pass
    players[pid] = name

print("Loading primary positions...")
import pandas as pd
position_df = pd.read_csv(PRIMARY_POS_FILE)
primary_position = dict(zip(position_df.playerId, position_df.best_fit_role))

# === Initialize stats ===
stats = defaultdict(lambda: {
    "matches": set(),
    "ground_duels": 0,
    "ground_duels_won": 0,
    "aerial_duels": 0,
    "aerial_duels_won": 0,
    "fouls": 0,
    "clearances": 0,
    "sliding_tackles": 0,
    "sliding_tackles_won": 0,
    "interceptions": 0,
    "anticipations": 0,
    "anticipated": 0,
    "ground_duels_match": defaultdict(int),
    "ground_duels_won_match": defaultdict(int),
})

print("Processing events...")
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
        sub = e.get("subEventName")
        tags = {t["id"] for t in e.get("tags", [])}
        success = SUCCESS_TAG in tags
        s = stats[pid]
        s["matches"].add(mid)

        if ename == "Duel" and sub == "Ground defending duel":
            s["ground_duels"] += 1
            s["ground_duels_match"][mid] += 1
            if success:
                s["ground_duels_won"] += 1
                s["ground_duels_won_match"][mid] += 1

        elif ename == "Duel" and sub == "Air duel":
            s["aerial_duels"] += 1
            if success:
                s["aerial_duels_won"] += 1

        elif ename == "Foul":
            s["fouls"] += 1

        elif sub == CLEARANCE_SUBEVENT:
            s["clearances"] += 1

        if 1601 in tags:
            s["sliding_tackles"] += 1
            if success:
                s["sliding_tackles_won"] += 1

        if 1401 in tags:
            s["interceptions"] += 1
        if 601 in tags:
            s["anticipations"] += 1
        if 602 in tags:
            s["anticipated"] += 1

# === Compute per-game stats ===
ground_duels_pg_list = []
clearances_pg_list = []
sliding_tackles_pg_list = []
interceptions_pg_list = []

raw_ratings, games_played, intermediate = {}, {}, {}

for pid, s in stats.items():
    games = len(s["matches"])
    if games == 0:
        continue

    gduel_pg = s["ground_duels"] / games
    cl_pg = clamp_clearance_pg(s["clearances"] / games)
    slide_pg = s["sliding_tackles"] / games
    int_pg = s["interceptions"] / games
    ground_duels_pg_list.append(gduel_pg)
    clearances_pg_list.append(cl_pg)
    sliding_tackles_pg_list.append(slide_pg)
    interceptions_pg_list.append(int_pg)

avg_ground_duels_pg = mean(ground_duels_pg_list)
avg_clearances_pg = mean(clearances_pg_list)
avg_sliding_tackles_pg = mean(sliding_tackles_pg_list)
avg_interceptions_pg = mean(interceptions_pg_list)

# === Final rating computation ===
print("Computing ratings...")

for pid, s in stats.items():
    games = len(s["matches"])
    if games == 0:
        continue

    ground_acc = smooth_ratio(s["ground_duels_won"], s["ground_duels"])
    aerial_acc = smooth_ratio(s["aerial_duels_won"], s["aerial_duels"])
    gduel_pg = s["ground_duels"] / games
    cl_pg = clamp_clearance_pg(s["clearances"] / games)
    f_pg = s["fouls"] / games
    slide_pg = s["sliding_tackles"] / games
    slide_acc = smooth_ratio(s["sliding_tackles_won"], s["sliding_tackles"])
    int_pg = s["interceptions"] / games
    antir = smooth_ratio(s["anticipations"], s["anticipations"] + s["anticipated"])
    consistency = calculate_consistency(s["ground_duels_match"], s["ground_duels_won_match"])


    raw = (
        WEIGHTS["ground_duel_acc"] * ground_acc +
        WEIGHTS["ground_duels_pg"] * (gduel_pg / avg_ground_duels_pg if avg_ground_duels_pg else 0) +
        WEIGHTS["aerial_duel_acc"] * aerial_acc +
        WEIGHTS["clearance_pg"] * (cl_pg / avg_clearances_pg if avg_clearances_pg else 0) +
        WEIGHTS["sliding_tackles_pg"] * (slide_pg / avg_sliding_tackles_pg if avg_sliding_tackles_pg else 0) +
        WEIGHTS["sliding_tackle_acc"] * slide_acc +
        WEIGHTS["interceptions_pg"] * (int_pg / avg_interceptions_pg if avg_interceptions_pg else 0) +
        WEIGHTS["anticipation_ratio"] * antir +
        WEIGHTS["consistency"] * consistency +
        WEIGHTS["fouls_pg"] * f_pg
    )

    raw_ratings[pid] = raw
    games_played[pid] = games
    intermediate[pid] = (
        ground_acc, aerial_acc, gduel_pg, cl_pg, f_pg,
        consistency, slide_pg, slide_acc, int_pg, antir
    )

# === Normalize ratings ===
print("Normalizing...")
all_scores = list(raw_ratings.values())
mean_raw = mean(all_scores)
std_raw = stdev(all_scores)

normalized_ratings = {}
for pid, raw in raw_ratings.items():
    z = (raw - mean_raw) / std_raw if std_raw else 0
    score = 75 + 10 * z
    normalized_ratings[pid] = max(0.0, min(100.0, score))

avg_score = mean(normalized_ratings.values())

# === Write to file ===
print("Writing to output file...")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
lines = ["Player,PrimaryPosition,Games,GroundDuelAcc,AerialDuelAcc,GroundDuelsPG,ClearancesPG,FoulsPG,Consistency,SlidingTacklesPG,SlidingTackleAcc,InterceptionsPG,AnticipationRatio,Rating"]

for pid, base_score in normalized_ratings.items():
    name = players[pid]
    pos = primary_position.get(pid, "Unknown")
    games = games_played[pid]
    g_acc, a_acc, gduel_pg, cl_pg, f_pg, cons, slide_pg, slide_acc, int_pg, antir = intermediate[pid]
    smooth_score = (games * base_score + PRIOR_WEIGHT_K * avg_score) / (games + PRIOR_WEIGHT_K)

    lines.append(",".join([
        csv_escape(name), pos, str(games),
        f"{g_acc:.3f}", f"{a_acc:.3f}", f"{gduel_pg:.2f}", f"{cl_pg:.3f}",
        f"{f_pg:.3f}", f"{cons:.3f}", f"{slide_pg:.2f}", f"{slide_acc:.3f}",
        f"{int_pg:.2f}", f"{antir:.3f}", f"{smooth_score:.3f}"
    ]))

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Done. Output saved to", OUTPUT_FILE)
