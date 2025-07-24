import json
import glob
import os
import csv

SPECIFIC_TAG_IDS = {101, 701, 702, 703, 302}  # Goal, Duel outcomes, Assist, Secondary Assist

def fix_unicode_escapes(s):
    try:
        if isinstance(s, str) and "\\u" in s:
            decoded = bytes(s, "utf-8").decode("unicode_escape")
            if any(ord(c) > 127 for c in decoded):
                return decoded
    except Exception:
        pass
    return s

def get_all_players(players_file='players.json'):
    with open(players_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def filter_tags(tags):
    tag_ids = [tag.get('id') for tag in tags if tag.get('id') is not None]
    specific_tags = [tid for tid in tag_ids if tid in SPECIFIC_TAG_IDS]
    return specific_tags if specific_tags else tag_ids

def format_tag_string(tag_ids):
    return ", ".join(str(tid) for tid in tag_ids) if tag_ids else ""

def extract_all_player_events(players_file='players.json', events_folder='events', output_folder='player_events_output'):
    players = get_all_players(players_file)
    os.makedirs(output_folder, exist_ok=True)

    # Preload all event files once
    all_events = []
    for filepath in glob.glob(f"{events_folder}/events_*.json"):
        with open(filepath, 'r', encoding='utf-8') as f:
            all_events.extend(json.load(f))

    for player in players:
        short_name = (
            player.get('shortName')
            or player.get('short_name')
            or player.get('shortname')
            or ''
        )
        short_name = fix_unicode_escapes(short_name)

        player_id = (
            player.get('wyId')
            or player.get('playerId')
            or player.get('id')
            or player.get('player_id')
        )
        if not short_name or not player_id:
            continue

        safe_name = short_name.replace('/', '_').replace('\\', '_')
        output_file = os.path.join(output_folder, f"{safe_name}_events.csv")
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['eventName', 'subEventName', 'startX', 'startY', 'endX', 'endY', 'tags']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            total = 0
            for event in all_events:
                if event.get('playerId') == player_id:
                    positions = event.get('positions', [])
                    start_x = positions[0]['x'] if len(positions) >= 1 else ""
                    start_y = positions[0]['y'] if len(positions) >= 1 else ""
                    end_x = positions[1]['x'] if len(positions) >= 2 else ""
                    end_y = positions[1]['y'] if len(positions) >= 2 else ""

                    tag_str = format_tag_string(filter_tags(event.get('tags', [])))

                    writer.writerow({
                        'eventName': event.get('eventName', ''),
                        'subEventName': event.get('subEventName', ''),
                        'startX': start_x,
                        'startY': start_y,
                        'endX': end_x,
                        'endY': end_y,
                        'tags': tag_str
                    })
                    total += 1

        print(f"Saved {total} events for {short_name} → {output_file}")

if __name__ == "__main__":
    extract_all_player_events()
