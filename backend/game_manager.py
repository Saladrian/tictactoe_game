import copy
import datetime
import json
import logging
import os
import random
import string
import threading
import time


EXECUTE_PATH = os.getcwd()
PATH = os.path.dirname(__file__)

SESSIONS_FILE_PATH = f"{PATH}/data/sessions.json"


log = logging.getLogger(__name__)

lock = threading.Lock()

stats_template = {"wins": {"x": 0, "o": 0}, "matches": 0, "played_since": None}
room_template = {"is_public": True, "players": {}, "started": False, "turn": "", "fields": {}, "stats": stats_template, "last_change": 0}  # "viewer": []
# example session:
# {"rooms": { "room_id": {"is_public": True, "players": {}, "turn": "", "fields": {}, , "stats": {}, "last_change": 0}}
sessions: dict = {"rooms": {}}


def init() -> None:
    create_file()
    read_sessions_from_file()


def create_file() -> None:
    if not os.path.exists(SESSIONS_FILE_PATH):
        with open(SESSIONS_FILE_PATH, "a") as f:
            json.dump(sessions, f, indent=4)


def read_sessions_from_file() -> None:
    with open(SESSIONS_FILE_PATH, "r") as f:
        global sessions
        sessions = json.load(f)


def write_sessions_to_file() -> None:
    with open(SESSIONS_FILE_PATH, "w") as f:
        global sessions
        json.dump(sessions, f, indent=4)


def get_room(is_public: bool) -> (str, bool):
    if is_public:
        for room_id, room_data in sessions.get("rooms").items():
            if room_data.get("is_public"):
                players = room_data.get("players", {})
                if len(players) == 1:
                    set_last_change(room_id)
                    if "x" not in players:
                        sessions["rooms"][room_id]["players"]["x"] = None
                        set_last_change(room_id)
                        write_sessions_to_file()
                        return room_id, False
                    elif "o" not in players:
                        sessions["rooms"][room_id]["players"]["o"] = None
                        set_last_change(room_id)
                        write_sessions_to_file()
                        return room_id, False
                    else:
                        raise AssertionError("Unexpected condition: Both 'x' and 'o' are already occupied in the room.")

    room_id = generate_room_id()
    print(f"Created room: {room_id}")
    sessions["rooms"][room_id]["is_public"] = is_public
    sessions["rooms"][room_id]["players"]["x"] = None
    set_last_change(room_id)
    write_sessions_to_file()
    return room_id, True


def generate_room_id() -> str:
    """
    Generates a new unique room ID

    :return: The generated room ID
    :type: str
    """
    characters = string.ascii_letters + string.digits
    while True:
        rid = ''.join(random.choice(characters) for _ in range(6))
        with lock:
            if rid not in sessions:
                sessions["rooms"][rid] = copy.deepcopy(room_template)
                return rid


def delete_inactive_lobbies(after: int):
    """
    Deletes inactive lobbies (marked as inactive after the given amount of time)

    :param after: Amount of min after which a lobby with no activity gets deleted
    :type after: int
    """
    if not sessions:
        create_file()
        read_sessions_from_file()

    rooms_to_delete = []
    for room_id, room_data in sessions.get("rooms").items():
        last_active = datetime.datetime.fromtimestamp(room_data.get("last_change"))
        now = datetime.datetime.fromtimestamp(int(time.time()))
        if last_active + datetime.timedelta(minutes=after) <= now:
            rooms_to_delete.append(room_id)

    if rooms_to_delete:
        for room_id in rooms_to_delete:
            del sessions["rooms"][room_id]
            print(f"Deleted room: {room_id}")
        write_sessions_to_file()


def set_last_change(room_id: str) -> None:
    sessions["rooms"][room_id]["last_change"] = int(time.time())


def game_is_started(room_id: str) -> bool:
    return sessions["rooms"].get(room_id).get("started")


def start_game_setup(room_id: str) -> None:
    sessions["rooms"][room_id]["turn"] = ""
    sessions["rooms"][room_id]["fields"] = {}
    sessions["rooms"][room_id]["started"] = True


def check_room_full(room_id: str) -> bool:
    players = sessions["rooms"].get(room_id).get("players")
    return players.get("x") is not None and players.get("o") is not None


