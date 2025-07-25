import csv
import matplotlib.pyplot as plt

# Tag-to-location mapping
goal_zones = {
    "1201": (0.5, 0.1), "1202": (0.9, 0.1), "1203": (0.5, 0.5),
    "1204": (0.3, 0.5), "1205": (0.1, 0.1), "1206": (0.7, 0.5),
    "1207": (0.5, 0.9), "1208": (0.1, 0.9), "1209": (0.9, 0.9),
    "1210": (1.0, 0.1), "1211": (0.2, 0.5), "1212": (0.0, 0.1),
    "1213": (0.8, 0.5), "1214": (0.5, 1.0), "1215": (0.1, 1.0),
    "1216": (0.9, 1.0), "1217": (1.0, 0.2), "1218": (0.2, 0.6),
    "1219": (0.0, 0.2), "1220": (0.8, 0.6), "1221": (0.5, 0.8),
    "1222": (0.1, 0.8), "1223": (0.9, 0.8),
}

# Human-readable tag descriptions
tag_descriptions = {
    "1201": "Goal low center", "1202": "Goal low right", "1203": "Goal center",
    "1204": "Goal center left", "1205": "Goal low left", "1206": "Goal center right",
    "1207": "Goal high center", "1208": "Goal high left", "1209": "Goal high right",
    "1210": "Out low right", "1211": "Out center left", "1212": "Out low left",
    "1213": "Out center right", "1214": "Out high center", "1215": "Out high left",
    "1216": "Out high right", "1217": "Post low right", "1218": "Post center left",
    "1219": "Post low left", "1220": "Post center right", "1221": "Post high center",
    "1222": "Post high left", "1223": "Post high right"
}

goal_tags = {str(i) for i in range(1201, 1210)}
miss_tags = set(goal_zones.keys()) - goal_tags

# Get player name
player_name = input("Enter player name (as in filename): ").strip()
file_path = f"./player_events_output/{player_name}_events.csv"

# Load and filter penalty shots
penalty_shots = []

try:
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        for row in reader:
            if len(row) < 7:
                continue

            event_type = row[0].strip()
            subevent_type = row[1].strip()
            tags_raw = row[-1].strip().strip('"')

            if subevent_type != "Penalty":
                continue

            tags = set(t.strip() for t in tags_raw.split(",") if t.strip().isdigit())
            location_tags = tags & set(goal_zones.keys())

            for tag in location_tags:
                x, y = goal_zones[tag]
                color = "green" if tag in goal_tags else "red"
                penalty_shots.append((x, y, color))

                # Print penalty info
                result = "GOAL" if color == "green" else "MISS"
                description = tag_descriptions.get(tag, "Unknown location")
                print(f"[{result}] Tag: {tag} → {description}")

except FileNotFoundError:
    print(f"❌ File not found: {file_path}")
    exit()

# Scale up to real goal dimensions: width = 7.32m, height = 2.44m
GOAL_WIDTH = 7.32
GOAL_HEIGHT = 2.44

# Convert relative coordinates (0–1) to goal dimensions
scaled_shots = [(x * GOAL_WIDTH, y * GOAL_HEIGHT, color) for x, y, color in penalty_shots]

# Plot
fig, ax = plt.subplots(figsize=(10, 4))  # Wider figure
ax.add_patch(plt.Rectangle((0, 0), GOAL_WIDTH, GOAL_HEIGHT, edgecolor='black', facecolor='none', lw=2))

for x, y, color in scaled_shots:
    ax.plot(x, y, 'o', color=color, markersize=12)

ax.set_xlim(-0.5, GOAL_WIDTH + 0.5)
ax.set_ylim(-0.1, GOAL_HEIGHT + 0.1)
ax.set_aspect('equal')
ax.set_xticks([])
ax.set_yticks([])
ax.set_title(f"Penalty Shot Map: {player_name} (Green = Goal, Red = Miss)")

plt.show()
