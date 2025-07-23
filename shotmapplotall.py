import os
import csv
import numpy as np
import matplotlib.pyplot as plt
from mplsoccer import Pitch
from scipy.stats import gaussian_kde

# --- Config ---
DATA_DIR = ""  # Dataset root
CSV_FILE = os.path.join(DATA_DIR, "all_shots_by_event", "events_World_Cup.csv")
COLORMAP = 'plasma'

# --- Shot groups ---
roles = ["Goalkeeper", "Defender", "Midfielder", "Forward"]
shots_by_role = {
    role: {"all": [], "goal": []} for role in roles
}

if not os.path.exists(CSV_FILE):
    print("World Cup shot file not found.")
    exit()

# --- Load and group ---
with open(CSV_FILE, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            x = float(row["x"]) * 1.2
            y = float(row["y"]) * 0.8
            role = row["role"]
            outcome = row["outcome"].lower()
        except:
            continue

        if role not in shots_by_role:
            continue

        shots_by_role[role]["all"].append((x, y))
        if "goal" in outcome:
            shots_by_role[role]["goal"].append((x, y))

# --- KDE Plotter ---
def plot_kde(ax, points, title):
    if not points:
        ax.set_title(f"{title}\n(No data)", fontsize=11)
        return

    x, y = zip(*points)
    xy = np.vstack([x, y])
    kde = gaussian_kde(xy)
    xgrid, ygrid = np.meshgrid(np.linspace(0, 120, 300), np.linspace(0, 80, 200))
    grid_coords = np.vstack([xgrid.ravel(), ygrid.ravel()])
    z = kde(grid_coords).reshape(xgrid.shape)
    z = z / z.max()
    ax.pcolormesh(xgrid, ygrid, z, shading='gouraud', cmap=COLORMAP, alpha=0.7)
    ax.scatter(x, y, s=3, color='gray', alpha=0.4, zorder=10)
    ax.set_title(title, fontsize=12)

# --- Plotting ---
pitch = Pitch(pitch_type='statsbomb', pitch_color='white', line_color='black')
fig, axs = pitch.draw(nrows=4, ncols=2, figsize=(16, 20))

for i, role in enumerate(roles):
    row = i
    plot_kde(axs[row][0], shots_by_role[role]["all"], f"{role} - All Shots")
    plot_kde(axs[row][1], shots_by_role[role]["goal"], f"{role} - Goals")

fig.suptitle("Shot Heatmaps by Role (World Cup)", fontsize=20)
plt.tight_layout()
plt.tight_layout()
save_path = os.path.join(DATA_DIR, "shot_heatmaps", "all_roles_heatmaps.png")
os.makedirs(os.path.dirname(save_path), exist_ok=True)
plt.savefig(save_path, dpi=300, bbox_inches="tight")
print(f"Saved heatmap to {save_path}")
# plt.show()  # optional

