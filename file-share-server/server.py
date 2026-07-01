import os, json, uuid, hashlib, shutil
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory, session, redirect, url_for

app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = 'fileshare-secret-key-change-in-production'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
DATA_DIR = os.path.join(BASE_DIR, 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
FILES_META = os.path.join(DATA_DIR, 'files.json')

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def load_json(path):
    if not os.path.exists(path): return []
    try:
        with open(path, 'r') as f: return json.load(f)
    except: return []

def save_json(path, data):
    with open(path, 'w') as f: json.dump(data, f, indent=2)

def get_users():
    return load_json(USERS_FILE)

def save_users(users):
    save_json(USERS_FILE, users)

def get_files_meta():
    return load_json(FILES_META)

def save_files_meta(files):
    save_json(FILES_META, files)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    display_name = data.get('displayName', '').strip()
    password = data.get('password', '')

    if not username or not display_name or not password:
        return jsonify({'error': 'All fields required'}), 400
    if len(username) < 3: return jsonify({'error': 'Username must be at least 3 characters'}), 400
    if len(password) < 4: return jsonify({'error': 'Password must be at least 4 characters'}), 400

    users = get_users()
    if any(u['username'] == username for u in users):
        return jsonify({'error': 'Username already taken'}), 409

    users.append({
        'username': username,
        'displayName': display_name,
        'password': hash_password(password)
    })
    save_users(users)
    return jsonify({'message': 'Account created'}), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    users = get_users()
    user = next((u for u in users if u['username'] == username and u['password'] == hash_password(password)), None)
    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401

    session['user'] = username
    session['displayName'] = user['displayName']
    session.permanent = True
    return jsonify({'username': username, 'displayName': user['displayName']})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'})

@app.route('/api/me')
def me():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify({'username': session['user'], 'displayName': session['displayName']})

@app.route('/api/files', methods=['GET'])
def list_files():
    tag = request.args.get('tag', '')
    files = get_files_meta()
    files.sort(key=lambda f: f['uploadedAt'], reverse=True)
    if tag:
        files = [f for f in files if tag.lower() in f['name'].lower() or tag.lower() in f['uploadedByDisplay'].lower()]
    return jsonify(files)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    stored_name = file_id + ext
    file_path = os.path.join(UPLOADS_DIR, stored_name)
    file.save(file_path)

    size = os.path.getsize(file_path)
    meta = {
        'id': file_id,
        'name': file.filename,
        'type': file.content_type or 'application/octet-stream',
        'size': size,
        'storedName': stored_name,
        'uploadedBy': session['user'],
        'uploadedByDisplay': session.get('displayName', session['user']),
        'uploadedAt': datetime.utcnow().isoformat() + 'Z'
    }
    files = get_files_meta()
    files.append(meta)
    save_files_meta(files)
    return jsonify(meta), 201

@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(UPLOADS_DIR, filename)

@app.route('/api/files/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    if 'user' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    files = get_files_meta()
    file = next((f for f in files if f['id'] == file_id), None)
    if not file:
        return jsonify({'error': 'File not found'}), 404
    if file['uploadedBy'] != session['user']:
        return jsonify({'error': 'You can only delete your own files'}), 403

    file_path = os.path.join(UPLOADS_DIR, file['storedName'])
    if os.path.exists(file_path):
        os.remove(file_path)
    files = [f for f in files if f['id'] != file_id]
    save_files_meta(files)
    return jsonify({'message': 'Deleted'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
