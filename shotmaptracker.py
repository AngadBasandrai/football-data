import os
import numpy as np
import matplotlib.pyplot as plt
from mplsoccer import Pitch
from scipy.stats import gaussian_kde

# --- Parameters ---
DATA_DIR = ""  # Dataset root
COLORMAP = 'plasma'

# --- Input ---
short_name = input("Enter player short name: ").strip()
file_path = os.path.join(DATA_DIR, "shot_tracking_output", f"{short_name}_shots.txt")

if not os.path.exists(file_path):
    print("Shot file not found.")
    exit()

# --- Categorize shots ---
all_x, all_y = [], []
goal_x, goal_y = [], []
miss_x, miss_y = [], []

with open(file_path, encoding="utf-8") as f:
    for line in f:
        if "at (" not in line:
            continue
        try:
            pos_str = line.strip().split("at (")[1].rstrip(")")
            x_str, y_str = pos_str.split(",")
            x = float(x_str) * 1.2
            y = float(y_str) * 0.8
        except:
            continue

        all_x.append(x)
        all_y.append(y)

        line_lower = line.lower()
        if "goal" in line_lower:
            goal_x.append(x)
            goal_y.append(y)
        else:
            miss_x.append(x)
            miss_y.append(y)

def plot_kde(ax, x, y, title):
    if not x:
        ax.set_title(f"{title}\n(No data)", fontsize=12)
        return

    # KDE heatmap
    xy = np.vstack([x, y])
    kde = gaussian_kde(xy)
    xgrid, ygrid = np.meshgrid(np.linspace(0, 120, 300), np.linspace(0, 80, 200))
    grid_coords = np.vstack([xgrid.ravel(), ygrid.ravel()])
    z = kde(grid_coords).reshape(xgrid.shape)
    z = z / z.max()
    ax.pcolormesh(xgrid, ygrid, z, shading='gouraud', cmap=COLORMAP, alpha=0.7)

    # Subtle dot overlay
    ax.scatter(x, y, s=3, color='gray', alpha=0.4, zorder=10)

    ax.set_title(title, fontsize=13)

# --- Plotting ---
pitch = Pitch(pitch_type='statsbomb', pitch_color='white', line_color='black')
fig, axs = pitch.draw(nrows=1, ncols=3, figsize=(18, 6))

plot_kde(axs[0], all_x, all_y, "All Shots")
plot_kde(axs[1], goal_x, goal_y, "Goals")
plot_kde(axs[2], miss_x, miss_y, "Misses")

fig.suptitle(f"Shot Heatmaps for {short_name}", fontsize=17)
plt.tight_layout()
save_path = os.path.join(DATA_DIR, "shot_heatmaps", f"{short_name}_heatmap.png")
os.makedirs(os.path.dirname(save_path), exist_ok=True)
plt.savefig(save_path, dpi=300, bbox_inches="tight")
print(f"Saved heatmap to {save_path}")
# plt.show()  # optional, if you still want to display it
