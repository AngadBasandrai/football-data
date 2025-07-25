import json
import pandas as pd
from collections import defaultdict
import os
import re
from math import dist
import codecs

# File paths
EVENTS_DIR = "./events"
PLAYERS_FILE = "./data/players.json"
OUTPUT_FILE = "./positions/player_positions.csv"

ROLE_CENTERS = {
    "gk": (5, 50),        # Goalkeeper

    # Defenders
    "cb": (20, 50),
    "rb": (26, 22),
    "lb": (26, 78),

    # Defensive Midfielder
    "cdm": (40, 50),

    # Central Midfielders
    "cm": (47, 50),
    "rcm": (47, 42),
    "lcm": (47, 58),

    # Attacking Midfielders
    "cam": (55, 50),
    "ram": (55, 40),
    "lam": (55, 60),

    # Wingers
    "rw": (69, 34),
    "lw": (69, 66),

    # Striker
    "st": (76, 50),
}

# Events to skip
EXCLUDE_EVENTS = {
    "Free Kick", "Corner", "Throw In", "Goalkeeper",
    "Offside", "Goal Kick", "Substitution", "Injury", "Whistle"
}

# Decode and clean name
def clean_name(name):
    if not isinstance(name, str):
        return ""
    try:
        name = codecs.decode(name, "unicode_escape")
    except:
        pass
    name = re.sub(r'[\uE000-\uF8FF\u200B-\u200F\u2060-\u206F]', '', name)
    return name.strip()

# Closest role to (x, y)
def get_closest_role(x, y):
    return min(ROLE_CENTERS.items(), key=lambda item: dist((x, y), item[1]))[0]

# Load players
with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
    player_data = json.load(f)

player_id_to_name = {
    player["wyId"]: clean_name(
        player.get("shortName") or f"{player.get('firstName', '')} {player.get('lastName', '')}".strip()
    )
    for player in player_data
}

# Initialize role counts
player_roles = defaultdict(lambda: defaultdict(int))
included = excluded = missing_xy = skipped_no_player = 0

# Process all event files
event_files = [f for f in os.listdir(EVENTS_DIR) if f.startswith("events_") and f.endswith(".json")]

for filename in event_files:
    filepath = os.path.join(EVENTS_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        events = json.load(f)

    for event in events:
        player_id = event.get("playerId")
        if not player_id:
            skipped_no_player += 1
            continue

        if event.get("eventName") in EXCLUDE_EVENTS:
            excluded += 1
            continue

        positions = event.get("positions")
        if not positions or "x" not in positions[0] or "y" not in positions[0]:
            missing_xy += 1
            continue

        x, y = positions[0]["x"], positions[0]["y"]
        role = get_closest_role(x, y)
        player_roles[player_id][role] += 1
        included += 1

# Write output
records = []
for player_id, roles in player_roles.items():
    name = player_id_to_name.get(player_id, f"Unknown ({player_id})")
    for role, count in roles.items():
        records.append({
            "playerId": player_id,
            "name": name,
            "role": role,
            "count": count
        })

df = pd.DataFrame(records)
df = df.sort_values(by=["name", "count"], ascending=[True, False])
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

print(f"Saved player role frequencies to {OUTPUT_FILE}")
print(f"Included: {included}, Excluded: {excluded}, No XY: {missing_xy}, No playerId: {skipped_no_player}")
