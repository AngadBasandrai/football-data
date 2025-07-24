import os
import json
from collections import defaultdict

PLAYERS_FILE = 'players.json'  # Your players file (list of dicts)
EVENTS_DIR = 'events'          # Directory containing event JSON files

def load_players():
    with open(PLAYERS_FILE, encoding='utf-8') as f:
        players = json.load(f)
    # Map shortName to player dict (id, role)
    player_map = {}
    for p in players:
        short_name = p.get('shortName', '').strip()
        if short_name:
            player_map[short_name] = {
                'id': p.get('wyId'),
                'role': p.get('role', {}).get('code2', 'Unknown')
            }
    return player_map

def load_all_events():
    all_events = []
    for fname in os.listdir(EVENTS_DIR):
        if fname.endswith('.json'):
            path = os.path.join(EVENTS_DIR, fname)
            with open(path, encoding='utf-8') as f:
                events = json.load(f)
                all_events.extend(events)
    return all_events

def main():
    player_map = load_players()
    all_events = load_all_events()

    player_shortname = input("Enter player short name (e.g. 'L. Messi'): ").strip()
    if player_shortname not in player_map:
        print(f"Player '{player_shortname}' not found.")
        return

    player_id = player_map[player_shortname]['id']

    # Count passes by this player: eventName == "Pass" and playerId matches
    passes_per_match = defaultdict(int)  # matchId -> count
    matches_played = set()

    for ev in all_events:
        if ev.get('playerId') == player_id:
            match_id = ev.get('matchId')
            if match_id is not None:
                matches_played.add(match_id)
                if ev.get('eventName', '').lower() == 'pass':
                    passes_per_match[match_id] += 1

    total_passes = sum(passes_per_match.values())
    total_matches = len(matches_played)

    if total_matches == 0:
        print(f"No match data found for player '{player_shortname}'.")
        return

    avg_passes_per_game = total_passes / total_matches

    print(f"Player: {player_shortname}")
    print(f"Total matches played: {total_matches}")
    print(f"Total passes: {total_passes}")
    print(f"Average passes per game: {avg_passes_per_game:.2f}")

if __name__ == "__main__":
    main()
