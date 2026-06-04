let board = null;
let currentPlayer = null;
let winner = null;
let userColor = null;
let status = null;
let yellowAssigned = false;

const canvas = document.getElementById('boardCanvas');
const ctx = canvas.getContext('2d');
const turnStatusSpan = document.getElementById('turnStatus');

const COLS = 7;
const ROWS = 6;
const RADIUS = 35;
const COLUMN_WIDTH = canvas.width / COLS;
const ROW_HEIGHT = canvas.height / ROWS;

function drawBoard() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // Draw grid circles
    for (let row = 0; row < ROWS; row++) {
        for (let col = 0; col < COLS; col++) {
            const x = col * COLUMN_WIDTH + COLUMN_WIDTH/2;
            const y = row * ROW_HEIGHT + ROW_HEIGHT/2;
            ctx.beginPath();
            ctx.arc(x, y, RADIUS, 0, 2*Math.PI);
            ctx.fillStyle = '#2c3e50';
            ctx.fill();
            ctx.strokeStyle = '#1a252f';
            ctx.lineWidth = 2;
            ctx.stroke();
            
            const piece = board ? board[row][col] : null;
            if (piece) {
                ctx.beginPath();
                ctx.arc(x, y, RADIUS-4, 0, 2*Math.PI);
                ctx.fillStyle = piece === 'red' ? '#e74c3c' : '#f1c40f';
                ctx.fill();
                ctx.shadowBlur = 0;
            }
        }
    }
}

async function fetchGameState() {
    const res = await fetch(`/api/game/${window.GAME_ID}`);
    if (!res.ok) return;
    const data = await res.json();
    board = data.board;
    currentPlayer = data.current_player;
    winner = data.winner;
    userColor = data.user_color;
    status = data.status;
    yellowAssigned = data.yellow_assigned;
    
    drawBoard();
    updateStatusText();
}

function updateStatusText() {
    if (winner === 'draw') {
        turnStatusSpan.innerText = "Game ended in a draw! 🤝";
    } else if (winner) {
        const winnerName = winner === 'red' ? '🔴 Red' : '🟡 Yellow';
        turnStatusSpan.innerText = `${winnerName} wins! 🎉`;
    } else if (status !== 'active') {
        turnStatusSpan.innerText = "⏳ Waiting for opponent to join...";
    } else if (userColor) {
        if (currentPlayer === userColor) {
            turnStatusSpan.innerText = "👉 Your turn! Click a column.";
        } else {
            turnStatusSpan.innerText = "👀 Opponent's turn...";
        }
    } else {
        turnStatusSpan.innerText = "👁️ Watching mode (you didn't join)";
    }
}

async function makeMove(column) {
    if (winner || status !== 'active') {
        alert("Game not active.");
        return false;
    }
    if (currentPlayer !== userColor) {
        alert("Not your turn!");
        return false;
    }
    const res = await fetch('/api/move', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({game_id: window.GAME_ID, column: column})
    });
    if (res.ok) {
        await fetchGameState();  // refresh
        return true;
    } else {
        const err = await res.json();
        alert(err.error || "Invalid move");
        return false;
    }
}

canvas.addEventListener('click', (e) => {
    if (!userColor || winner || currentPlayer !== userColor) return;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const mouseX = (e.clientX - rect.left) * scaleX;
    const col = Math.floor(mouseX / COLUMN_WIDTH);
    if (col >= 0 && col < COLS) makeMove(col);
});

// Poll every 1.5 seconds
fetchGameState();
setInterval(fetchGameState, 1500);

// Copy link button
document.getElementById('copyLinkBtn')?.addEventListener('click', () => {
    const url = window.location.href;
    navigator.clipboard.writeText(url);
    alert('Link copied! Send it to your friend.');
});
