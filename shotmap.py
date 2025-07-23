import json
import os

DATA_DIR = ""  # Set your dataset root directory
events_dir = os.path.join(DATA_DIR, "events")
matches_dir = os.path.join(DATA_DIR, "matches")

# --- Load players ---
with open(os.path.join(DATA_DIR, "players.json"), encoding="utf-8") as f:
    players = json.load(f)
player_map = {p.get("shortName"): p["wyId"] for p in players if p.get("shortName")}

# --- Load teams ---
with open(os.path.join(DATA_DIR, "teams.json"), encoding="utf-8") as f:
    teams_raw = json.load(f)
teams = {t["wyId"]: t["name"] for t in teams_raw}

# --- Load matches ---
match_teams = {}
for fname in os.listdir(matches_dir):
    if not fname.endswith(".json"):
        continue
    with open(os.path.join(matches_dir, fname), encoding="utf-8") as f:
        matches = json.load(f)
        for match in matches:
            teams_data = match["teamsData"]
            home = away = None
            for team_entry in teams_data.values():
                if team_entry.get("side") == "home":
                    home = team_entry["teamId"]
                elif team_entry.get("side") == "away":
                    away = team_entry["teamId"]
            if home and away:
                match_teams[match["wyId"]] = (home, away)

# --- Input player short name ---
target_name = input("Enter player short name: ").strip()
if target_name not in player_map:
    print(f"No such player: {target_name}")
    exit()

player_id = player_map[target_name]
shot_lines = []

# --- Process all events ---
for fname in os.listdir(events_dir):
    if not fname.endswith(".json"):
        continue
    with open(os.path.join(events_dir, fname), encoding="utf-8") as f:
        events = json.load(f)

    for e in events:
        if e.get("eventName") != "Shot" or e.get("playerId") != player_id:
            continue

        match_id = e.get("matchId")
        team_id = e.get("teamId")

        # Opponent name
        home, away = match_teams.get(match_id, (None, None))
        if not home or not away:
            opponent = "Unknown"
        else:
            opponent_id = away if team_id == home else home
            raw_name = teams.get(opponent_id, f"Team {opponent_id}")
            try:
                opponent = raw_name.encode('utf-8').decode('unicode_escape')
            except:
                opponent = raw_name

        # Position
        pos = e.get("positions", [{}])
        # if len(pos) >= 2:
        #     x, y = pos[1].get("x", 0), pos[1].get("y", 0)
        # else:
        x, y = pos[0].get("x", 0), pos[0].get("y", 0)

        # Tags
        tags = [tag["id"] for tag in e.get("tags", [])]
        is_goal = 101 in tags

        # Proper time formatting
        sec = e.get("eventSec", 0)
        if not isinstance(sec, (int, float)) or sec < 0:
            sec = 0.0
        minutes = int(sec // 60)
        seconds = int(sec % 60)

        time_str = f"{minutes:02}:{seconds:02}"
        outcome = "GOAL" if is_goal else "Miss"

        shot_lines.append(
            f"{time_str} vs {opponent} - {outcome} at ({x:.1f}, {y:.1f})"
        )

# --- Write to file ---
output_dir = os.path.join(DATA_DIR, "shot_tracking_output")
os.makedirs(output_dir, exist_ok=True)

output_path = os.path.join(output_dir, f"{target_name}_shots.txt")
with open(output_path, "w", encoding="utf-8") as out:
    for line in shot_lines:
        out.write(line + "\n")

print(f"Saved shot data to {output_path}")
