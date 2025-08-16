import json
import pandas as pd
from collections import defaultdict
import os
import re
from math import dist
import codecs

# File paths
EVENTS_DIR = "./events"
PLAYERS_FILE = "./data/players.json"
POSITIONS_OUTPUT_FILE = "./positions/player_positions.csv"
PRIMARY_OUTPUT_FILE = "./positions/player_primary_positions.csv"

ROLE_CENTERS = {
    "gk": (5, 50),        # Goalkeeper

    # Defenders
    "cb": (20, 50),
    "rb": (26, 22),
    "lb": (26, 78),

    # Defensive Midfielder
    "cdm": (40, 50),

    # Central Midfielders
    "cm": (47, 50),
    "rcm": (47, 42),
    "lcm": (47, 58),

    # Attacking Midfielders
    "cam": (55, 50),
    "ram": (55, 40),
    "lam": (55, 60),

    # Wingers
    "rw": (69, 34),
    "lw": (69, 66),

    # Striker
    "st": (76, 50),
}

CATEGORY_TO_ROLES = {
    "gk": {"gk"},
    "df": {"rb", "lb", "cb"},
    "md": {"cdm", "rcm", "lcm", "cam", "ram", "lam", "cm"},
    "fw": {"st", "rw", "lw"},
}

ROLE_MAP = {
    "GK": "gk", "GKP": "gk",
    "DF": "df", "DEF": "df",
    "MD": "md", "MID": "md",
    "FW": "fw", "FWD": "fw"
}

# Events to skip
EXCLUDE_EVENTS = {
    "Free Kick", "Corner", "Throw In", "Goalkeeper",
    "Offside", "Goal Kick", "Substitution", "Injury", "Whistle"
}

# Events that contribute to playstyle analysis
PLAYSTYLE_EVENTS = {
    "Pass", "Shot", "Duel", "Foul", "Touch", "Carry"
}

def clean_name(name):
    """Decode and clean player names"""
    if not isinstance(name, str):
        return ""
    if "\\u" in name:
        try:
            name = codecs.decode(name, "unicode_escape")
        except:
            pass
    name = re.sub(r'[\uE000-\uF8FF\u200B-\u200F\u2060-\u206F]', '', name)
    return name.strip()

def get_closest_role(x, y):
    """Find the closest role to given (x, y) coordinates"""
    return min(ROLE_CENTERS.items(), key=lambda item: dist((x, y), item[1]))[0]

def load_player_data():
    """Load and process player metadata"""
    with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
        players_raw = json.load(f)

    player_id_to_name = {}
    player_id_to_type = {}

    for p in players_raw:
        pid = p["wyId"]
        
        # Extract and clean name
        name = p.get("shortName") or f'{p.get("firstName", "")} {p.get("lastName", "")}'.strip()
        name = clean_name(name)
        player_id_to_name[pid] = name

        # Extract role category
        role_obj = p.get("role", {})
        raw_code = role_obj.get("code3") or role_obj.get("code2") or ""
        player_id_to_type[pid] = ROLE_MAP.get(raw_code.upper(), "unknown")

    return player_id_to_name, player_id_to_type

