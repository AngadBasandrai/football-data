import json
import os
from collections import defaultdict

DATA_DIR = ""  # Set your dataset root directory path here
events_dir = os.path.join(DATA_DIR, "events")
matches_dir = os.path.join(DATA_DIR, "matches")

# --- Load Players ---
with open(os.path.join(DATA_DIR, "players.json"), encoding="utf-8") as f:
    players = {
        p["wyId"]: p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "")}'.strip()
        for p in json.load(f)
    }

# --- Load Teams ---
with open(os.path.join(DATA_DIR, "teams.json"), encoding="utf-8") as f:
    teams = {t["wyId"]: t["name"] for t in json.load(f)}

# --- Structure: {country: {team_name: {player: (completed, attempted)}}} ---
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

        passes_by_country_team[country][team_name][player_name][1] += 1  # attempted
        if any(tag.get("id") == 1801 for tag in e.get("tags", [])):       # tag 1801 = accurate
            passes_by_country_team[country][team_name][player_name][0] += 1  # completed

# --- Output ---
output_dir = os.path.join(DATA_DIR, "pass_accuracy_by_country")
os.makedirs(output_dir, exist_ok=True)

for country, teams_data in passes_by_country_team.items():
    out_path = os.path.join(output_dir, f"{country}_passes.txt")
    
    # Write output with correct Unicode support
    with open(out_path, "w", encoding="utf-8", errors="replace") as out:
        for team_name in sorted(teams_data.keys()):
            out.write(f"=== {team_name} ===\n")
            player_stats = teams_data[team_name]

            # Determine team max attempts
            max_attempts = max((v[1] for v in player_stats.values()), default=1)
            threshold = 0.25 * max_attempts

            # Filter + sort by accuracy
            filtered = [
                (player, comp, att, (comp / att) * 100)
                for player, (comp, att) in player_stats.items()
                if att >= threshold
            ]
            filtered.sort(key=lambda x: x[3], reverse=True)  # sort by accuracy

            for player, comp, att, acc in filtered:
                out.write(f"{player}: {acc:.2f}% ({comp}/{att})\n")
            out.write("\n")

    print(f"Wrote {out_path}")
