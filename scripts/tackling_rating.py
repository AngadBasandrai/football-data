import os
import json
import math
import codecs
from collections import defaultdict
from statistics import mean, stdev

DATA_DIR = "./"
EVENTS_DIR = os.path.join(DATA_DIR, "events")
PLAYERS_FILE = os.path.join(DATA_DIR, "data/players.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "ratings/player_tackling_rating.csv")

SUCCESS_TAG = 1801

DUEL_SUBEVENTS = {"Ground defending duel", "Air duel"}
CLEARANCE_SUBEVENT = "Clearance"

WEIGHTS = {
    "ground_duel_acc": 0.6,
    "ground_duels_pg": 0.25,
    "aerial_duel_acc": 0.3,
    "clearance_pg": 0.075,
    "consistency": 0.25,
    "fouls_pg": -0.02,
}

MAX_GAME_BONUS = 0.7
MIN_GAME_PENALTY = -0.2
GAMES_FOR_MAX_EFFECT = 50
PRIOR_WEIGHT_K = 15

def smooth_ratio(success, total, prior_mean=0.5, prior_weight=10):
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

print("Loading players...")
with open(PLAYERS_FILE, encoding="utf-8") as f:
    players_raw = json.load(f)

players, player_roles = {}, {}
for p in players_raw:
    pid = p["wyId"]
    name = p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "")}'
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except:
            pass
    players[pid] = name
    role = p.get("role", {}).get("code3") or p.get("role", {}).get("code2") or "Unknown"
    player_roles[pid] = role

print(f"Loaded {len(players)} players.")

stats = defaultdict(lambda: {
    "matches": set(),
    "ground_duels": 0,
    "ground_duels_won": 0,
    "aerial_duels": 0,
    "aerial_duels_won": 0,
    "fouls": 0,
    "clearances": 0,
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

print("Computing raw ratings...")
raw_ratings, games_played, intermediate = {}, {}, {}

for pid, s in stats.items():
    games = len(s["matches"])
    if games == 0:
        continue

    ground_acc = smooth_ratio(s["ground_duels_won"], s["ground_duels"])
    aerial_acc = smooth_ratio(s["aerial_duels_won"], s["aerial_duels"])
    ground_duels_pg = s["ground_duels"] / games
    clearances_pg = clamp_clearance_pg(s["clearances"] / games)
    fouls_pg = s["fouls"] / games
    consistency = calculate_consistency(s["ground_duels_match"], s["ground_duels_won_match"])

    game_bonus = (
        MAX_GAME_BONUS if games >= GAMES_FOR_MAX_EFFECT
        else MIN_GAME_PENALTY if games < 5
        else MAX_GAME_BONUS * (games / GAMES_FOR_MAX_EFFECT)
    )

    rating = (
        WEIGHTS["ground_duel_acc"] * ground_acc +
        WEIGHTS["ground_duels_pg"] * (ground_duels_pg / 10.0) +
        WEIGHTS["aerial_duel_acc"] * aerial_acc +
        WEIGHTS["clearance_pg"] * (clearances_pg / 5.0) +
        WEIGHTS["consistency"] * consistency +
        WEIGHTS["fouls_pg"] * fouls_pg +
        game_bonus
    )

    raw_ratings[pid] = rating
    games_played[pid] = games
    intermediate[pid] = (ground_acc, aerial_acc, ground_duels_pg, clearances_pg, fouls_pg, consistency)

print("Applying global normalization...")
all_scores = list(raw_ratings.values())
mean_raw = mean(all_scores)
std_raw = stdev(all_scores)

normalized_ratings = {}
for pid, raw in raw_ratings.items():
    z = (raw - mean_raw) / std_raw if std_raw > 0 else 0
    score = 65 + 10 * z
    normalized_ratings[pid] = max(0.0, min(100.0, score))

print("Writing to output file...")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
lines = ["Player,Role,Games,GroundDuelAcc,AerialDuelAcc,GroundDuelsPG,ClearancesPG,FoulsPG,Consistency,Rating"]

for pid, base_score in normalized_ratings.items():
    name = players[pid]
    role = player_roles[pid]
    games = games_played[pid]
    g_acc, a_acc, gduel_pg, cl_pg, f_pg, cons = intermediate[pid]
    smooth_score = (games * base_score + PRIOR_WEIGHT_K * 65) / (games + PRIOR_WEIGHT_K)

    lines.append(",".join([
        csv_escape(name), role, str(games),
        f"{g_acc:.3f}", f"{a_acc:.3f}", f"{gduel_pg:.2f}", f"{cl_pg:.3f}",
        f"{f_pg:.3f}", f"{cons:.3f}", f"{smooth_score:.3f}"
    ]))

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("Done. Output saved to", OUTPUT_FILE)
