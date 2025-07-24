import os
import json
import math
import codecs
from collections import defaultdict
from statistics import mean, stdev

# === SETTINGS ===
DATA_DIR = "./"
EVENTS_DIR = os.path.join(DATA_DIR, "events")
PLAYERS_FILE = os.path.join(DATA_DIR, "data/players.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "ratings/player_crossing_rating.csv")

# === TAGS ===
SUCCESS_TAG_ID = 1801
KEY_PASS_TAG_ID = 302

# === CROSS TYPES ===
VALID_CROSS_TYPES = {
    ("Pass", "Cross"),
    ("Pass", "High pass"),
    ("Pass", "Launch"),
    ("Free Kick", "Free kick cross")
}

# === RATING WEIGHTS ===
WEIGHTS = {
    "cross_accuracy": 0.55,
    "crosses_per_game": 0.25,
    "consistency": 0.1,
    "turnover_rate": -0.05,
    "key_passes_per_game": 0.3,
}

MAX_GAME_BONUS = 0.25
MIN_GAME_PENALTY = -0.2
GAMES_FOR_MAX_EFFECT = 30
PRIOR_WEIGHT_K = 20  # For Bayesian smoothing

SMOOTH_PRIORS = {
    "cross_acc": (0.4, 20),
}

ROLE_MAP = {
    "GK": "GK", "GKP": "GK",
    "DF": "DF", "DEF": "DF",
    "MD": "MD", "MID": "MD",
    "FW": "FW", "FWD": "FW",
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
    mean_acc = sum(accs) / len(accs)
    stddev = math.sqrt(sum((a - mean_acc) ** 2 for a in accs) / (len(accs) - 1))
    return max(0.0, 1.0 - stddev / mean_acc) if mean_acc else 0.0

def csv_escape(s):
    s = str(s)
    return f'"{s.replace("\"", "\"\"")}"' if "," in s or '"' in s else s

# === Load players ===
print("Loading players...")
with open(PLAYERS_FILE, encoding="utf-8") as f:
    players_raw = json.load(f)

players = {}
player_roles = {}
for p in players_raw:
    pid = p["wyId"]
    name = p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "")}'
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except Exception:
            pass
    players[pid] = name
    role = p.get("role", {}).get("code3") or p.get("role", {}).get("code2") or "Unknown"
    role = ROLE_MAP.get(role.upper(), "Unknown")
    player_roles[pid] = role

print(f"Loaded {len(players)} players.")

# === Initialize stats ===
stats = defaultdict(lambda: {
    "matches": set(),
    "cross_total": 0,
    "cross_success": 0,
    "cross_keypasses": 0,
    "crosses_per_match": defaultdict(int),
    "cross_success_per_match": defaultdict(int),
})

# === Parse events ===
print("Processing event files...")
event_files = [f for f in os.listdir(EVENTS_DIR) if f.startswith("events_") and f.endswith(".json")]

for ef in event_files:
    with open(os.path.join(EVENTS_DIR, ef), encoding="utf-8") as f:
        events = json.load(f)

    for e in events:
        event_name = e.get("eventName")
        sub_event = e.get("subEventName")
        if (event_name, sub_event) not in VALID_CROSS_TYPES:
            continue

        pid = e.get("playerId")
        mid = e.get("matchId")
        if pid not in players or not mid:
            continue

        tags = [t.get("id") for t in e.get("tags", [])]
        success = SUCCESS_TAG_ID in tags
        is_key_pass = KEY_PASS_TAG_ID in tags

        s = stats[pid]
        s["matches"].add(mid)
        s["cross_total"] += 1
        s["crosses_per_match"][mid] += 1
        if success:
            s["cross_success"] += 1
            s["cross_success_per_match"][mid] += 1
        if is_key_pass:
            s["cross_keypasses"] += 1

# === Calculate raw ratings ===
print("Calculating raw crossing ratings...")
raw_ratings = {}
games_played = {}
intermediate_metrics = {}

for pid, s in stats.items():
    games = len(s["matches"])
    if games == 0 or s["cross_total"] == 0:
        continue

    acc = smooth_ratio(s["cross_success"], s["cross_total"], *SMOOTH_PRIORS["cross_acc"])
    crosses_pg = s["cross_total"] / games
    keypasses_pg = s["cross_keypasses"] / games
    turnover = 1 - acc
    consistency = calculate_consistency(s["crosses_per_match"], s["cross_success_per_match"])

    if games < 5:
        game_bonus = MIN_GAME_PENALTY
    elif games >= GAMES_FOR_MAX_EFFECT:
        game_bonus = MAX_GAME_BONUS
    else:
        game_bonus = MAX_GAME_BONUS * (games / GAMES_FOR_MAX_EFFECT)

    rating = (
        WEIGHTS["cross_accuracy"] * acc +
        WEIGHTS["crosses_per_game"] * (crosses_pg / 5) +
        WEIGHTS["key_passes_per_game"] * (keypasses_pg / 2) +
        WEIGHTS["consistency"] * consistency +
        WEIGHTS["turnover_rate"] * turnover +
        game_bonus
    )

    raw_ratings[pid] = rating
    games_played[pid] = games
    intermediate_metrics[pid] = (acc, crosses_pg, keypasses_pg, consistency, turnover)

# === Role-wise normalization with light global anchoring (mean = 65, std = 10)
print("Normalizing ratings by role with light global anchoring...")

ANCHOR_WEIGHT = 0.2  # 20% weight toward global distribution

# Global stats
all_ratings = list(raw_ratings.values())
global_mean = mean(all_ratings)
global_std = stdev(all_ratings)

role_groups = defaultdict(list)
for pid, rating in raw_ratings.items():
    role = player_roles.get(pid, "Unknown")
    role_groups[role].append((pid, rating))

normalized_ratings = {}

for role, players_in_role in role_groups.items():
    ratings = [r for _, r in players_in_role]
    if len(ratings) < 2:
        for pid, r in players_in_role:
            normalized_ratings[pid] = 65.0
        continue

    role_mean = mean(ratings)
    role_std = stdev(ratings)

    blend_mean = (1 - ANCHOR_WEIGHT) * role_mean + ANCHOR_WEIGHT * global_mean
    blend_std = (1 - ANCHOR_WEIGHT) * role_std + ANCHOR_WEIGHT * global_std

    for pid, r in players_in_role:
        z = (r - blend_mean) / blend_std if blend_std > 0 else 0
        target_mean = 65
        norm_score = target_mean + 10 * z
        norm_score = max(0.0, min(100.0, norm_score))
        normalized_ratings[pid] = norm_score


# === Final output with Bayesian smoothing on normalized rating
print("Writing to output file...")
output_lines = ["Player,Role,Games,CrossAccuracy,CrossesPerGame,KeyPassesPerGame,Consistency,TurnoverRate,Rating"]

for pid, base_score in normalized_ratings.items():
    name = players[pid]
    role = player_roles[pid]
    games = games_played[pid]
    acc, crosses_pg, keypasses_pg, consistency, turnover = intermediate_metrics[pid]

    smoothed_rating = (games * base_score + PRIOR_WEIGHT_K * 65) / (games + PRIOR_WEIGHT_K)

    output_lines.append(",".join([
        csv_escape(name), role, str(games),
        f"{acc:.3f}",
        f"{crosses_pg:.3f}",
        f"{keypasses_pg:.3f}",
        f"{consistency:.3f}",
        f"{turnover:.3f}",
        f"{smoothed_rating:.3f}"
    ]))

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print("Done. Output saved to", OUTPUT_FILE)
