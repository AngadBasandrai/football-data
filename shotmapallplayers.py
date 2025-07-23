import os
import json
import csv

DATA_DIR = ""  # Root directory of your dataset
events_dir = os.path.join(DATA_DIR, "events")
players_path = os.path.join(DATA_DIR, "players.json")

# Output folder
output_dir = os.path.join(DATA_DIR, "all_shots_by_event")
os.makedirs(output_dir, exist_ok=True)

# --- Load players ---
with open(players_path, encoding="utf-8") as f:
    players = json.load(f)

player_id_to_info = {
    p["wyId"]: {
        "name": p.get("shortName", "").encode('utf-8').decode('unicode_escape'),
        "role": p.get("role", {}).get("name", "Unknown")
    }
    for p in players
}

# --- Process each events_*.json file ---
for fname in os.listdir(events_dir):
    if not fname.startswith("events_") or not fname.endswith(".json"):
        continue

    input_path = os.path.join(events_dir, fname)
    output_path = os.path.join(output_dir, fname.replace(".json", ".csv"))

    with open(input_path, encoding="utf-8") as f:
        events = json.load(f)

    rows = []
    for e in events:
        if e.get("eventName") != "Shot":
            continue

        player_id = e.get("playerId")
        info = player_id_to_info.get(player_id)
        if not info:
            continue

        name = info["name"]
        role = info["role"]

        # Determine if it was a goal
        tags = [tag["id"] for tag in e.get("tags", [])]
        outcome = "GOAL" if 101 in tags else "Miss"

        pos = e.get("positions", [{}])
        x = pos[0].get("x", 0)
        y = pos[0].get("y", 0)

        rows.append((name, outcome, x, y, role))

    # Skip files with no shot data
    if not rows:
        continue

    with open(output_path, "w", encoding="utf-8", newline="") as out_csv:
        writer = csv.writer(out_csv)
        writer.writerow(["player", "outcome", "x", "y", "role"])
        writer.writerows(rows)

    print(f"Saved {len(rows)} shots to {output_path}")
