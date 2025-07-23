import json
import os
import codecs
from collections import defaultdict

DATA_DIR = ""  # Set dataset root here
events_dir = os.path.join(DATA_DIR, "events")

# --- Load Players ---
with open(os.path.join(DATA_DIR, "players.json"), encoding="utf-8") as f:
    players = {
        p["wyId"]: p.get("shortName") or f'{p["firstName"]} {p["lastName"]}'
        for p in json.load(f)
    }

# --- Load Teams ---
with open(os.path.join(DATA_DIR, "teams.json"), encoding="utf-8") as f:
    teams = {t["wyId"]: t["name"] for t in json.load(f)}

# --- Structure: {country: {team_name: {player: [completed, attempted]}}} ---
passes_by_country_team = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0])))

# --- Process all countries ---
for fname in os.listdir(events_dir):
    if not fname.startswith("events_") or not fname.endswith(".json"):
        continue

    country = fname[len("events_"):-len(".json")]
    print(f"Processing {country}...")

    with open(os.path.join(events_dir, fname), encoding="utf-8") as f:
        events = json.load(f)

    for e in events:
        if e.get("eventName") != "Pass":
            continue

        player_id = e.get("playerId")
        team_id = e.get("teamId")
        if player_id is None or team_id is None:
            continue

        player_name = players.get(player_id, f"Player {player_id}")
        team_name = teams.get(team_id, f"Team {team_id}")

        # Fix Unicode if escaped
        if "\\u" in player_name:
            try:
                player_name = codecs.decode(player_name, "unicode_escape")
            except Exception:
                pass
        if "\\u" in team_name:
            try:
                team_name = codecs.decode(team_name, "unicode_escape")
            except Exception:
                pass

        passes_by_country_team[country][team_name][player_name][1] += 1  # attempted
        if any(tag.get("id") == 1801 for tag in e.get("tags", [])):       # tag 1801 = accurate
            passes_by_country_team[country][team_name][player_name][0] += 1  # completed

# --- Output ---
output_dir = os.path.join(DATA_DIR, "pass_accuracy_by_country")
os.makedirs(output_dir, exist_ok=True)

for country, teams_data in passes_by_country_team.items():
    file_path = os.path.join(output_dir, f"{country}_passes.txt")
    with open(file_path, "w", encoding="utf-8") as out:
        for team_name in sorted(teams_data):
            out.write(f"=== {team_name} ===\n")
            player_stats = teams_data[team_name]

            max_attempts = max((v[1] for v in player_stats.values()), default=1)
            threshold = 0.25 * max_attempts

            filtered = [
                (p, c, a, (c / a) * 100)
                for p, (c, a) in player_stats.items() if a >= threshold
            ]
            filtered.sort(key=lambda x: x[3], reverse=True)

            for name, comp, att, acc in filtered:
                out.write(f"{name}: {acc:.2f}% ({comp}/{att})\n")
            out.write("\n")

    print(f"Wrote {file_path}")