def join_client_in_room(room_id: str, client_id: str) -> (str, str):
    room = sessions["rooms"].get(room_id, False)
    if room:
        players = room.get("players", {})
        set_last_change(room_id)
        if client_id not in players.values():
            if players.get("x") is None:
                sessions["rooms"][room_id]["players"]["x"] = client_id
                return "success", "x"
            elif players.get("o") is None:
                sessions["rooms"][room_id]["players"]["o"] = client_id
                return "success", "o"
            elif players.get("x") is not None and players.get("o") is not None:
                return "full", ""
        else:
            return "rejoin", ""
    return "invalid", ""


def make_move(room_id: str, player_id: str, field: str) -> str:
    if 1 <= int(field) <= 9:
        occupied_fields = sessions["rooms"].get(room_id).get("fields").keys()
        if field not in occupied_fields:
            place_symbol(room_id, player_id, field)
            return "success"
        else:
            return "occupied"
    else:
        return "range"


def place_symbol(room_id: str, player_id: str, field: str) -> None:
    symbol = get_player_symbol(room_id, player_id)
    sessions["rooms"][room_id]["fields"][field] = symbol
    set_last_change(room_id)
    write_sessions_to_file()


def get_player_symbol(room_id: str, sid: str) -> str:
    room = sessions["rooms"].get(room_id)
    if room:
        for symbol, player_id in room.get("players").items():
            if player_id == sid:
                return symbol
        raise ValueError(f"Player ({sid}) not found in the given room!")
    raise ValueError(f"room_id ({room_id}) not found!")


def its_players_turn(room_id: str, player_id: str):
    player_symbol = get_player_symbol(room_id, player_id)
    turn = sessions["rooms"].get(room_id).get("turn")
    return player_symbol == turn or not turn


def check_win(room_id: str, player_id: str) -> (str, list):
    """
    Checks if the last move got a Win (3 in a row)

    :param room_id: ID of the room to check
    :type room_id: str

    :param player_id: ID of ther player which made the last move
    :type player_id: str

    :return: Whether the player won, it's a draw or till now there is no win.
    :rtype: str
    """
    winning_combos = [
        {1, 2, 3}, {4, 5, 6}, {7, 8, 9},  # rows
        {1, 4, 7}, {2, 5, 8}, {3, 6, 9},  # colums
        {1, 5, 9}, {3, 5, 7}              # diagonals
    ]

    player_symbol = get_player_symbol(room_id, player_id)
    fields = sessions["rooms"].get(room_id).get("fields").items()

    player_fields = [int(field) for field, symbol in fields if symbol == player_symbol]
    if len(fields) >= 5:
        for combo in winning_combos:
            if combo.issubset(set(player_fields)):
                return player_symbol, list(combo)
        # sadly the approach below won't work, as intended, when I calculated this it seemed to work, but now testing it
        # I realized, that it also matches combos like (2, 4, 6) or (1, 2, 9) wich obviously aren't wins. I still leave
        # it here as a "memorial", cause I was really proud of it, but then checking it in detail revealed some issues.
        #
        # field_values = [int(field) for field in player_fields]
        # for combo in combinations(field_values, 3):
        #     combo_sum = sum(combo)
        #     if combo_sum == 15 or combo_sum % 6 == 0 and 2 not in combo:
        #         return player_symbol
    if len(fields) == 9:
        return "draw", None
    return "next", None


def calculate_game_state(result_win: str, room_id: str, player_id: str = None) -> None:
    if result_win == "next":
        turn = sessions["rooms"].get(room_id).get("turn")
        if turn:
            new_turn_is_x = (turn == "o")
        else:
            if player_id:
                new_turn_is_x = get_player_symbol(room_id, player_id) == "o"
            else:
                raise ValueError("'player_id' is missing!")
        sessions["rooms"][room_id]["turn"] = "x" if new_turn_is_x else "o"
        return
    elif result_win == "redo":
        return
    elif result_win in ["x", "o"]:
        sessions["rooms"][room_id]["stats"]["wins"][result_win] += 1
    elif result_win == "draw":
        pass
    else:
        raise ValueError(f"'{result_win}' is no valid value for result_win")

    sessions["rooms"][room_id]["started"] = False
    sessions["rooms"][room_id]["stats"]["matches"] += 1
    set_last_change(room_id)


def get_stats(room_id: str) -> dict:
    return sessions["rooms"].get(room_id).get("stats")


def get_game_state(room_id: str) -> dict:
    room = sessions["rooms"].get(room_id)
    fields = room.get("fields")
    turn = room.get("turn")
    return {"fields": fields, "turn": turn}


def leave_session(room_id, client_id):
    player_symbol = get_player_symbol(room_id, client_id)
    del sessions["rooms"][room_id]["players"][player_symbol]
