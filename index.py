import random
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

# --- Inicialização da Aplicação ---
# Instale o eventlet para melhor performance: pip install eventlet
app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma_chave_muito_secreta_e_segura!'
socketio = SocketIO(app, async_mode='eventlet') 

# --- Armazenamento de Dados em Memória ---
users = {'player': None, 'controller': None}
current_match = {}
crash_game = {
    "state": "idle",  # idle, running, crashed
    "multiplier": 1.00,
    "player_sid": None,
    "player_cashed_out": False
}

# --- Dados para Apostas Esportivas ---
TEAMS = {
    "europe": [
        {"name": "Real Madrid", "logo": "https://i.imgur.com/gJ5Jv5t.png", "players": ["Bellingham", "Vini Jr.", "Rodrygo", "Kroos", "Rüdiger"]},
        {"name": "Manchester City", "logo": "https://i.imgur.com/nJ3zWUN.png", "players": ["Haaland", "De Bruyne", "Foden", "Rodri", "Dias"]},
        {"name": "Liverpool FC", "logo": "https://i.imgur.com/mIBcnFf.png", "players": ["Salah", "Van Dijk", "Alisson", "Núñez", "Szoboszlai"]},
        {"name": "Bayern Munich", "logo": "https://i.imgur.com/m0j0g3j.png", "players": ["Kane", "Musiala", "Kimmich", "Davies", "Neuer"]},
    ],
    "brazil": [
        {"name": "Flamengo", "logo": "https://i.imgur.com/1u3vFGR.png", "players": ["G. Barbosa", "De Arrascaeta", "Pedro", "Gerson", "Ayrton Lucas"]},
        {"name": "Palmeiras", "logo": "https://i.imgur.com/s65c9iB.png", "players": ["Endrick", "Raphael Veiga", "Dudu", "Gomez", "Weverton"]},
        {"name": "Fluminense", "logo": "https://i.imgur.com/UaR2w1G.png", "players": ["Germán Cano", "Ganso", "André", "Marcelo", "J. Arias"]},
        {"name": "Corinthians", "logo": "https://i.imgur.com/pEo2x05.png", "players": ["Yuri Alberto", "R. Augusto", "Fagner", "Cássio", "Fausto Vera"]},
    ]
}

# --- Tarefa de Fundo do Jogo Crash ---
def run_crash_game():
    """Uma tarefa de fundo que executa o multiplicador do jogo crash."""
    global crash_game
    crash_game["state"] = "running"
    if users['controller']:
        socketio.emit('decision_request', {
            'type': 'crash_start',
            'msg': 'O jogo Crash começou! Prepare-se para quebrar.'
        }, room=users['controller'])

    while crash_game["state"] == "running":
        # *** A MUDANÇA ESTÁ AQUI: O multiplicador agora cresce mais lentamente ***
        crash_game["multiplier"] *= 1.005
        
        socketio.emit('crash_update', {'multiplier': f'{crash_game["multiplier"]:.2f}x'})
        socketio.sleep(0.1) # Controla a velocidade do jogo (ticks por segundo)

    # Este código executa DEPOIS que o loop é quebrado pelo controlador
    socketio.emit('crash_event', {
        'multiplier': f'{crash_game["multiplier"]:.2f}x',
        'cashed_out': crash_game['player_cashed_out']
    }, room=crash_game['player_sid'])
    
    if users['controller']:
        socketio.emit('game_ended', {'type': 'crash'}, room=users['controller'])
    
    socketio.sleep(5) # Pausa antes de resetar
    crash_game = { "state": "idle", "multiplier": 1.00, "player_sid": None, "player_cashed_out": False }
    socketio.emit('crash_ready') # Notifica os clientes que podem jogar de novo


# --- Rotas HTTP do Flask ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sports')
def sports_bet():
    global current_match
    current_match = {"europe": random.choice(TEAMS["europe"]), "brazil": random.choice(TEAMS["brazil"])}
    return render_template('sports_bet.html', matchup=current_match)

@app.route('/crash')
def crash_game_route():
    return render_template('crash.html')

@app.route('/controller')
def controller():
    return render_template('controller.html')


# --- Handlers de Eventos Socket.IO ---
@socketio.on('connect')
def handle_connect():
    print(f'Cliente conectado: {request.sid}')

@socketio.on('disconnect')
def handle_disconnect():
    print(f'Cliente desconectado: {request.sid}')
    if request.sid == users.get('player'): users['player'] = None
    if request.sid == users.get('controller'): users['controller'] = None
    if request.sid == crash_game.get("player_sid") and crash_game['state'] == 'running':
        crash_game["state"] = "crashed"

@socketio.on('register_player')
def handle_register_player():
    users['player'] = request.sid
    print(f'Jogador registrado: {users["player"]}')

@socketio.on('register_controller')
def handle_register_controller():
    users['controller'] = request.sid
    print(f'Controlador registrado: {users["controller"]}')

@socketio.on('spin')
def handle_spin():
    if users['controller']:
        emit('decision_request', {'type': 'slot'}, room=users['controller'])

@socketio.on('decision')
def handle_decision(data):
    if users['player']:
        emit('spin_result', {'outcome': data['outcome']}, room=users['player'])

@socketio.on('place_bet')
def handle_place_bet(data):
    if users['controller']:
        emit('decision_request', {
            'type': 'sports',
            'msg': f"Jogador apostou em {data['team_name']}",
            'match': current_match
        }, room=users['controller'])

@socketio.on('sports_decision')
def handle_sports_decision(data):
    winner = data['winner']
    score1, score2 = random.randint(0, 4), random.randint(0, 4)
    if score1 == score2: score1 += 1
    final_score = f"{max(score1, score2)} - {min(score1, score2)}" if winner == current_match["europe"]["name"] else f"{min(score1, score2)} - {max(score1, score2)}"
    if users['player']:
        emit('bet_result', {'winner': winner, 'score': final_score}, room=users['player'])

@socketio.on('start_crash')
def handle_start_crash():
    global crash_game
    if crash_game["state"] == "idle":
        crash_game["player_sid"] = request.sid
        socketio.start_background_task(target=run_crash_game)

@socketio.on('cashout')
def handle_cashout():
    global crash_game
    if crash_game["state"] == "running" and request.sid == crash_game["player_sid"] and not crash_game["player_cashed_out"]:
        crash_game["player_cashed_out"] = True
        emit('cashout_success', {'multiplier': f'{crash_game["multiplier"]:.2f}x'})

@socketio.on('crash_decision')
def handle_crash_decision():
    global crash_game
    if crash_game["state"] == "running":
        crash_game["state"] = "crashed"

if __name__ == '__main__':
    print("Iniciando Servidor de Jogos Controlado por Humanos...")
    print("URLs do Jogador: http://127.0.0.1:5000/ (Tigrinho), http://127.0.0.1:5000/sports, http://127.0.0.1:5000/crash")
    print("URL do Controlador: http://127.0.0.1:5000/controller")
    socketio.run(app, host='0.0.0.0', port=5000)