import json
import os
import codecs
from collections import defaultdict, Counter

DATA_DIR = ""
events_dir = os.path.join(DATA_DIR, "events")
matches_dir = os.path.join(DATA_DIR, "matches")

# --- Load Players ---
with open(os.path.join(DATA_DIR, "players.json"), encoding="utf-8") as f:
    players = {
        p["wyId"]: p.get("shortName") or f'{p["firstName"]} {p["lastName"]}'
        for p in json.load(f)
    }

# --- Load Teams ---
with open(os.path.join(DATA_DIR, "teams.json"), encoding="utf-8") as f:
    teams = {t["wyId"]: t["name"] for t in json.load(f)}

# --- Prepare structures ---
goals_by_country_team = defaultdict(lambda: defaultdict(Counter))
assists_by_country_team = defaultdict(lambda: defaultdict(Counter))

# --- Loop through countries ---
for fname in os.listdir(events_dir):
    if not fname.startswith("events_") or not fname.endswith(".json"):
        continue

    country = fname[len("events_"):-len(".json")]
    print(f"Processing {country}...")

    with open(os.path.join(events_dir, fname), encoding="utf-8") as f:
        events = json.load(f)

    with open(os.path.join(matches_dir, f"matches_{country}.json"), encoding="utf-8") as f:
        matches = {m["wyId"]: m for m in json.load(f)}

    for e in events:
        player_id = e.get("playerId")
        team_id = e.get("teamId")
        match_id = e.get("matchId")
        tags = e.get("tags", [])

        if not (player_id and team_id and match_id):
            continue

        player_name = players.get(player_id, f"Player {player_id}")
        team_name = teams.get(team_id, f"Team {team_id}")

        # Unicode decode fix
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

        # Goals
        if e.get("eventName") == "Shot" and any(tag.get("id") == 101 for tag in tags):
            goals_by_country_team[country][team_name][player_name] += 1

        # Assists
        if e.get("eventName") == "Pass" and any(tag.get("id") == 302 for tag in tags):
            assists_by_country_team[country][team_name][player_name] += 1

# --- Write Goals ---
goals_output = os.path.join(DATA_DIR, "goal_scorers_by_country")
os.makedirs(goals_output, exist_ok=True)

for country, teams_data in goals_by_country_team.items():
    file_path = os.path.join(goals_output, f"{country}_scorers.txt")
    with open(file_path, "w", encoding="utf-8") as out:
        for team_name in sorted(teams_data):
            out.write(f"=== {team_name} ===\n")
            for player, count in teams_data[team_name].most_common():
                out.write(f"{player}: {count} goals\n")
            out.write("\n")
    print(f"Wrote {file_path}")

# --- Write Assists ---
assists_output = os.path.join(DATA_DIR, "assist_providers_by_country")
os.makedirs(assists_output, exist_ok=True)

for country, teams_data in assists_by_country_team.items():
    file_path = os.path.join(assists_output, f"{country}_assists.txt")
    with open(file_path, "w", encoding="utf-8") as out:
        for team_name in sorted(teams_data):
            out.write(f"=== {team_name} ===\n")
            for player, count in teams_data[team_name].most_common():
                out.write(f"{player}: {count} assists\n")
            out.write("\n")
    print(f"Wrote {file_path}")
