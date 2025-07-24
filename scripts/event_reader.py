import json
import glob
import os
import csv

def find_player_id_by_shortname(short_name, players_file='./data/players.json'):
    with open(players_file, 'r', encoding='utf-8') as f:
        players = json.load(f)
    for player in players:
        player_short = player.get('shortName') or player.get('short_name') or player.get('shortname') or ''
        if player_short.strip().lower() == short_name.strip().lower():
            return player.get('wyId') or player.get('playerId') or player.get('id') or player.get('player_id')
    return None

def extract_player_events_csv(short_name, players_file='./data/players.json', events_folder='./events', output_folder='./player_events_output'):
    player_id = find_player_id_by_shortname(short_name, players_file)
    if player_id is None:
        print(f"Player with short name '{short_name}' not found in {players_file}")
        return

    print(f"Found player '{short_name}' with ID {player_id}")

    os.makedirs(output_folder, exist_ok=True)
    output_file = os.path.join(output_folder, f"{short_name}_events.csv")

    total_events = 0
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['eventName', 'subEventName', 'startX', 'startY', 'endX', 'endY', 'tags']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for filepath in glob.glob(f"{events_folder}/events_*.json"):
            with open(filepath, 'r', encoding='utf-8') as f:
                events = json.load(f)

            for event in events:
                if event.get('playerId') == player_id:
                    positions = event.get('positions', [])
                    start_x = positions[0]['x'] if len(positions) >= 1 else ""
                    start_y = positions[0]['y'] if len(positions) >= 1 else ""
                    end_x = positions[1]['x'] if len(positions) >= 2 else ""
                    end_y = positions[1]['y'] if len(positions) >= 2 else ""

                    # Extract all tag IDs (no filtering)
                    tag_ids = [str(tag.get('id')) for tag in event.get('tags', []) if tag.get('id') is not None]
                    tag_str = ", ".join(tag_ids)

                    writer.writerow({
                        'eventName': event.get('eventName', ''),
                        'subEventName': event.get('subEventName', ''),
                        'startX': start_x,
                        'startY': start_y,
                        'endX': end_x,
                        'endY': end_y,
                        'tags': tag_str
                    })
                    total_events += 1

    print(f"Extracted {total_events} events for player '{short_name}' into {output_file}")

if __name__ == "__main__":
    short_name_input = input("Enter player short name (exact match): ")
    extract_player_events_csv(short_name_input)
