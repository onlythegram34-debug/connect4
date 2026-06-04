import os
import json
import secrets
from flask import Flask, render_template, request, jsonify, session
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Neon database connection from environment variable
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    """Create games table if it doesn't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            board JSON NOT NULL,
            current_player TEXT NOT NULL,
            winner TEXT,
            red_assigned BOOLEAN DEFAULT TRUE,
            yellow_assigned BOOLEAN DEFAULT FALSE,
            status TEXT DEFAULT 'waiting',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

# Helper: Check win/draw
def check_win(board, row, col, piece):
    directions = [(1,0), (0,1), (1,1), (1,-1)]
    for dr, dc in directions:
        count = 1
        for step in range(1,4):
            r, c = row + step*dr, col + step*dc
            if 0 <= r < 6 and 0 <= c < 7 and board[r][c] == piece:
                count += 1
            else:
                break
        for step in range(1,4):
            r, c = row - step*dr, col - step*dc
            if 0 <= r < 6 and 0 <= c < 7 and board[r][c] == piece:
                count += 1
            else:
                break
        if count >= 4:
            return True
    return False

def is_draw(board):
    return all(board[0][c] is not None for c in range(7))

def drop_piece(board, column, piece):
    for row in range(5, -1, -1):
        if board[row][column] is None:
            board[row][column] = piece
            return row, column
    return None, None  # column full

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create', methods=['POST'])
def create_game():
    game_id = secrets.token_urlsafe(6)
    # Empty board: 6 rows, 7 cols, all None
    board = [[None for _ in range(7)] for _ in range(6)]
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO games (id, board, current_player, red_assigned, status) VALUES (%s, %s, %s, %s, %s)",
        (game_id, json.dumps(board), 'red', True, 'waiting')
    )
    conn.commit()
    cur.close()
    conn.close()
    session['game_id'] = game_id
    session['player_color'] = 'red'
    return jsonify({'game_id': game_id, 'color': 'red'})

@app.route('/join', methods=['POST'])
def join_game():
    data = request.get_json()
    game_id = data.get('game_id')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT yellow_assigned, status FROM games WHERE id = %s", (game_id,))
    game = cur.fetchone()
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    if game['yellow_assigned']:
        return jsonify({'error': 'Game already has two players'}), 400
    if game['status'] != 'waiting' and game['status'] != 'active':
        return jsonify({'error': 'Game is not joinable'}), 400

    # Assign yellow and activate game
    cur.execute(
        "UPDATE games SET yellow_assigned = TRUE, status = 'active' WHERE id = %s",
        (game_id,)
    )
    conn.commit()
    cur.close()
    conn.close()
    session['game_id'] = game_id
    session['player_color'] = 'yellow'
    return jsonify({'game_id': game_id, 'color': 'yellow'})

@app.route('/game/<game_id>')
def game_page(game_id):
    # Check if game exists
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM games WHERE id = %s", (game_id,))
    game = cur.fetchone()
    cur.close()
    conn.close()
    if not game:
        return "Game not found", 404
    return render_template('game.html', game_id=game_id)

@app.route('/api/game/<game_id>', methods=['GET'])
def get_game_state(game_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT board, current_player, winner, status, red_assigned, yellow_assigned FROM games WHERE id = %s", (game_id,))
    game = cur.fetchone()
    cur.close()
    conn.close()
    if not game:
        return jsonify({'error': 'Game not found'}), 404

    # Determine user's color from session
    user_color = None
    if session.get('game_id') == game_id:
        user_color = session.get('player_color')

    return jsonify({
        'board': game['board'],
        'current_player': game['current_player'],
        'winner': game['winner'],
        'status': game['status'],
        'user_color': user_color,
        'yellow_assigned': game['yellow_assigned']
    })

@app.route('/api/move', methods=['POST'])
def make_move():
    data = request.get_json()
    game_id = data.get('game_id')
    column = data.get('column')
    
    if session.get('game_id') != game_id:
        return jsonify({'error': 'You are not part of this game'}), 403
    user_color = session.get('player_color')
    if not user_color:
        return jsonify({'error': 'No player color assigned'}), 403

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT board, current_player, winner, status FROM games WHERE id = %s", (game_id,))
    game = cur.fetchone()
    if not game:
        return jsonify({'error': 'Game not found'}), 404
    if game['winner']:
        return jsonify({'error': 'Game already finished'}), 400
    if game['status'] != 'active':
        return jsonify({'error': 'Waiting for second player to join'}), 400
    if game['current_player'] != user_color:
        return jsonify({'error': 'Not your turn'}), 400

    board = game['board']
    # column is int 0-6
    row, col = drop_piece(board, column, user_color)
    if row is None:
        return jsonify({'error': 'Column is full'}), 400

    # Check win
    if check_win(board, row, col, user_color):
        winner = user_color
        status = 'finished'
        cur.execute("UPDATE games SET board = %s, winner = %s, status = %s WHERE id = %s",
                    (json.dumps(board), winner, status, game_id))
    elif is_draw(board):
        winner = 'draw'
        status = 'finished'
        cur.execute("UPDATE games SET board = %s, winner = %s, status = %s WHERE id = %s",
                    (json.dumps(board), winner, status, game_id))
    else:
        # switch turn
        next_player = 'yellow' if user_color == 'red' else 'red'
        cur.execute("UPDATE games SET board = %s, current_player = %s WHERE id = %s",
                    (json.dumps(board), next_player, game_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)
