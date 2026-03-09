# app/app.py
from flask import Flask, request, jsonify, render_template_string, make_response
import sqlite3
import jwt
import os
import subprocess
import pickle
import base64
from datetime import datetime, timedelta

app = Flask(__name__)

# 🔴 VULNÉRABILITÉ 1 : Clé secrète codée en dur (Secret Hardcoding)
# Au lieu d'utiliser une variable d'environnement
app.config['SECRET_KEY'] = 'ma_super_cle_secrete_123456789'  # À NE PAS FAIRE EN PROD!

# 🔴 VULNÉRABILITÉ 2 : Debug mode activé (à ne jamais faire en prod)
app.config['DEBUG'] = True

# Base de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'database', 'bank.db')
print(f"📁 Base de données sera créée dans : {DATABASE}")

def get_db():
    """Connexion à la base de données"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialisation de la base de données avec des données de test"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Création des tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'user'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_number TEXT UNIQUE NOT NULL,
            balance REAL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_account TEXT NOT NULL,
            to_account TEXT NOT NULL,
            amount REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Insertion des données de test (si table vide)
    cursor.execute("SELECT COUNT(*) as count FROM users")
    if cursor.fetchone()['count'] == 0:
        # Mots de passe en clair ! (À NE PAS FAIRE)
        cursor.execute("INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)",
                      ('admin', 'admin123', 'admin@bank.com', 'admin'))
        cursor.execute("INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)",
                      ('alice', 'password123', 'alice@bank.com', 'user'))
        cursor.execute("INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)",
                      ('bob', 'bobpass', 'bob@bank.com', 'user'))
        
        # Comptes bancaires
        cursor.execute("INSERT INTO accounts (user_id, account_number, balance) VALUES (?, ?, ?)",
                      (1, 'FR123456789', 10000))
        cursor.execute("INSERT INTO accounts (user_id, account_number, balance) VALUES (?, ?, ?)",
                      (2, 'FR987654321', 5000))
        cursor.execute("INSERT INTO accounts (user_id, account_number, balance) VALUES (?, ?, ?)",
                      (3, 'FR555555555', 2500))
    
    conn.commit()
    conn.close()

# Initialiser la DB au démarrage
init_db()

# ==================== ENDPOINTS VULNÉRABLES ====================

# 🔴 VULNÉRABILITÉ 3 : Injection SQL
@app.route('/api/user', methods=['GET'])
def get_user():
    """
    Recherche un utilisateur par son nom.
    VULNÉRABLE : Injection SQL possible via le paramètre 'username'
    """
    username = request.args.get('username', '')
    
    # ❌ MAUVAISE PRATIQUE : Concaténation directe dans la requête SQL
    query = f"SELECT id, username, email, role FROM users WHERE username = '{username}'"
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(query)
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return jsonify({
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'role': user['role']
            })
        else:
            return jsonify({'error': 'Utilisateur non trouvé'}), 404
    except Exception as e:
        # ❌ MAUVAISE PRATIQUE : Afficher l'erreur SQL à l'utilisateur
        return jsonify({'error': str(e)}), 500

# 🔴 VULNÉRABILITÉ 4 : Injection SQL dans le login
@app.route('/api/login', methods=['POST'])
def login():
    """
    Authentification utilisateur.
    VULNÉRABLE : Injection SQL + Mots de passe en clair
    """
    data = request.get_json()
    username = data.get('username', '')
    password = data.get('password', '')
    
    # ❌ MAUVAISE PRATIQUE : Requête SQL vulnérable
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(query)
    user = cursor.fetchone()
    conn.close()
    
    if user:
        # ❌ MAUVAISE PRATIQUE : JWT sans expiration, algorithme faible
        token = jwt.encode(
            {'user_id': user['id'], 'username': user['username']},
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )
        return jsonify({'token': token, 'message': 'Login réussi'})
    else:
        return jsonify({'error': 'Identifiants invalides'}), 401

# 🔴 VULNÉRABILITÉ 5 : Manque de vérification JWT
@app.route('/api/balance', methods=['GET'])
def get_balance():
    """
    Récupère le solde du compte.
    VULNÉRABLE : Le token JWT n'est pas vérifié correctement
    """
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    try:
        # ❌ MAUVAISE PRATIQUE : Pas de vérification de la signature
        # On décode sans vérifier !
        payload = jwt.decode(token, options={"verify_signature": False})
        
        # ❌ MAUVAISE PRATIQUE : Utilisation directe de l'user_id sans vérification
        user_id = payload.get('user_id')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT account_number, balance FROM accounts WHERE user_id = ?", (user_id,))
        accounts = cursor.fetchall()
        conn.close()
        
        return jsonify([{'account': a['account_number'], 'balance': a['balance']} for a in accounts])
    except Exception as e:
        return jsonify({'error': str(e)}), 401

# 🔴 VULNÉRABILITÉ 6 : Injection de commande (Command Injection)
@app.route('/api/ping', methods=['POST'])
def ping_server():
    """
    Ping une adresse IP.
    VULNÉRABLE : Injection de commande shell
    """
    data = request.get_json()
    ip = data.get('ip', '')
    
    # ❌ MAUVAISE PRATIQUE : Exécution directe de commande shell
    command = f"ping -c 3 {ip}"
    
    try:
        # shell=True est DANGEREUX !
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return jsonify({
            'command': command,
            'output': result.stdout,
            'error': result.stderr
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 🔴 VULNÉRABILITÉ 7 : Server-Side Template Injection (SSTI)
@app.route('/api/greet', methods=['GET'])
def greet():
    """
    Affiche un message de bienvenue personnalisé.
    VULNÉRABLE : SSTI (Server-Side Template Injection)
    """
    name = request.args.get('name', 'visiteur')
    
    # ❌ MAUVAISE PRATIQUE : Construction dynamique de template
    template = f"<h1>Bonjour {name}!</h1><p>Bienvenue sur SecDevOpsBank</p>"
    
    return render_template_string(template)

# 🔴 VULNÉRABILITÉ 8 : Désérialisation non sécurisée (Pickle)
@app.route('/api/load_session', methods=['POST'])
def load_session():
    """
    Charge une session utilisateur.
    VULNÉRABLE : Désérialisation pickle non sécurisée
    """
    data = request.get_data()
    
    try:
        # ❌ MAUVAISE PRATIQUE : pickle.loads sur des données non fiables
        session_data = pickle.loads(data)
        return jsonify({'message': 'Session chargée', 'data': str(session_data)})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# 🔴 VULNÉRABILITÉ 9 : Path Traversal
@app.route('/api/read_file', methods=['GET'])
def read_file():
    """
    Lit le contenu d'un fichier.
    VULNÉRABLE : Path traversal
    """
    filename = request.args.get('filename', '')
    
    # ❌ MAUVAISE PRATIQUE : Pas de validation du chemin
    try:
        with open(filename, 'r') as f:
            content = f.read()
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# 🔴 VULNÉRABILITÉ 10 : Information Disclosure
@app.route('/api/debug', methods=['GET'])
def debug_info():
    """
    Affiche des informations de debug.
    VULNÉRABLE : Exposition d'informations sensibles
    """
    import platform
    import os
    
    info = {
        'app': 'SecDevOpsBank',
        'version': '1.0.0',
        'debug': app.config['DEBUG'],
        'secret_key': app.config['SECRET_KEY'],  # ❌ EXPOSÉ !
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'environment': dict(os.environ),  # ❌ TOUTES LES VARIABLES D'ENV !
        'database': DATABASE
    }
    
    return jsonify(info)

# 🔴 VULNÉRABILITÉ 11 : Manque de rate limiting
@app.route('/api/transfer', methods=['POST'])
def transfer():
    """
    Effectue un transfert d'argent.
    VULNÉRABLE : Pas de rate limiting, pas de validation
    """
    data = request.get_json()
    from_account = data.get('from_account')
    to_account = data.get('to_account')
    amount = data.get('amount', 0)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Vérifier le solde
    cursor.execute("SELECT balance FROM accounts WHERE account_number = ?", (from_account,))
    account = cursor.fetchone()
    
    if account and account['balance'] >= amount:
        # Débiter
        cursor.execute("UPDATE accounts SET balance = balance - ? WHERE account_number = ?",
                      (amount, from_account))
        # Créditer
        cursor.execute("UPDATE accounts SET balance = balance + ? WHERE account_number = ?",
                      (amount, to_account))
        # Enregistrer la transaction
        cursor.execute("INSERT INTO transactions (from_account, to_account, amount) VALUES (?, ?, ?)",
                      (from_account, to_account, amount))
        conn.commit()
        conn.close()
        return jsonify({'message': 'Transfert réussi'})
    else:
        conn.close()
        return jsonify({'error': 'Solde insuffisant'}), 400

# 🔴 VULNÉRABILITÉ 12 : XSS (Cross-Site Scripting)
@app.route('/api/comment', methods=['POST'])
def add_comment():
    """
    Ajoute un commentaire.
    VULNÉRABLE : XSS (pas d'échappement)
    """
    data = request.get_json()
    comment = data.get('comment', '')
    
    # ❌ MAUVAISE PRATIQUE : Renvoyer le commentaire sans échappement
    html = f"""
    <html>
        <body>
            <h2>Votre commentaire :</h2>
            <div>{comment}</div>
        </body>
    </html>
    """
    
    return render_template_string(html)

# Page d'accueil simple
@app.route('/')
def home():
    return """
    <html>
        <head>
            <title>SecDevOpsBank</title>
            <style>
                body { font-family: Arial; margin: 40px; }
                .vuln { color: red; }
            </style>
        </head>
        <body>
            <h1>🏦 SecDevOpsBank</h1>
            <p>Bienvenue sur l'application bancaire vulnérable pédagogique.</p>
            <h2 class="vuln">⚠️ API Vulnérable - NE PAS UTILISER EN PRODUCTION !</h2>
            <h3>Endpoints disponibles :</h3>
            <ul>
                <li><b>GET /api/user?username=XXX</b> - Injection SQL</li>
                <li><b>POST /api/login</b> - Authentification faible</li>
                <li><b>GET /api/balance</b> - JWT non vérifié</li>
                <li><b>POST /api/ping</b> - Injection de commande</li>
                <li><b>GET /api/greet?name=XXX</b> - SSTI</li>
                <li><b>POST /api/load_session</b> - Pickle désérialisation</li>
                <li><b>GET /api/read_file?filename=XXX</b> - Path traversal</li>
                <li><b>GET /api/debug</b> - Information disclosure</li>
                <li><b>POST /api/transfer</b> - Transfert sans rate limiting</li>
                <li><b>POST /api/comment</b> - XSS</li>
            </ul>
            <p><i>Ce projet est conçu pour l'apprentissage de la sécurité.</i></p>
        </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)