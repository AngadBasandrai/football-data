import os
import math
import numpy as np
import matplotlib.pyplot as plt
from mplsoccer import Pitch
from scipy.stats import gaussian_kde
import csv

DATA_DIR = ""
EVENTS_FOLDER = "player_events_output"
SAVE_FOLDER = "player_event_data"

COLORMAP = 'plasma'
SUCCESS_TAGS = {101, 701, 302, 1801}
FAIL_TAGS = {1802, 702, 703}

def load_player_events(short_name):
    filepath = os.path.join(DATA_DIR, EVENTS_FOLDER, f"{short_name}_events.csv")
    if not os.path.exists(filepath):
        print(f"Event CSV file for player '{short_name}' not found at {filepath}")
        return None

    events = []
    with open(filepath, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                sx = float(row['startX']) * 1.2
                sy = float(row['startY']) * 0.8
                ex = float(row['endX']) * 1.2
                ey = float(row['endY']) * 0.8
            except:
                continue
            events.append({
                'eventName': row['eventName'],
                'subEventName': row['subEventName'],
                'startX': sx, 'startY': sy,
                'endX': ex, 'endY': ey,
                'tags': row['tags']
            })
    return events

def arrow_color(tags_str):
    tags = set(int(t.strip()) for t in tags_str.split(',') if t.strip().isdigit())
    if tags & SUCCESS_TAGS:
        return 'green'
    if tags & FAIL_TAGS:
        return 'red'
    return 'gray'

def is_corner_or_invalid(x, y):
    return (x, y) in [(0, 0), (0, 80), (120, 0), (120, 80)] or x < 0 or x > 120 or y < 0 or y > 80

def plot_kde(ax, x, y, title):
    if not x:
        ax.set_title(f"{title}\n(No data)", fontsize=10)
        return
    try:
        xy = np.vstack([x, y])
        kde = gaussian_kde(xy)
        xgrid, ygrid = np.meshgrid(np.linspace(0, 120, 300), np.linspace(0, 80, 200))
        z = kde(np.vstack([xgrid.ravel(), ygrid.ravel()])).reshape(xgrid.shape)
        z /= z.max()
        ax.pcolormesh(xgrid, ygrid, z, shading='gouraud', cmap=COLORMAP, alpha=0.7)
        ax.scatter(x, y, s=3, color='gray', alpha=0.1, zorder=10)
    except:
        ax.set_title(f"{title}\n(KDE failed)", fontsize=10)

def plot_directions(ax, events):
    for ev in events:
        sx, sy, ex, ey = ev['startX'], ev['startY'], ev['endX'], ev['endY']
        color = arrow_color(ev['tags'])
        if is_corner_or_invalid(ex, ey):
            ax.scatter(sx, sy, color=color, s=15, alpha=1, zorder=10)
        else:
            ax.arrow(sx, sy, ex - sx, ey - sy, head_width=1.5, head_length=2,
                     length_includes_head=True, color=color, alpha=1, lw=0.8)

def save_event_figures(short_name, event_groups):
    out_dir = os.path.join(SAVE_FOLDER, f"{short_name}_data")
    os.makedirs(out_dir, exist_ok=True)

    for event_name, subev_dict in event_groups.items():
        subevents = sorted(subev_dict.keys())
        n_rows = len(subevents)

        fig, axs = plt.subplots(n_rows, 2, figsize=(8, 3 * n_rows))
        if n_rows == 1:
            axs = np.array([axs])  # keep 2D shape

        pitch = Pitch(pitch_type='statsbomb', pitch_color='white', line_color='black')

        for i, subev in enumerate(subevents):
            evs = subev_dict[subev]
            x = [e['startX'] for e in evs]
            y = [e['startY'] for e in evs]

            pitch.draw(ax=axs[i][0])
            plot_kde(axs[i][0], x, y, "")
            axs[i][0].set_title(f"{subev} (heatmap)", fontsize=10)

            pitch.draw(ax=axs[i][1])
            plot_directions(axs[i][1], evs)
            axs[i][1].set_title(f"{subev} (arrows/dots)", fontsize=10)

        fig.suptitle(f"{event_name} - {short_name}", fontsize=14)
        plt.tight_layout(rect=[0, 0, 1, 0.95])
        save_path = os.path.join(out_dir, f"{event_name}_combined.png")
        plt.savefig(save_path, dpi=300)
        plt.close()
        print(f"Saved: {save_path}")

def save_summary_plots(short_name, event_groups):
    out_dir = os.path.join(SAVE_FOLDER, f"{short_name}_data")
    os.makedirs(out_dir, exist_ok=True)

    for mode in ['heatmap', 'direction']:
        n = len(event_groups)
        n_cols = 3
        n_rows = math.ceil(n / n_cols)
        fig, axs = plt.subplots(n_rows, n_cols, figsize=(4*n_cols, 3*n_rows))
        axs = axs.flatten()
        pitch = Pitch(pitch_type='statsbomb', pitch_color='white', line_color='black')

        for i, (event_name, subev_dict) in enumerate(event_groups.items()):
            ax = axs[i]
            pitch.draw(ax=ax)
            events = [ev for evs in subev_dict.values() for ev in evs]
            if mode == 'heatmap':
                x = [ev['startX'] for ev in events]
                y = [ev['startY'] for ev in events]
                plot_kde(ax, x, y, "")
            else:
                plot_directions(ax, events)
            ax.set_title(event_name, fontsize=10)

        for j in range(i+1, len(axs)):
            fig.delaxes(axs[j])

        title = f"{short_name} - {'Start Heatmaps' if mode=='heatmap' else 'Arrows/Dots'}"
        fig.suptitle(title, fontsize=16)
        plt.tight_layout(rect=[0, 0, 1, 0.95])
        fname = f"summary_{mode}.png"
        plt.savefig(os.path.join(out_dir, fname), dpi=300)
        plt.close()
        print(f"Saved summary: {fname}")

def main():
    short_name = input("Enter player short name (exact): ").strip()
    events = load_player_events(short_name)
    if not events:
        return

    event_groups = {}
    for ev in events:
        event_groups.setdefault(ev['eventName'], {}).setdefault(ev['subEventName'], []).append(ev)

    save_event_figures(short_name, event_groups)
    save_summary_plots(short_name, event_groups)

if __name__ == "__main__":
    main()
