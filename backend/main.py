import json
import logging
import os
import sys
import threading
import time
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room

import game_manager as gm


IP = "0.0.0.0"  # "localhost"
PORT = 1338
DEBUG_MODE = True
SESSION_EXPIRES_AFTER = 120


EXECUTE_PATH = os.getcwd()
PATH = os.path.dirname(__file__)
PARENT_PATH = os.path.dirname(PATH)
DATE = time.strftime("%d-%m-%Y")
LOG_PATH = f"{PATH}/logs"


if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

logging.basicConfig(
    level=logging.DEBUG,
    format=f"%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(filename=f"{LOG_PATH}/log{DATE}.log", mode="a"),
        logging.StreamHandler(sys.stdout)
    ]
)

log = logging.getLogger(__name__)


app = Flask(__name__, static_url_path="/static", static_folder=f"{PARENT_PATH}/frontend/static")
socketio = SocketIO(app, cors_allowed_origins="*")
lock = threading.Lock()

client_rooms = {}


@app.route("/")
def index():
    """
    Main Page
    :return: Main Page
    """
    with open(f"{PARENT_PATH}/frontend/index.html", "r") as f:
        return f.read(), 200


@app.route("/ttt", methods=["GET"])
def ttt():
    """
    Page of the TicTacToe Game
    :return: TicTacToe Game Page
    """
    with open(f"{PARENT_PATH}/frontend/ttt.html", "r") as f:
        return f.read(), 200


@app.route("/ttt/api/join", methods=["POST"])
def generate_room():
    """
    Create a new roomId.

    :param isPulbic: Whether its a public lobby anyone can join, or a privat lobby only players with the room_id can join
    :type isPublic: bool

    :param roomId: (optional) The room ID of the room you want to join (leave empty to get a new room)
    :type roomId: str

    :return: session_id
    """
    data = request.json
    is_public = data.get("isPublic")
    room_id, new_created = gm.get_room(is_public)
    print("selected", room_id, new_created)
    gm.write_sessions_to_file()

    return jsonify({"result": "success", "roomId": room_id, "isPulbic": is_public}), 201 if new_created else 200


@app.route("/ttt/api/watch", methods=["POST"])
def watch():
    """
    WIP
    :return:
    """
    def generate_temp_watch_id():
        return "WIP"
    return generate_temp_watch_id()


@socketio.on("connect")
def on_connect():
    client_id = request.sid
    print(f"Client connected: {client_id}")
    pass


@socketio.on("join_game")
def on_join_game(data):
    data = json.loads(data)
    room_id = data.get("roomId")
    client_id = request.sid
    if room_id:
        result, symbol = gm.join_client_in_room(room_id, client_id)
        if result in "success":
            join_room(room_id)
            client_rooms[client_id] = room_id
            socketio.emit("success", {"code": 2001, "message": f"Joined room '{room_id}' successfully"}, room=client_id)
            send_player_type(symbol, client_id)

            if gm.check_room_full(room_id):
                send_start_game(room_id)
        elif result == "rejoin":
            socketio.emit("success", {"code": 2002, "message": f"rejoin"}, room=client_id)
            return
        elif result == "full":
            socketio.emit("error", {"code": 1001, "message": "room is already full"}, room=client_id)
        elif result == "invalid":
            socketio.emit("error", {"code": 1001, "message": "room_id is invalid: room not found"}, room=client_id)
        else:
            raise AssertionError(f"Recieved invalid result ({result}) from join_client_in_room()")
    else:
        socketio.emit("error", {"code": 1001, "message": "roomId is missing"}, room=client_id)


@socketio.on("make_move")
def on_make_move(data):
    data = json.loads(data)
    client_id = request.sid
    room_id = data.get("roomId")
    if room_id:
        client_room = client_rooms.get(client_id)
        if client_room == room_id:
            if gm.game_is_started(room_id):
                if gm.its_players_turn(room_id, client_id):
                    field = data.get("field")
                    if field:
                        result_move = gm.make_move(room_id, client_id, field)
                        if result_move == "success":
                            result_win, win_fields = gm.check_win(room_id, client_id)
                            socketio.emit("success", {"code": 2001, "message": "Field placed"}, room=client_id)
                            gm.calculate_game_state(result_win, room_id, client_id)
                            send_game_state(room_id, result_win, win_fields)

                        elif result_move == "occupied":
                            socketio.emit("error", {"code": 1001, "message": "Invalid field: field is already occupied"},
                                          room=client_id)
                            gm.calculate_game_state("redo", room_id)
                            send_game_state(room_id, "redo")
                        elif result_move == "range":
                            socketio.emit("error", {"code": 1001, "message": "Invalid field: field is out of range"},
                                          room=client_id)
                            gm.calculate_game_state("redo", room_id)
                            send_game_state(room_id, "redo")
                        else:
                            raise AssertionError("got unknown result from make_move")
                    else:
                        socketio.emit("error", {"code": 1001, "message": "Missing field on which was placed"}, room=client_id)
                else:
                    socketio.emit("error", {"code": 1001, "message": "It's not your turn!"}, room=client_id)
            else:
                socketio.emit("error", {"code": 1002, "message": "Game has not started yet"}, room=client_id)
        else:
            socketio.emit("error", {"code": 1001, "message": "Invalid roomId, the client is not in this room"},
                          room=client_id)
    else:
        socketio.emit("error", {"code": 1001, "message": "Missing roomId"}, room=client_id)


@socketio.on("disconnect")
def on_disconnect():
    client_id = request.sid
    print(f"Client disconnected: {client_id}")
    room_id = client_rooms.get(client_id)
    if room_id:
        leave_room(room_id)
        del client_rooms[client_id]
        gm.leave_session(room_id, client_id)


def send_start_game(room_id: str) -> None:
    log.debug("Send: start game")
    gm.start_game_setup(room_id)
    socketio.emit("start_game", {"fields": {}}, room=room_id)


def send_game_state(room_id: str, result_win: str = None, win_fields: list = None) -> None:
    log.debug("Send: game state")
    game_state = gm.get_game_state(room_id)
    socketio.emit("game_state", game_state, room=room_id)
    log.debug(f"game_state: {result_win = }")
    if result_win in ["x", "o", "draw"]:
        send_end_game(result_win, room_id, win_fields)


def send_end_game(result_win: str, room_id: str, win_fields: list) -> None:
    log.debug("Send: end game")
    winner = result_win if not result_win == "draw" else ""
    socketio.emit("end_game", {"winner": winner, "win_fields": win_fields}, room=room_id)
    send_stats(room_id)

    def restart_after_delay():
        time.sleep(3)
        send_start_game(room_id)
    threading.Thread(target=restart_after_delay).start()


def send_stats(room_id: str) -> None:
    log.debug("Send: stats")
    stats = gm.get_stats(room_id)
    socketio.emit("stats", stats, room=room_id)


def send_player_type(symbol: str, client_id: str) -> None:
    socketio.emit("player_type", {"symbol": symbol}, room=client_id)


def task_delete_inactive_lobbies():
    while True:
        gm.delete_inactive_lobbies(20)
        time.sleep(SESSION_EXPIRES_AFTER)


if __name__ == '__main__':
    gm.init()
    threading.Thread(target=task_delete_inactive_lobbies).start()
    socketio.run(app, host=IP, port=PORT, debug=DEBUG_MODE, allow_unsafe_werkzeug=True)
