import pandas as pd
from math import dist
import os
import codecs
import json
import re

# File paths
POSITIONS_FILE = "./positions/player_positions.csv"
PLAYERS_FILE = "./data/players.json"
OUTPUT_FILE = "./positions/player_primary_positions.csv"

ROLE_CENTERS = {
    "gk": (5, 50),        # Goalkeeper

    # Defenders
    "cb": (20, 50),
    "rcb": (22, 44),      # Symmetrical spread around center
    "lcb": (22, 56),
    "rb": (26, 30),       # Modern fullback slightly tucked in
    "lb": (26, 70),

    # Defensive Midfielder
    "cdm": (35, 50),

    # Central Midfielders
    "cm": (48, 50),
    "rcm": (48, 43),
    "lcm": (48, 57),

    # Attacking Midfielders
    "cam": (58, 50),
    "ram": (58, 37),      # Symmetric offset
    "lam": (58, 63),

    # Wingers
    "rw": (70, 25),
    "lw": (70, 75),

    # Strikers / Forwards
    "st": (76, 50),
    "rs": (76, 42),
    "ls": (76, 58),

}

# Role category mapping
CATEGORY_TO_ROLES = {
    "gk": {"gk"},
    "df": {"rcb", "rb", "lcb", "lb", "cb"},
    "md": {"cdm", "rcm", "lcm", "cam", "ram", "lam", "cm"},
    "fw": {"ls", "rs", "st", "rw", "lw"},
}

ROLE_MAP = {
    "GK": "gk", "GKP": "gk",
    "DF": "df", "DEF": "df",
    "MD": "md", "MID": "md",
    "FW": "fw", "FWD": "fw"
}

def clean_name(name):
    if not isinstance(name, str):
        return ""
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except:
            pass
    name = re.sub(r'[\uE000-\uF8FF\u200B-\u200F\u2060-\u206F]', '', name)
    return name.strip()

# Load player info
with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
    players_raw = json.load(f)

player_id_to_type = {}
player_id_to_name = {}

for p in players_raw:
    pid = p["wyId"]
    name = p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "")}'.strip()
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except:
            pass
    name = re.sub(r'[\uE000-\uF8FF\u200B-\u200F\u2060-\u206F]', '', name).strip()
    player_id_to_name[pid] = name

    role_obj = p.get("role", {})
    raw_code = role_obj.get("code3") or role_obj.get("code2") or ""
    player_id_to_type[pid] = ROLE_MAP.get(raw_code.upper(), "unknown")

# Load position data
df = pd.read_csv(POSITIONS_FILE, encoding="utf-8")

records = []

for player_id, group in df.groupby("playerId"):
    name = clean_name(group["name"].iloc[0])
    total = group["count"].sum()
    if total == 0:
        continue

    sum_x = sum_y = 0
    for _, row in group.iterrows():
        role = row["role"]
        count = row["count"]
        if role not in ROLE_CENTERS:
            continue
        x, y = ROLE_CENTERS[role]
        sum_x += x * count
        sum_y += y * count

    centroid = (sum_x / total, sum_y / total)

    # Raw best-fit (regardless of role category)
    raw_best_fit = min(ROLE_CENTERS.items(), key=lambda item: dist(centroid, item[1]))[0]

    # Category-based best-fit
    category = player_id_to_type.get(player_id, "unknown")
    allowed_roles = CATEGORY_TO_ROLES.get(category, ROLE_CENTERS.keys())
    best_fit = min(
        ((role, ROLE_CENTERS[role]) for role in allowed_roles if role in ROLE_CENTERS),
        key=lambda item: dist(centroid, item[1])
    )[0]

    records.append({
        "playerId": player_id,
        "name": name,
        "category": category,
        "best_fit_role": best_fit,
        "raw_best_fit_role": raw_best_fit
    })

# Save final assignments
out_df = pd.DataFrame(records)
out_df = out_df.sort_values(by="name")
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
out_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

# Diagnostic summary
total = len(out_df)
unknown_count = sum(out_df["category"] == "unknown")
percent = round(100 * unknown_count / total, 2)
print(f"Saved player primary positions to {OUTPUT_FILE}")
print(f"{unknown_count}/{total} players ({percent}%) had unknown role categories.")

# Print count of players per best_fit_role
print("\nBest-fit role distribution:")
role_counts = out_df["best_fit_role"].value_counts().sort_index()
for role, count in role_counts.items():
    print(f"{role:4s}: {count}")
