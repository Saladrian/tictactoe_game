var ready = (callback) => {
    if (document.readyState != "loading") callback();
    else document.addEventListener("DOMContentLoaded", callback);
}

ready(() => {
    console.log('page loaded');
    attachEventlisteners();
    lockButtons(true);
})

const serverUrl = `${window.location.origin}`; // /ttt/api
const socket = io(serverUrl, {autoConnect: false});

const line_colors = {"x": "#265aa9", "o": "#de1e2c"}
const urlParams = new URLSearchParams(window.location.search);
var connected;
var room_id = urlParams.get("room");
var fields = {};
var my_player;
var my_turn;
var winner;


connection_button = document.getElementById("connect");


function connection(event) {
    if (!event.target.className.includes("connected")) {
        console.log("Connecting...");
        if (!room_id) {
            const fetchOptions = {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({isPublic: true})
            };

            fetch("/ttt/api/join", fetchOptions)
                .then(response => response.json())
                .then(data => {
                    console.log("Success:", data);
                    room_id = data["roomId"];
                    socket.connect()
                    connected = true;
                    console.log("Connected");
                })
                .catch(error => {
                    console.error("Error in the request:", error);
                });
        } else {
            socket.connect()
            connected = true;
            console.log("Connected");
        }
    } else {
        console.log("Disconnecting...");
        socket.disconnect();
        connected = false;
        console.log("Disconnected!")
        room_id = "";
    }
}


function overlay(id, state) {
    const element = document.getElementById(id);
    if (state) {
        element.classList.add("show");
    } else {
        element.classList.remove("show");
    }
}


function lockButtons(state) {
    buttons = document.querySelectorAll('.ttt');
    buttons.forEach(button => {
        button.disabled = state;
    });
}


var buttons = [];

function attachEventlisteners() {
    buttons = document.querySelectorAll('.ttt');
    buttons.forEach(button => {
        button.addEventListener('click', tttEventFunction);
    });
    document.getElementById("connect").addEventListener("click", connection);

    const overlays = ["about", "howto"];
    overlays.forEach(overlayId => {
        document.getElementById(`${overlayId}`).addEventListener("click", () => {overlay(`overlay-${overlayId}`, true)});
        document.getElementById(`overlay-${overlayId}`).addEventListener("click", () => {overlay(`overlay-${overlayId}`, false)});
        document.getElementById(`content-${overlayId}`).addEventListener("click", function(event) {
            event.stopPropagation(); // Verhindert, dass das Klick-Ereignis auf das Overlay weitergeleitet wird
        });
    })
}


function drawLine(button1_id, button2_id, player_symbol) {
    const button1 = document.getElementById(button1_id);
    const button2 = document.getElementById(button2_id);

    const rect1 = button1.getBoundingClientRect();
    const rect2 = button2.getBoundingClientRect();

    color = line_colors[player_symbol]

    const x1 = rect1.x + rect1.width / 2;
    const y1 = rect1.y + rect1.height / 2;
    const x2 = rect2.x + rect2.width / 2;
    const y2 = rect2.y + rect2.height / 2;

    const line = document.getElementById('win-line');
    const lineElement = document.createElementNS("http://www.w3.org/2000/svg", "line");
    lineElement.setAttribute("x1", x1);
    lineElement.setAttribute("y1", y1);
    lineElement.setAttribute("x2", x1);
    lineElement.setAttribute("y2", y1);
    lineElement.setAttribute("stroke", color);
    lineElement.setAttribute("stroke-width", "10");
    lineElement.setAttribute("stroke-linecap", "round");
    line.appendChild(lineElement);

    const duration = 500; // Animation duration in milliseconds
    const startTime = performance.now();

    function animate() {
        const currentTime = performance.now();
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1); // Ensure progress doesn't exceed 1

        const x = x1 + (x2 - x1) * progress;
        const y = y1 + (y2 - y1) * progress;

        lineElement.setAttribute("x2", x);
        lineElement.setAttribute("y2", y);

        if (progress < 1) {
            requestAnimationFrame(animate); // Continue the animation
        }
    }

    requestAnimationFrame(animate); // Start the animation
};

function removeLine() {
    const line = document.getElementById("win-line");
    if (line) {
        line.innerHTML = "";
    }
};


function tttEventFunction(event) {
    if (my_turn) {
        if (event.target.className.includes('ttt') && !event.target.className.includes('symbol_x') && !event.target.className.includes('symbol_o')) {
            console.log("Clicked:", event.target.id);
            socket.emit("make_move", JSON.stringify({roomId: room_id, field: event.target.id}))
        }
    }
};

function update_fields() {
    buttons = document.querySelectorAll('.ttt');
    buttons.forEach(button => {
        if (fields[button.id]) {
            button.classList.add(fields[button.id]);
        }
        else {
            button.classList.remove("x");
            button.classList.remove("o");
        }
    })
};


socket.on("start_game", (data) => {
    removeLine();
    console.log("Game started");
    fields = data.fields;
    lockButtons(false);
    my_turn = true;
    winner = null;
    update_fields()
});

socket.on("game_state", (data) => {
    console.log("Game state:", data);
    fields = data.fields;
    turn = data.turn;
    my_turn = (my_player == turn)
    update_fields()
    lockButtons(!my_turn);
});

socket.on("end_game", (data) => {
    console.log("Game ended:", data)
    winner = data.winner;
    win_fields = data.win_fields;
    lockButtons(true);
    my_turn = null;
    if (winner) {
        win_fields.sort()
        console.log(win_fields)
        drawLine(win_fields[0], win_fields[2], winner)
        if (winner == my_player) {
            console.log("You won!");
        } else {
            console.log("You lose!");
        }
    } else {
        console.log("It's a draw!");
    }
});


socket.on("stats", (data) => {
    wins_x = data.wins.x
    wins_o = data.wins.o
    matches = data.matches
    played_since = data.playedSince

    let status;
    if (connected) {
        status = `Connected!<br>(Room: ${room_id})`
    } else {
        status = "Disconnected!"
    }

    document.getElementById("info1").innerHTML = `<b>Wins</b><br>X ${wins_x} | ${wins_o} O`;
    document.getElementById("info2").innerHTML = `<b>Matches played</b><br>${matches}`;
    document.getElementById("info3").innerHTML = `<b>Status</b><br>${status}`;
});

socket.on("connect", () => {
    socket.emit("join_game", JSON.stringify({roomId: room_id}));

    connection_button.classList.add("connected");
    connection_button.textContent = "Disconnect";
    document.getElementById("nav-bar").classList.add("connected");
});


socket.on("disconnect", () => {
    connection_button.classList.remove("connected");
    connection_button.textContent = "Connect";
    document.getElementById("nav-bar").classList.remove("connected");
});

socket.on("success", (data) => {
    console.log("WS Success: ", data)
});

socket.on("error", (data) => {
    console.log("WS Error: ", data)
});

socket.on("player_type", (data) => {
    my_player = data.symbol
});