def process_event_data(player_id_to_name):
    """Process all event files to count player positions and collect playstyle stats"""
    player_roles = defaultdict(lambda: defaultdict(int))
    player_stats = defaultdict(lambda: {
        'passes': 0, 'successful_passes': 0, 'key_passes': 0, 'assists': 0,
        'shots': 0, 'goals': 0, 'duels': 0, 'successful_duels': 0,
        'avg_x_position': [], 'total_events': 0, 'touches': 0,
        'dribbles': 0, 'successful_dribbles': 0, 'avg_y_position': [],
        'aerial_duels': 0, 'successful_aerial_duels': 0,
        'crosses': 0, 'successful_crosses': 0
    })
    
    included = excluded = missing_xy = skipped_no_player = 0

    # Process all event files
    event_files = [f for f in os.listdir(EVENTS_DIR) if f.startswith("events_") and f.endswith(".json")]

    for filename in event_files:
        filepath = os.path.join(EVENTS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            events = json.load(f)

        for event in events:
            player_id = event.get("playerId")
            if not player_id:
                skipped_no_player += 1
                continue

            if event.get("eventName") in EXCLUDE_EVENTS:
                excluded += 1
                continue

            positions = event.get("positions")
            if not positions or "x" not in positions[0] or "y" not in positions[0]:
                missing_xy += 1
                continue

            x, y = positions[0]["x"], positions[0]["y"]
            role = get_closest_role(x, y)
            player_roles[player_id][role] += 1
            included += 1

            # Collect playstyle statistics
            event_name = event.get("eventName", "")
            sub_event_name = event.get("subEventName", "")
            tags = event.get("tags", [])
            if event_name in PLAYSTYLE_EVENTS:
                stats = player_stats[player_id]
                stats['avg_x_position'].append(x)
                stats['avg_y_position'].append(y)
                stats['total_events'] += 1
                
                # Pass statistics
                if event_name == "Pass":
                    stats['passes'] += 1
                    for tag in tags:
                        if tag.get("id") == 1801:
                            stats["successful_passes"] += 1
                        if tag.get("id") == 302:  # Key pass tag
                            stats['key_passes'] += 1
                        if tag.get("id") == 301:  # Assist tag
                            stats['assists'] += 1
                
                # Shot statistics
                if event_name == "Shot":
                    stats['shots'] += 1
                    for tag in tags:
                        if tag.get("id") == 101:  # Goal tag
                            stats['goals'] += 1
                
                # Dribble statistics
                if event_name == "Duel" and any(tag.get("id") == 1801 for tag in event.get("tags", [])):
                    stats['duels'] += 1
                    if sub_event_name == "Air Duel":
                        stats['aerial_duels'] += 1
                    for tag in tags:
                        if tag.get("id") == 1801:
                            stats['successful_duels'] += 1
                            if sub_event_name == "Air Duel":
                                stats['successful_aerial_duels'] += 1
                            break
                
                # Touch count
                if event_name in {"Pass"} or sub_event_name == "Touch":
                    stats["touches"] += 1

                if sub_event_name == "Acceleration":
                    stats["dribbles"] += 1
                    for tag in tags:
                        if tag.get("id") == 1801:
                            stats["successful_dribbles"] += 1
                            break

                if "cross" in sub_event_name.lower():
                    stats['crosses'] += 1
                    for tag in tags:
                        if tag.get("id") == 1801:
                            stats["successful_crosses"] += 1
                            break


    print(f"Event processing stats - Included: {included}, Excluded: {excluded}, No XY: {missing_xy}, No playerId: {skipped_no_player}")
    return player_roles, player_stats

def save_position_frequencies(player_roles, player_id_to_name):
    """Save detailed position frequency data"""
    records = []
    for player_id, roles in player_roles.items():
        name = player_id_to_name.get(player_id, f"Unknown ({player_id})")
        for role, count in roles.items():
            records.append({
                "playerId": player_id,
                "name": name,
                "role": role,
                "count": count
            })

    df = pd.DataFrame(records)
    df = df.sort_values(by=["name", "count"], ascending=[True, False])
    os.makedirs(os.path.dirname(POSITIONS_OUTPUT_FILE), exist_ok=True)
    df.to_csv(POSITIONS_OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"Saved player role frequencies to {POSITIONS_OUTPUT_FILE}")
    return df

def classify_cam_playstyle(player_id, stats):
    """Classify CAM players into specific playstyles based on their statistics"""
    if stats['total_events'] < 30:  
        return "am" 
    
    pass_rate = (stats['passes'] / stats['total_events']) * 100 if stats['total_events'] > 0 else 0
    shot_rate = (stats['shots'] / stats['total_events']) * 100 if stats['total_events'] > 0 else 0
    dribble_rate = (stats['dribbles'] / stats['total_events']) * 100 if stats['total_events'] > 0 else 0
    
    pass_accuracy = stats['successful_passes'] / stats['passes'] if stats['passes'] > 0 else 0
    dribble_success = stats['successful_dribbles'] / stats['dribbles'] if stats['dribbles'] > 0 else 0
    
    key_pass_rate = (stats['key_passes'] / stats['total_events']) * 100 if stats['total_events'] > 0 else 0
    assist_rate = (stats['assists'] / stats['total_events']) * 100 if stats['total_events'] > 0 else 0
    goal_rate = (stats['goals'] / stats['total_events']) * 100 if stats['total_events'] > 0 else 0
    
    avg_x = sum(stats['avg_x_position']) / len(stats['avg_x_position']) if stats['avg_x_position'] else 55
    
    touch_rate = (stats['touches'] / stats['total_events']) * 100 if stats['total_events'] > 0 else 0
    
    ss_score = (
        (shot_rate / 5) * 3 +
        (goal_rate / 0.5) * 2 +
        ((avg_x - 56) / 2) * 1.5 +
        (1 if shot_rate > pass_rate * 0.2 else 0)
    )

    ap_score = (
        (pass_rate / 40) * 2.5 +
        (assist_rate / 1.0) * 1.3 +
        (key_pass_rate / 2) * 1.2 +
        (pass_accuracy * 1.5) +
        ((55 - avg_x) / 2) * 1.0 +
        (1 if pass_rate > shot_rate * 5 else 0)
    )

    tq_score = (
        (dribble_rate / 12) * 3 +
        (key_pass_rate / 2) * 2 +
        (dribble_success * 4) +
        (touch_rate / 13) +
        (2 if dribble_rate > shot_rate else 0)
    )

    am_score = (
        2 + (pass_rate / 30) * 0.8 + (dribble_rate / 6) * 0.6
    )

    scores = {
        "ss": ss_score,
        "ap": ap_score,
        "tq": tq_score,
        "am": am_score
    }

    min_thresholds = {
        "ss": 6,
        "ap": 6,
        "tq": 6,
        "am": 0
    }

    valid_scores = {k: v for k, v in scores.items() if v >= min_thresholds[k]}
    
    if not valid_scores:
        return "am"
    
    best_playstyle = max(valid_scores.items(), key=lambda x: x[1])[0]
    
    return best_playstyle

def classify_cm_rcm_lcm_playstyle(player_id, stats):
    if stats['total_events'] < 30:
        return "cm"
    
    pass_rate = (stats['passes'] / stats['total_events']) * 100
    touch_rate = (stats['touches'] / stats['total_events']) * 100
    key_pass_rate = (stats['key_passes'] / stats['total_events']) * 100
    duels_rate = (stats['duels'] / stats['total_events']) * 100

    avg_x = sum(stats['avg_x_position']) / len(stats['avg_x_position']) if stats['avg_x_position'] else 69
    avg_y = abs(50 - sum(stats['avg_y_position']) / len(stats['avg_y_position'])) if stats['avg_y_position'] else 16

    cm_score = (
        (pass_rate / 15) +
        (touch_rate / 15) +
        (key_pass_rate / 3) +
        ((45 - avg_x) / 3)
    )

    bwm_score = (
        (pass_rate / 30) +
        (touch_rate / 25) +
        (duels_rate / 8) +
        ((avg_y - 10) / 8) +
        ((20 - avg_y) / 8)
    )

    mz_score = (
        (pass_rate / 13) +
        (touch_rate / 13) +
        ((avg_y - 25) / 3) +
        (key_pass_rate / 3)
    )

    dlp_score = (
        (duels_rate / 5) +
        (touch_rate / 20) +
        ((42 - avg_x) / 4) +
        (pass_rate / 20)
    )

    scores = {
        "cm": cm_score,
        "mz": mz_score,
        "bwm": bwm_score,
        "dlp": dlp_score
    }

    min_thresholds = {
        "bwm": 6,
        "mz": 6,
        "dlp": 6,
        "cm": 0
    }

    valid_scores = {k: v for k, v in scores.items() if v >= min_thresholds[k]}
    
    if not valid_scores:
        return "cm"
    
    best_playstyle = max(valid_scores.items(), key=lambda x: x[1])[0]
    
    return best_playstyle

def classify_cdm_playstyle(player_id, stats):
    if stats['total_events'] < 30:
        return "dm"
    
    pass_rate = (stats['passes'] / stats['total_events']) * 100
    dribble_rate = (stats['dribbles'] / stats['total_events']) * 100
    touch_rate = (stats['touches'] / stats['total_events']) * 100
    duels_rate = (stats['duels'] / stats['total_events']) * 100
    duels_rate = (stats['duels'] / stats['total_events']) * 100

    avg_x = sum(stats['avg_x_position']) / len(stats['avg_x_position']) if stats['avg_x_position'] else 69

    dm_score = (
        (pass_rate / 17) +
        (touch_rate / 17) +
        (dribble_rate / 5) +
        ((30 - avg_x) / 3)
    )

    hb_score = (
        (pass_rate / 20) +
        (touch_rate / 20) +
        (dribble_rate / 6) +
        ((25 - avg_x) / 2) +
        (duels_rate / 3)
    )

    a_score = (
        (pass_rate / 30) +
        (touch_rate / 30) +
        (dribble_rate / 12) +
        (duels_rate / 12)
    )

    scores = {
        "dm": dm_score,
        "hb": hb_score,
        "a": a_score
    }

    min_thresholds = {
        "dm": 0,
        "hb": 6,
        "a": 6
    }

    valid_scores = {k: v for k, v in scores.items() if v >= min_thresholds[k]}
    
    if not valid_scores:
        return "dm"
    
    best_playstyle = max(valid_scores.items(), key=lambda x: x[1])[0]
    
    return best_playstyle

def classify_cb_playstyle(player_id, stats):
    if stats['total_events'] < 30:
        return "cb"
    
    pass_rate = (stats['passes'] / stats['total_events']) * 100
    duels_rate = (stats['duels'] / stats['total_events']) * 100
    duels_rate = (stats['duels'] / stats['total_events']) * 100

    cb_score = (
        ((duels_rate - 10) / 2) +
        (pass_rate / 20)
    )

    bpd_score = (
        ((15 - duels_rate) / 2) + 
        ((pass_rate / 10))
    )

    scores = {
        "cb": cb_score,
        "bpd": bpd_score
    }

    min_thresholds = {
        "cb": 0,
        "bpd": 6
    }

    valid_scores = {k: v for k, v in scores.items() if v >= min_thresholds[k]}
    
    if not valid_scores:
        return "cb"
    
    best_playstyle = max(valid_scores.items(), key=lambda x: x[1])[0]
    
    return best_playstyle

def classify_ram_lam_playstyle(player_id, stats):
    if stats['total_events'] < 30:
        return "wm"

    
    pass_rate = (stats['passes'] / stats['total_events']) * 100
    shot_rate = (stats['shots'] / stats['total_events']) * 100
    dribble_rate = (stats['dribbles'] / stats['total_events']) * 100
    touch_rate = (stats['touches'] / stats['total_events']) * 100
    key_pass_rate = (stats['key_passes'] / stats['total_events']) * 100

    pass_accuracy = stats['successful_passes'] / stats['passes'] if stats['passes'] else 0
    dribble_success = stats['successful_dribbles'] / stats['dribbles'] if stats['dribbles'] else 0
    avg_x = sum(stats['avg_x_position']) / len(stats['avg_x_position']) if stats['avg_x_position'] else 55

    
    w_score = (
        (dribble_success * 1.8) +
        (dribble_rate / 11) +
        ((avg_x - 58)) +
        (touch_rate / 13) +
        (1 if dribble_rate > pass_rate else 0)
    )

    wp_score = (
        (pass_rate / 35) * 2 +
        (key_pass_rate / 2) * 1.7 +
        (pass_accuracy * 2) +
        ((58 - avg_x)) +
        (1 if pass_rate > shot_rate * 3 else 0)
    )

    wm_score = (
        4 +
        (2 if avg_x < 56 else 0) +
        (1.2 if pass_rate > 18 else 0) +
        (1 if dribble_rate < 6 else 0)
    )

    scores = {
        "w": w_score,
        "wp": wp_score,
        "wm": wm_score
    }

    min_thresholds = {
        "w": 6,
        "wp": 6,
        "wm": 0
    }



    valid_scores = {k: v for k, v in scores.items() if v >= min_thresholds[k]}
    if not valid_scores:
        return "wm"
    
    return max(valid_scores.items(), key=lambda x: x[1])[0]

def classify_st_playstyle(player_id, stats):
    if stats['total_events'] < 30:
        return "af"

    
    pass_rate = (stats['passes'] / stats['total_events']) * 100
    shot_rate = (stats['shots'] / stats['total_events']) * 100
    dribble_rate = (stats['dribbles'] / stats['total_events']) * 100
    touch_rate = (stats['touches'] / stats['total_events']) * 100
    key_pass_rate = (stats['key_passes'] / stats['total_events']) * 100
    goal_rate = (stats['goals'] / stats['total_events']) * 100
    assist_rate = (stats['assists'] / stats['total_events']) * 100
    aerial_duels_rate = (stats['aerial_duels'] / stats['total_events']) * 100

    dribble_success = stats['successful_dribbles'] / stats['dribbles'] if stats['dribbles'] else 0
    avg_x = sum(stats['avg_x_position']) / len(stats['avg_x_position']) if stats['avg_x_position'] else 55

    
    af_score = (
        (shot_rate / 10) * 2 +
        (dribble_rate / 7) + 
        (goal_rate) * 2.5 +
        (touch_rate / 13) +
        (avg_x - 73) + 
        (1 if shot_rate > key_pass_rate else 0)
    )

    
    f9_score = (
        key_pass_rate + 
        (pass_rate / 25) + 
        (62 - avg_x) * 1.7 +
        (touch_rate / 14) + 
        (dribble_rate / 10) + 
        (dribble_success) * 1.8
    )

    dlf_score = (
        (aerial_duels_rate) * 2.5 +
        (pass_rate / 20) + 
        (67 - avg_x) * 0.5 +
        (avg_x - 62) * 0.5 +
        (goal_rate) * 1.5 + 
        (assist_rate) * 2.5
    )
    
    cf_score = (
        (shot_rate / 12) * 3 +
        (goal_rate) +
        (assist_rate) * 1.6 +
        (dribble_rate) +
        (key_pass_rate) * 1.3 +
        (touch_rate / 12) +
        (aerial_duels_rate) * 1.3
    )

    scores = {
        "af": af_score,     
        "f9": f9_score,
        "dlf": dlf_score,
        "cf": cf_score
    }

    min_thresholds = {
        "f9": 6,
        "dlf": 6,
        "cf": 6,
        "af": 0
    }


    valid_scores = {k: v for k, v in scores.items() if v >= min_thresholds[k]}
    if not valid_scores:
        return "af"
    
    return max(valid_scores.items(), key=lambda x: x[1])[0]

def classify_rw_lw_playstyle(player_id, stats):
    if stats['total_events'] < 30:
        return "w"

    
    shot_rate = (stats['shots'] / stats['total_events']) * 100
    dribble_rate = (stats['dribbles'] / stats['total_events']) * 100
    touch_rate = (stats['touches'] / stats['total_events']) * 100
    key_pass_rate = (stats['key_passes'] / stats['total_events']) * 100
    goal_rate = (stats['goals'] / stats['total_events']) * 100
    assist_rate = (stats['assists'] / stats['total_events']) * 100
    cross_rate = (stats['crosses'] / stats['total_events']) * 100

    avg_y = abs(50 - sum(stats['avg_y_position']) / len(stats['avg_y_position'])) if stats['avg_y_position'] else 16

    w_score = (
        (dribble_rate) * 5 +
        ((avg_y - 20) / 4) + 
        (cross_rate) +
        (key_pass_rate) + 
        (assist_rate) * 0.7 +
        (shot_rate) * 0.4
    )   

    iw_score = (
        (dribble_rate) +
        ((20 - avg_y) / 4) + 
        ((avg_y - 12) / 4) +
        (cross_rate) * 0.6 +
        (key_pass_rate) * 1.2 + 
        (assist_rate) * 0.6 +
        (goal_rate) +
        (shot_rate) * 0.5
    ) 

    if_score = (
        ((12 - avg_y) / 4) + 
        (touch_rate / 9) +
        (goal_rate) * 0.9 +
        (key_pass_rate) * 0.6 +
        (dribble_rate) * 0.4
    )

    scores = {
        "w": w_score,
        "iw": iw_score,
        "if": if_score,
    }

    min_thresholds = {
        "iw": 6,
        "if": 6,
        "rmd": 6,
        "w": 0
    }


    valid_scores = {k: v for k, v in scores.items() if v >= min_thresholds[k]}
    if not valid_scores:
        return "w"
    
    return max(valid_scores.items(), key=lambda x: x[1])[0]

def classify_rb_lb_playstyle(player_id, stats):
    if stats['total_events'] < 30:
        return "fb"

    avg_x = sum(stats['avg_x_position']) / len(stats['avg_x_position']) if stats['avg_x_position'] else 26
    avg_y = abs(50 - sum(stats['avg_y_position']) / len(stats['avg_y_position'])) if stats['avg_y_position'] else 28

    fb_score = (
        (30 - avg_x) +
        (avg_y - 15)
    )

    wb_score = (
        (avg_x - 35) +
        (20 - avg_y)
    )

    scores = {
        "fb": fb_score,
        "wb": wb_score
    }

    min_thresholds = {
        "fb": 0,
        "wb": 0
    }


    valid_scores = {k: v for k, v in scores.items() if v >= min_thresholds[k]}
    if not valid_scores:
        return "fb" if fb_score > wb_score else "wb"
    
    return max(valid_scores.items(), key=lambda x: x[1])[0]

def assign_primary_positions(player_roles, player_id_to_name, player_id_to_type, player_stats):
    """Assign primary positions and specific playstyles based on position frequency data"""
    records = []

    for player_id, role_counts in player_roles.items():
        if not role_counts:
            continue

        name = clean_name(player_id_to_name.get(player_id, f"Unknown ({player_id})"))
        total = sum(role_counts.values())

        if total == 0:
            continue

        # Calculate centroid
        sum_x = sum_y = 0
        for role, count in role_counts.items():
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

        if raw_best_fit in allowed_roles:
            best_fit = raw_best_fit
        else:
            # Find closest allowed role
            best_fit = min(
                ((role, ROLE_CENTERS[role]) for role in allowed_roles if role in ROLE_CENTERS),
                key=lambda item: dist(centroid, item[1])
            )[0]

        playstyle = None
        
        if best_fit == "cam":
            playstyle = classify_cam_playstyle(player_id, player_stats.get(player_id, {}))
        elif best_fit in {"ram", "lam"}:
            playstyle = classify_ram_lam_playstyle(player_id, player_stats.get(player_id, {}))
        elif best_fit == "st":
            playstyle = classify_st_playstyle(player_id, player_stats.get(player_id, {}))
        elif best_fit in {"rw", "lw"}:
            playstyle = classify_rw_lw_playstyle(player_id, player_stats.get(player_id, {}))
        elif best_fit in {"cm", "rcm", "lcm"}:
            playstyle = classify_cm_rcm_lcm_playstyle(player_id, player_stats.get(player_id, {}))
        elif best_fit == "cdm":
            playstyle = classify_cdm_playstyle(player_id, player_stats.get(player_id, {}))
        elif best_fit in {"lb", "rb"}:
            playstyle = classify_rb_lb_playstyle(player_id, player_stats.get(player_id, {}))
        elif best_fit == "cb":
            playstyle = classify_cb_playstyle(player_id, player_stats.get(player_id, {}))
        records.append({
            "playerId": player_id,
            "name": name,
            "category": category,
            "best_fit_role": best_fit,
            "raw_best_fit_role": raw_best_fit,
            "playstyle": playstyle
        })

    return records

def save_primary_positions(records):
    """Save primary position assignments with playstyles"""
    out_df = pd.DataFrame(records)
    out_df = out_df.sort_values(by="name")
    os.makedirs(os.path.dirname(PRIMARY_OUTPUT_FILE), exist_ok=True)
    out_df.to_csv(PRIMARY_OUTPUT_FILE, index=False, encoding="utf-8")

    # Diagnostic summary
    total = len(out_df)
    unknown_count = sum(out_df["category"] == "unknown")
    percent = round(100 * unknown_count / total, 2) if total > 0 else 0
    
    print(f"Saved player primary positions to {PRIMARY_OUTPUT_FILE}")
    print(f"{unknown_count}/{total} players ({percent}%) had unknown role categories.")

    # Print count of players per best_fit_role
    print("\nBest-fit role distribution:")
    role_counts = out_df["best_fit_role"].value_counts().sort_index()
    for role, count in role_counts.items():
        print(f"{role:4s}: {count}")
    
    playstyle_assigned_players = out_df[out_df["playstyle"].notna()]
    if len(playstyle_assigned_players) > 0:
        print("\nPlaystyle distribution:")
        playstyle_counts = playstyle_assigned_players["playstyle"].value_counts()
        for style, count in playstyle_counts.items():
            print(f"{style:2s}: {count}")


def main():
    """Main execution function"""
    print("=== Starting merged player position analysis with playstyles ===")
    
    # Load player metadata
    print("Loading player data...")
    player_id_to_name, player_id_to_type = load_player_data()
    
    # Process event data to count positions and collect stats
    print("Processing event data...")
    player_roles, player_stats = process_event_data(player_id_to_name)
    
    # Save detailed position frequencies
    print("Saving position frequencies...")
    position_df = save_position_frequencies(player_roles, player_id_to_name)
    
    # Assign and save primary positions with playstyles
    print("Assigning primary positions and playstyles...")
    primary_records = assign_primary_positions(player_roles, player_id_to_name, player_id_to_type, player_stats)
    save_primary_positions(primary_records)
    
    print("=== Analysis complete ===")

if __name__ == "__main__":
    main()