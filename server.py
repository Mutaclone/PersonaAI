"""
server.py — Persona Community Server
Runs a Bottle + WebSocket server on a configurable port.
Handles: Discord OAuth2, real-time chat (WebSocket), forum posts,
         DMs, character card gallery and uploads.

All community data is stored as JSON in BASE_DIR/community/.
The server runs in a background thread alongside the eel UI server.
"""

import os
import sys
import json
import time
import uuid
import hmac
import hashlib
import threading
import urllib.request
import urllib.parse
import urllib.error
import base64
import hashlib
import mimetypes
from datetime import datetime
from pathlib import Path

# ── Detect base directory ─────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

COMMUNITY_DIR = os.path.join(BASE_DIR, 'community')

# ── Community data paths ──────────────────────────────────────
def _path(name):
    return os.path.join(COMMUNITY_DIR, name)

USERS_FILE    = _path('users.json')
ROOMS_FILE    = _path('rooms.json')
MESSAGES_FILE = _path('messages.json')
POSTS_FILE    = _path('posts.json')
DMS_FILE      = _path('dms.json')
SESSIONS_FILE = _path('sessions.json')

os.makedirs(COMMUNITY_DIR, exist_ok=True)

# ── Data helpers ──────────────────────────────────────────────
_lock = threading.Lock()

def _load(path, default):
    try:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f'[server] load {path}: {e}')
    return default

def _save(path, data):
    with _lock:
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'[server] save {path}: {e}')

def _now():
    return datetime.utcnow().isoformat() + 'Z'

def _uid():
    return str(uuid.uuid4())

# ── Bootstrap default room ────────────────────────────────────
def _ensure_defaults():
    rooms = _load(ROOMS_FILE, [])
    if not rooms:
        rooms = [{
            'id': 'general', 'name': 'general',
            'description': 'Welcome! Introduce yourself.',
            'created_by': 'system', 'created_at': _now(),
            'pinned': True,
        }]
        _save(ROOMS_FILE, rooms)

_ensure_defaults()

# ══════════════════════════════════════════════════════════════
#  SESSION MANAGEMENT
# ══════════════════════════════════════════════════════════════

_SECRET = base64.urlsafe_b64encode(os.urandom(32)).decode()

def _make_session(discord_user: dict) -> str:
    """Create a session token and persist the user."""
    token    = base64.urlsafe_b64encode(os.urandom(24)).decode()
    user_id  = discord_user['id']
    sessions = _load(SESSIONS_FILE, {})
    sessions[token] = {
        'user_id':    user_id,
        'created_at': _now(),
        'expires':    time.time() + 86400 * 30,  # 30 days
    }
    _save(SESSIONS_FILE, sessions)

    # Upsert user record
    users = _load(USERS_FILE, {})
    users[user_id] = {
        'id':         user_id,
        'username':   discord_user.get('username', 'Unknown'),
        'global_name':discord_user.get('global_name') or discord_user.get('username',''),
        'avatar':     discord_user.get('avatar'),
        'joined_at':  users.get(user_id, {}).get('joined_at', _now()),
        'last_seen':  _now(),
    }
    _save(USERS_FILE, users)
    return token

def _get_session(token: str) -> dict | None:
    if not token:
        return None
    sessions = _load(SESSIONS_FILE, {})
    sess = sessions.get(token)
    if not sess:
        return None
    if sess.get('expires', 0) < time.time():
        del sessions[token]
        _save(SESSIONS_FILE, sessions)
        return None
    users = _load(USERS_FILE, {})
    user  = users.get(sess['user_id'])
    if user:
        # touch last_seen
        user['last_seen'] = _now()
        users[sess['user_id']] = user
        _save(USERS_FILE, users)
    return user

def _delete_session(token: str):
    sessions = _load(SESSIONS_FILE, {})
    sessions.pop(token, None)
    _save(SESSIONS_FILE, sessions)

# ══════════════════════════════════════════════════════════════
#  WEBSOCKET BROADCAST
# ══════════════════════════════════════════════════════════════

_ws_clients: dict[str, object] = {}   # token → ws
_ws_lock = threading.Lock()

def _broadcast(data: dict, exclude_token: str = None):
    """Send a JSON payload to all connected WebSocket clients."""
    payload = json.dumps(data)
    dead    = []
    with _ws_lock:
        for tok, ws in list(_ws_clients.items()):
            if tok == exclude_token:
                continue
            try:
                ws.send(payload)
            except Exception:
                dead.append(tok)
    for tok in dead:
        with _ws_lock:
            _ws_clients.pop(tok, None)

def _send_to(token: str, data: dict):
    """Send a JSON payload to a specific client."""
    with _ws_lock:
        ws = _ws_clients.get(token)
    if ws:
        try:
            ws.send(json.dumps(data))
        except Exception:
            with _ws_lock:
                _ws_clients.pop(token, None)

def _online_users() -> list:
    sessions = _load(SESSIONS_FILE, {})
    users    = _load(USERS_FILE, {})
    with _ws_lock:
        connected_tokens = set(_ws_clients.keys())
    result = []
    for tok in connected_tokens:
        sess = sessions.get(tok)
        if sess:
            u = users.get(sess['user_id'])
            if u:
                result.append(_public_user(u))
    return result

def _public_user(u: dict) -> dict:
    avatar_hash = u.get('avatar')
    avatar_url  = (f"https://cdn.discordapp.com/avatars/{u['id']}/{avatar_hash}.png?size=64"
                   if avatar_hash else None)
    return {
        'id':          u['id'],
        'username':    u.get('username','?'),
        'global_name': u.get('global_name') or u.get('username','?'),
        'avatar_url':  avatar_url,
    }

# ══════════════════════════════════════════════════════════════
#  DISCORD OAUTH2 HELPERS
# ══════════════════════════════════════════════════════════════

DISCORD_AUTH_URL = 'https://discord.com/api/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_USER_URL  = 'https://discord.com/api/users/@me'

def _discord_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = urllib.parse.urlencode({
        'client_id':     client_id,
        'redirect_uri':  redirect_uri,
        'response_type': 'code',
        'scope':         'identify',
        'state':         state,
    })
    return f'{DISCORD_AUTH_URL}?{params}'

def _discord_exchange_code(code: str, client_id: str, client_secret: str,
                            redirect_uri: str) -> dict | None:
    data = urllib.parse.urlencode({
        'client_id':     client_id,
        'client_secret': client_secret,
        'grant_type':    'authorization_code',
        'code':          code,
        'redirect_uri':  redirect_uri,
    }).encode()
    req  = urllib.request.Request(DISCORD_TOKEN_URL, data=data,
                                   headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f'[discord_exchange] {e}')
        return None

def _discord_get_user(access_token: str) -> dict | None:
    req = urllib.request.Request(DISCORD_USER_URL,
                                  headers={'Authorization': f'Bearer {access_token}'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f'[discord_user] {e}')
        return None

# ══════════════════════════════════════════════════════════════
#  SERVER CONFIG  (live reference updated by app.py)
# ══════════════════════════════════════════════════════════════

_config: dict = {
    'port':           8765,
    'discord_client_id':     '',
    'discord_client_secret': '',
    'redirect_uri':   'http://localhost:8765/auth/callback',
    'chars_folder':   os.path.join(BASE_DIR, 'characters'),
    'uploads_folder': os.path.join(COMMUNITY_DIR, 'uploads'),
    'server_name':    'Persona Community',
    'allow_uploads':  True,
}

def configure(cfg: dict):
    _config.update(cfg)
    os.makedirs(_config['uploads_folder'], exist_ok=True)

# ══════════════════════════════════════════════════════════════
#  BOTTLE APPLICATION
# ══════════════════════════════════════════════════════════════

try:
    from bottle import (Bottle, request, response, static_file,
                        redirect, abort, HTTPResponse)
    from geventwebsocket import WebSocketError
    from geventwebsocket.handler import WebSocketHandler
    from gevent.pywsgi import WSGIServer
    import gevent
    _BOTTLE_OK = True
except ImportError as _e:
    print(f'[server] Missing dependency: {_e}. Community server disabled.')
    _BOTTLE_OK = False

if _BOTTLE_OK:
    app = Bottle()

    # ── CORS middleware ───────────────────────────────────────
    def _cors():
        response.headers['Access-Control-Allow-Origin']  = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'

    @app.hook('after_request')
    def enable_cors():
        _cors()

    def _json(data, status=200):
        response.content_type = 'application/json'
        response.status       = status
        return json.dumps(data, ensure_ascii=False)

    def _auth_user() -> dict | None:
        """Extract and validate the session from cookie or Authorization header."""
        token = request.get_cookie('persona_token') or ''
        if not token:
            auth = request.headers.get('Authorization', '')
            if auth.startswith('Bearer '):
                token = auth[7:]
        return _get_session(token)

    def _require_auth():
        user = _auth_user()
        if not user:
            abort(401, 'Not authenticated')
        return user

    # ── Health / info ─────────────────────────────────────────
    @app.route('/api/info')
    def api_info():
        user = _auth_user()
        return _json({
            'name':         _config['server_name'],
            'online':       len(_ws_clients),
            'version':      '1.0',
            'authenticated': user is not None,
            'user':         _public_user(user) if user else None,
            'allow_uploads': _config['allow_uploads'],
            'oauth_configured': bool(_config['discord_client_id']),
        })

    # ── Discord OAuth ─────────────────────────────────────────
    @app.route('/login')
    def login():
        if not _config['discord_client_id']:
            return _json({'error': 'Discord OAuth not configured on this server.'}, 503)
        state = base64.urlsafe_b64encode(os.urandom(16)).decode()
        response.set_cookie('oauth_state', state, httponly=True, max_age=600)
        url = _discord_auth_url(
            _config['discord_client_id'],
            _config['redirect_uri'],
            state,
        )
        redirect(url)

    @app.route('/auth/callback')
    def auth_callback():
        code  = request.query.get('code', '')
        state = request.query.get('state', '')
        saved = request.get_cookie('oauth_state', '')

        if not code:
            return _serve_client_with_error('OAuth cancelled or failed.')
        if state != saved:
            return _serve_client_with_error('OAuth state mismatch — please try again.')

        tokens = _discord_exchange_code(
            code,
            _config['discord_client_id'],
            _config['discord_client_secret'],
            _config['redirect_uri'],
        )
        if not tokens or 'access_token' not in tokens:
            return _serve_client_with_error('Failed to exchange OAuth code.')

        discord_user = _discord_get_user(tokens['access_token'])
        if not discord_user or 'id' not in discord_user:
            return _serve_client_with_error('Failed to fetch Discord user info.')

        session_token = _make_session(discord_user)
        response.set_cookie('persona_token', session_token,
                             httponly=True, max_age=86400 * 30)
        redirect('/')

    @app.route('/logout')
    def logout():
        token = request.get_cookie('persona_token', '')
        if token:
            _delete_session(token)
        response.delete_cookie('persona_token')
        redirect('/')

    # ── Online users ──────────────────────────────────────────
    @app.route('/api/users/online')
    def api_online_users():
        return _json(_online_users())

    @app.route('/api/users/<user_id>')
    def api_user(user_id):
        users = _load(USERS_FILE, {})
        u = users.get(user_id)
        if not u:
            abort(404, 'User not found')
        return _json(_public_user(u))

    # ── Rooms ─────────────────────────────────────────────────
    @app.route('/api/rooms')
    def api_rooms():
        return _json(_load(ROOMS_FILE, []))

    @app.route('/api/rooms', method='POST')
    def api_create_room():
        user = _require_auth()
        data = request.json or {}
        name = (data.get('name') or '').strip().lower().replace(' ', '-')
        if not name:
            abort(400, 'Room name required')
        rooms = _load(ROOMS_FILE, [])
        if any(r['name'] == name for r in rooms):
            abort(409, 'Room already exists')
        room = {
            'id':          _uid(), 'name': name,
            'description': data.get('description', ''),
            'created_by':  user['id'], 'created_at': _now(),
            'pinned':      False,
        }
        rooms.append(room)
        _save(ROOMS_FILE, rooms)
        _broadcast({'type': 'room_created', 'room': room})
        return _json(room, 201)

    # ── Messages ──────────────────────────────────────────────
    @app.route('/api/rooms/<room_id>/messages')
    def api_get_messages(room_id):
        limit  = int(request.query.get('limit', 50))
        before = request.query.get('before', '')
        since  = int(request.query.get('since', 0))
        msgs   = _load(MESSAGES_FILE, {}).get(room_id, [])
        if before:
            msgs = [m for m in msgs if m['id'] < before]
        if since:
            msgs = [m for m in msgs if m.get('ts', 0) > since]
        result = msgs[-min(limit, 100):]
        # Normalize author shape for all messages
        users = _load(USERS_FILE, {})
        for m in result:
            if 'author' not in m:
                u = users.get(m.get('author_id', ''))
                if u:
                    m['author'] = _public_user(u)
                else:
                    m['author'] = {'username': m.get('author_id', 'Unknown'),
                                   'global_name': m.get('author_id', 'Unknown')}
            # Ensure ts field exists
            if 'ts' not in m:
                m['ts'] = int(m.get('created_at', '0').replace('Z','').replace('T',' ')
                              .split('.')[0].replace('-','').replace(':','').replace(' ','') or 0)
        return _json(result)

    @app.route('/api/rooms/<room_id>/messages', method='POST')
    def api_post_message(room_id):
        data    = request.json or {}
        content = (data.get('content') or '').strip()
        if not content:
            abort(400, 'Content required')
        if len(content) > 2000:
            abort(400, 'Message too long (max 2000 chars)')

        # Accept either authenticated user (OAuth session) or
        # anonymous Persona client (author + optional avatar in body)
        user = _auth_user()
        if user:
            author_name = user.get('global_name') or user.get('username', 'Unknown')
            author_id   = user['id']
            avatar_url  = (f"https://cdn.discordapp.com/avatars/{user['id']}/{user['avatar']}.png?size=64"
                           if user.get('avatar') else None)
        else:
            # Anonymous Persona client — use display name from body
            author_name = (data.get('author') or 'Anonymous')[:64]
            author_id   = 'anon_' + hashlib.md5(author_name.encode()).hexdigest()[:8]
            avatar_url  = data.get('avatar') if data.get('avatar','').startswith('http') else None

        msg = {
            'id':         _uid(), 'room_id': room_id,
            'author_id':  author_id, 'content': content,
            'created_at': _now(), 'type': 'message',
            'edited':     False,
            'ts':         int(time.time()),
            'iso':        _now(),
        }
        all_msgs = _load(MESSAGES_FILE, {})
        all_msgs.setdefault(room_id, []).append(msg)
        if len(all_msgs[room_id]) > 1000:
            all_msgs[room_id] = all_msgs[room_id][-1000:]
        _save(MESSAGES_FILE, all_msgs)
        payload = {**msg, 'author': {
            'id':          author_id,
            'username':    author_name,
            'global_name': author_name,
            'avatar_url':  avatar_url,
        }}
        _broadcast({'type': 'message', 'data': payload})
        return _json({**payload, 'ok': True}, 201)

    # ── Forum posts ───────────────────────────────────────────
    @app.route('/api/rooms/<room_id>/posts')
    def api_get_posts(room_id):
        posts = _load(POSTS_FILE, {}).get(room_id, [])
        users = _load(USERS_FILE, {})
        for p in posts:
            u = users.get(p.get('author_id', ''))
            p['author'] = _public_user(u) if u else {'username': 'Unknown'}
            for r in p.get('replies', []):
                ru = users.get(r.get('author_id', ''))
                r['author'] = _public_user(ru) if ru else {'username': 'Unknown'}
        return _json(sorted(posts, key=lambda x: x['created_at'], reverse=True))

    @app.route('/api/rooms/<room_id>/posts', method='POST')
    def api_create_post(room_id):
        user    = _require_auth()
        data    = request.json or {}
        title   = (data.get('title') or '').strip()
        content = (data.get('content') or '').strip()
        if not title or not content:
            abort(400, 'Title and content required')
        post = {
            'id':         _uid(), 'room_id': room_id,
            'title':      title[:200], 'content': content[:10000],
            'author_id':  user['id'], 'created_at': _now(),
            'replies':    [], 'pinned': False, 'tag': data.get('tag', ''),
        }
        all_posts = _load(POSTS_FILE, {})
        all_posts.setdefault(room_id, []).append(post)
        _save(POSTS_FILE, all_posts)
        payload = {**post, 'author': _public_user(user)}
        _broadcast({'type': 'post_created', 'data': payload})
        return _json(payload, 201)

    @app.route('/api/posts/<post_id>/replies', method='POST')
    def api_reply_post(post_id):
        user    = _require_auth()
        data    = request.json or {}
        content = (data.get('content') or '').strip()
        if not content:
            abort(400, 'Content required')
        all_posts = _load(POSTS_FILE, {})
        for room_posts in all_posts.values():
            for p in room_posts:
                if p['id'] == post_id:
                    reply = {
                        'id':         _uid(),
                        'author_id':  user['id'],
                        'content':    content[:5000],
                        'created_at': _now(),
                    }
                    p.setdefault('replies', []).append(reply)
                    _save(POSTS_FILE, all_posts)
                    payload = {**reply, 'author': _public_user(user), 'post_id': post_id}
                    _broadcast({'type': 'reply_created', 'data': payload})
                    return _json(payload, 201)
        abort(404, 'Post not found')

    # ── Direct Messages ───────────────────────────────────────
    @app.route('/api/dms')
    def api_get_dms():
        user = _require_auth()
        dms  = _load(DMS_FILE, {})
        result = []
        for dm_id, dm in dms.items():
            if user['id'] in dm.get('participants', []):
                other_id = next((p for p in dm['participants'] if p != user['id']), None)
                users_db = _load(USERS_FILE, {})
                other    = users_db.get(other_id)
                result.append({
                    'id':           dm_id,
                    'other_user':   _public_user(other) if other else None,
                    'last_message': dm['messages'][-1] if dm.get('messages') else None,
                    'unread':       dm.get(f'unread_{user["id"]}', 0),
                })
        return _json(result)

    @app.route('/api/dms/<other_user_id>', method='GET')
    def api_get_dm(other_user_id):
        user = _require_auth()
        dms  = _load(DMS_FILE, {})
        dm_id = _dm_id(user['id'], other_user_id)
        dm    = dms.get(dm_id, {'messages': []})
        # Clear unread
        dm[f'unread_{user["id"]}'] = 0
        dms[dm_id] = dm
        _save(DMS_FILE, dms)
        users_db = _load(USERS_FILE, {})
        msgs = dm.get('messages', [])[-100:]
        for m in msgs:
            u = users_db.get(m.get('author_id'))
            m['author'] = _public_user(u) if u else {'username': 'Unknown'}
        return _json(msgs)

    @app.route('/api/dms/<other_user_id>', method='POST')
    def api_send_dm(other_user_id):
        user    = _require_auth()
        data    = request.json or {}
        content = (data.get('content') or '').strip()
        if not content:
            abort(400, 'Content required')
        dms   = _load(DMS_FILE, {})
        dm_id = _dm_id(user['id'], other_user_id)
        dm    = dms.get(dm_id, {
            'id': dm_id, 'participants': [user['id'], other_user_id], 'messages': []
        })
        msg = {
            'id':         _uid(), 'author_id': user['id'],
            'content':    content[:2000], 'created_at': _now(),
        }
        dm.setdefault('messages', []).append(msg)
        if len(dm['messages']) > 500:
            dm['messages'] = dm['messages'][-500:]
        dm[f'unread_{other_user_id}'] = dm.get(f'unread_{other_user_id}', 0) + 1
        dms[dm_id] = dm
        _save(DMS_FILE, dms)
        payload = {**msg, 'author': _public_user(user), 'dm_id': dm_id}
        # Notify recipient's WS session
        sessions = _load(SESSIONS_FILE, {})
        with _ws_lock:
            for tok, ws in list(_ws_clients.items()):
                sess = sessions.get(tok)
                if sess and sess['user_id'] == other_user_id:
                    try:
                        ws.send(json.dumps({'type': 'dm', 'data': payload}))
                    except Exception:
                        pass
        return _json(payload, 201)

    def _dm_id(a: str, b: str) -> str:
        """Deterministic DM conversation ID from two user IDs."""
        return '_'.join(sorted([a, b]))

    # ── Character Card Gallery ────────────────────────────────
    @app.route('/api/cards')
    def api_cards():
        cards = []
        chars_dir = _config['chars_folder']
        uploads   = _config['uploads_folder']

        for folder, source in [(chars_dir, 'host'), (uploads, 'community')]:
            if not os.path.isdir(folder):
                continue
            for fname in sorted(os.listdir(folder)):
                if not fname.lower().endswith(('.json', '.png')):
                    continue
                fpath = os.path.join(folder, fname)
                name  = os.path.splitext(fname)[0]

                # Extract NSFW badge from metadata
                is_nsfw = False
                if source == 'community':
                    meta_path = os.path.join(folder, "cards_meta.json")
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                                is_nsfw = meta.get(fname, {}).get('nsfw', False)
                        except Exception:
                            pass

                cards.append({
                    'filename':    fname,
                    'name':        name,
                    'source':      source,
                    'has_png':     fname.lower().endswith('.png'),
                    'url_download': f'/cards/{source}/{urllib.parse.quote(fname)}',
                    'url_thumb':    f'/cards/{source}/{urllib.parse.quote(fname)}' if fname.lower().endswith('.png') else None,
                    'size':        os.path.getsize(fpath),
                    'modified':    os.path.getmtime(fpath),
                    'nsfw':        is_nsfw,
                })
        return _json(cards)

    @app.route('/cards/<source>/<filename>')
    def serve_card(source, filename):
        if source == 'host':
            folder = _config['chars_folder']
        elif source == 'community':
            folder = _config['uploads_folder']
        else:
            abort(404)
        return static_file(filename, root=folder)

    @app.route('/api/cards/upload', method='POST')
    def api_upload_card():
        if not _config['allow_uploads']:
            abort(403, 'Uploads are disabled on this server.')
        user = _require_auth()
        upload = request.files.get('card')
        if not upload:
            abort(400, 'No file provided')
        fname = upload.filename
        if not fname.lower().endswith(('.png', '.json')):
            abort(400, 'Only .png and .json card files are accepted')
        # Sanitise filename
        fname  = ''.join(c for c in fname if c.isalnum() or c in '._- ')[:80]
        folder = _config['uploads_folder']
        os.makedirs(folder, exist_ok=True)
        save_path = os.path.join(folder, fname)
        upload.save(save_path, overwrite=True)

        is_nsfw = request.forms.get('nsfw') in ['1', 'true', 'True']
        meta_path = os.path.join(folder, "cards_meta.json")
        meta = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
            except Exception:
                pass
        meta[fname] = {'nsfw': is_nsfw, 'uploaded_by': user['id']}
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f)
        except Exception:
            pass

        _broadcast({
            'type': 'card_uploaded',
            'data': {
                'filename': fname, 'name': os.path.splitext(fname)[0],
                'uploaded_by': _public_user(user),
                'url_download': f'/cards/community/{urllib.parse.quote(fname)}',
                'nsfw': is_nsfw,
            }
        })
        return _json({'ok': True, 'filename': fname, 'uploaded_by': user['id']}, 201)

    # ── WebSocket ─────────────────────────────────────────────
    @app.route('/ws')
    def websocket():
        ws  = request.environ.get('wsgi.websocket')
        if not ws:
            abort(400, 'WebSocket only')

        token = request.query.get('token', '')
        user  = _get_session(token)

        # Register
        with _ws_lock:
            _ws_clients[token] = ws

        try:
            # Greet
            ws.send(json.dumps({
                'type': 'hello',
                'user': _public_user(user) if user else None,
                'online': _online_users(),
            }))
            # Announce join
            if user:
                _broadcast({
                    'type': 'user_joined',
                    'user': _public_user(user),
                    'online': _online_users(),
                }, exclude_token=token)

            while True:
                raw = ws.receive()
                if raw is None:
                    break
                try:
                    msg = json.loads(raw)
                    _handle_ws_message(token, user, msg, ws)
                except Exception as e:
                    print(f'[ws] handle error: {e}')

        except WebSocketError:
            pass
        finally:
            with _ws_lock:
                _ws_clients.pop(token, None)
            if user:
                _broadcast({
                    'type': 'user_left',
                    'user': _public_user(user),
                    'online': _online_users(),
                })

    def _handle_ws_message(token, user, msg, ws):
        """Handle an incoming WebSocket message from the client."""
        mtype = msg.get('type')

        if mtype == 'ping':
            ws.send(json.dumps({'type': 'pong'}))

        elif mtype == 'typing':
            if user:
                _broadcast({
                    'type': 'typing',
                    'room_id': msg.get('room_id'),
                    'user':    _public_user(user),
                }, exclude_token=token)

    # ── Static client app ─────────────────────────────────────
    @app.route('/')
    @app.route('/<path:path>')
    def client(path=''):
        # Return the embedded client HTML
        return HTTPResponse(
            body=_CLIENT_HTML,
            status=200,
            headers={'Content-Type': 'text/html; charset=utf-8'},
        )

# ══════════════════════════════════════════════════════════════
#  CLIENT HTML  (served to guests — standalone SPA)
# ══════════════════════════════════════════════════════════════

_CLIENT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Persona Community</title>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500&family=Crimson+Pro:ital,wght@0,400;0,600;1,400&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{
  --bg:#0f0d10;--surface:#161419;--elevated:#1d1a20;--elevated2:#242029;
  --border:#2c2830;--border-light:#3c3840;--accent:#c8894a;
  --accent-dim:rgba(200,137,74,.14);--text:#e4ddd3;--text-muted:#978e96;
  --text-dim:#635e68;--red:#c84a4a;--blue:#4a8bc8;
  --radius:10px;--radius-sm:6px;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);font-family:'Crimson Pro',serif;font-size:15px;}
button{cursor:pointer;border:none;background:none;color:inherit;font:inherit;}
input,textarea{font-family:inherit;font-size:inherit;color:inherit;background:var(--elevated);border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 11px;outline:none;transition:border-color .2s;}
input:focus,textarea:focus{border-color:var(--accent);}
::-webkit-scrollbar{width:4px;}::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--border-light);border-radius:4px;}
#app{display:flex;height:100vh;}
/* Sidebar */
#sidebar{width:240px;flex-shrink:0;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden;}
#sidebar-header{padding:14px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.logo{font-family:'Cinzel',serif;font-size:15px;font-weight:500;letter-spacing:.08em;color:var(--accent);}
#user-pill{display:flex;align-items:center;gap:7px;padding:8px 12px;margin:6px;background:var(--elevated);border-radius:var(--radius-sm);border:1px solid var(--border);}
.user-ava{width:28px;height:28px;border-radius:50%;background:var(--elevated2);object-fit:cover;display:flex;align-items:center;justify-content:center;font-family:'Cinzel',serif;font-size:10px;color:var(--accent);border:1px solid var(--border);flex-shrink:0;}
.user-ava img{width:100%;height:100%;border-radius:50%;object-fit:cover;}
.user-name{font-size:12.5px;font-weight:600;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.nav-section-label{font-family:'JetBrains Mono',monospace;font-size:9.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--text-dim);padding:10px 14px 4px;}
.nav-item{display:flex;align-items:center;gap:8px;padding:8px 12px;margin:1px 6px;border-radius:var(--radius-sm);cursor:pointer;font-size:13px;color:var(--text-muted);transition:all .12s;border:1px solid transparent;}
.nav-item:hover{background:var(--elevated);color:var(--text);}
.nav-item.active{background:var(--accent-dim);color:var(--accent);border-color:rgba(200,137,74,.22);}
.nav-item-icon{width:18px;text-align:center;flex-shrink:0;font-size:14px;}
.unread-badge{margin-left:auto;background:var(--red);color:#fff;font-size:9px;font-family:'JetBrains Mono',monospace;padding:1px 5px;border-radius:8px;font-weight:700;}
/* Online users */
#online-panel{border-top:1px solid var(--border);padding:8px;flex-shrink:0;max-height:160px;overflow-y:auto;}
.online-label{font-family:'JetBrains Mono',monospace;font-size:9.5px;text-transform:uppercase;letter-spacing:.1em;color:var(--text-dim);padding:4px 6px 6px;}
.online-user{display:flex;align-items:center;gap:7px;padding:4px 6px;border-radius:5px;cursor:pointer;}
.online-user:hover{background:var(--elevated);}
.online-dot{width:8px;height:8px;border-radius:50%;background:#57f287;flex-shrink:0;}
.online-username{font-size:12px;color:var(--text-muted);}
/* Main area */
#main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0;}
#main-header{padding:0 16px;height:52px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.main-title{font-family:'Cinzel',serif;font-size:14px;font-weight:500;letter-spacing:.05em;}
.main-sub{font-family:'JetBrains Mono',monospace;font-size:10.5px;color:var(--text-dim);}
/* Views */
.view{display:none;flex:1;flex-direction:column;overflow:hidden;min-height:0;}
.view.active{display:flex;}
/* Chat view */
#chat-messages{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;}
.msg{display:flex;gap:10px;animation:msgIn .15s ease;}
@keyframes msgIn{from{opacity:0;transform:translateY(4px);}to{opacity:1;transform:none;}}
.msg-ava{width:32px;height:32px;border-radius:50%;flex-shrink:0;overflow:hidden;background:var(--elevated2);display:flex;align-items:center;justify-content:center;font-family:'Cinzel',serif;font-size:11px;color:var(--accent);border:1px solid var(--border);}
.msg-ava img{width:100%;height:100%;object-fit:cover;}
.msg-body{flex:1;min-width:0;}
.msg-meta{display:flex;align-items:baseline;gap:8px;margin-bottom:2px;}
.msg-author{font-size:13px;font-weight:600;color:var(--accent);}
.msg-time{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-dim);}
.msg-content{font-size:14.5px;line-height:1.6;color:var(--text);word-break:break-word;}
.typing-indicator{font-size:12px;color:var(--text-dim);font-style:italic;padding:4px 16px;font-family:'JetBrains Mono',monospace;}
.system-msg{text-align:center;font-size:11.5px;color:var(--text-dim);font-family:'JetBrains Mono',monospace;padding:4px 0;font-style:italic;}
/* Input */
#chat-input-area{padding:10px 16px 12px;border-top:1px solid var(--border);background:var(--surface);flex-shrink:0;}
.chat-input-row{display:flex;gap:8px;}
#chat-input{flex:1;padding:9px 14px;border-radius:var(--radius);font-size:14.5px;min-height:40px;max-height:120px;resize:none;line-height:1.4;}
.send-btn{width:40px;height:40px;border-radius:var(--radius);background:var(--accent);color:#1a0800;font-size:16px;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .2s;}
.send-btn:hover:not(:disabled){filter:brightness(1.15);}
.send-btn:disabled{opacity:.4;cursor:not-allowed;}
/* Cards gallery */
#cards-grid{flex:1;overflow-y:auto;padding:16px;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;align-content:start;}
.card-item{background:var(--elevated);border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden;cursor:pointer;transition:all .15s;}
.card-item:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.4);}
.card-thumb{width:100%;aspect-ratio:2/3;object-fit:cover;background:var(--elevated2);display:block;}
.card-thumb-placeholder{width:100%;aspect-ratio:2/3;background:var(--elevated2);display:flex;align-items:center;justify-content:center;font-family:'Cinzel',serif;font-size:32px;color:var(--text-dim);}
.card-info{padding:7px 9px;}
.card-name{font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.card-meta{font-size:10px;color:var(--text-dim);font-family:'JetBrains Mono',monospace;margin-top:2px;}
.source-badge{display:inline-block;font-size:9px;font-family:'JetBrains Mono',monospace;padding:1px 5px;border-radius:3px;margin-top:3px;}
.source-host{background:rgba(200,137,74,.15);color:var(--accent);border:1px solid rgba(200,137,74,.3);}
.source-community{background:rgba(74,139,200,.15);color:var(--blue);border:1px solid rgba(74,139,200,.3);}
/* Card detail panel */
#card-detail{position:fixed;inset:0;background:rgba(0,0,0,.75);backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;z-index:50;padding:20px;}
#card-detail.hidden{display:none;}
.card-detail-box{background:var(--surface);border:1px solid var(--border-light);border-radius:var(--radius);width:100%;max-width:500px;max-height:90vh;overflow-y:auto;box-shadow:0 24px 64px rgba(0,0,0,.6);}
.card-detail-img{width:100%;max-height:320px;object-fit:cover;object-position:top;}
.card-detail-body{padding:18px 20px;}
.card-detail-name{font-family:'Cinzel',serif;font-size:20px;font-weight:500;letter-spacing:.05em;color:var(--accent);margin-bottom:8px;}
.card-detail-desc{font-size:14.5px;color:var(--text-muted);line-height:1.6;max-height:120px;overflow-y:auto;margin-bottom:12px;}
.card-detail-actions{display:flex;gap:8px;flex-wrap:wrap;}
.btn-accent{background:var(--accent);color:#1a0800;font-family:'Cinzel',serif;font-size:12px;font-weight:600;letter-spacing:.06em;padding:8px 18px;border-radius:var(--radius-sm);transition:all .18s;}
.btn-accent:hover{filter:brightness(1.12);}
.btn-ghost{border:1px solid var(--border-light);color:var(--text-muted);font-size:12.5px;padding:7px 14px;border-radius:var(--radius-sm);transition:all .12s;}
.btn-ghost:hover{border-color:var(--accent);color:var(--accent);}
/* Forum posts */
#posts-view{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;}
.post-item{background:var(--elevated);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;cursor:pointer;transition:all .12s;}
.post-item:hover{border-color:var(--border-light);}
.post-title{font-family:'Cinzel',serif;font-size:14.5px;font-weight:500;letter-spacing:.03em;margin-bottom:5px;}
.post-excerpt{font-size:13px;color:var(--text-muted);line-height:1.5;max-height:48px;overflow:hidden;}
.post-meta{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-dim);margin-top:7px;display:flex;gap:12px;}
.post-tag{font-size:9.5px;padding:1px 6px;border-radius:3px;background:var(--elevated2);border:1px solid var(--border);margin-right:6px;}
/* Post detail */
#post-detail-view{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;}
.post-full-title{font-family:'Cinzel',serif;font-size:18px;font-weight:500;letter-spacing:.04em;color:var(--accent);}
.post-full-body{font-size:15px;color:var(--text);line-height:1.7;background:var(--elevated);border:1px solid var(--border);border-radius:var(--radius-sm);padding:14px 16px;}
.reply-item{display:flex;gap:10px;}
.reply-body{flex:1;background:var(--elevated);border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 13px;}
/* DMs */
#dm-list{flex:1;overflow-y:auto;padding:8px;}
.dm-item{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:var(--radius-sm);cursor:pointer;transition:background .12s;}
.dm-item:hover{background:var(--elevated);}
/* Upload */
#upload-zone{border:2px dashed var(--border);border-radius:var(--radius);padding:32px 20px;text-align:center;cursor:pointer;transition:all .2s;margin:16px;}
#upload-zone:hover,#upload-zone.drag{border-color:var(--accent);background:var(--accent-dim);}
.upload-icon{font-size:36px;opacity:.4;margin-bottom:10px;}
.upload-label{font-size:14px;color:var(--text-muted);}
.upload-sub{font-size:12px;color:var(--text-dim);font-family:'JetBrains Mono',monospace;margin-top:4px;}
/* Login */
#login-screen{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:18px;padding:40px;text-align:center;}
.login-logo{font-family:'Cinzel',serif;font-size:28px;font-weight:500;letter-spacing:.12em;color:var(--accent);}
.login-sub{color:var(--text-muted);font-size:15px;max-width:320px;line-height:1.6;}
.discord-btn{display:flex;align-items:center;gap:10px;background:#5865f2;color:#fff;font-family:'Cinzel',serif;font-size:13px;font-weight:500;letter-spacing:.06em;padding:12px 24px;border-radius:var(--radius-sm);cursor:pointer;transition:all .2s;border:none;}
.discord-btn:hover{background:#4752c4;transform:translateY(-1px);}
.discord-logo{width:22px;height:22px;fill:#fff;flex-shrink:0;}
.guest-note{font-size:12px;color:var(--text-dim);font-family:'JetBrains Mono',monospace;}
/* Toast */
#toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%) translateY(10px);background:var(--elevated2);border:1px solid var(--border-light);border-radius:var(--radius-sm);padding:8px 16px;font-size:12.5px;font-family:'JetBrains Mono',monospace;z-index:999;pointer-events:none;opacity:0;transition:all .2s;white-space:nowrap;}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0);}
/* New post / room modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;z-index:100;padding:20px;}
.modal-overlay.hidden{display:none;}
.modal-box{background:var(--surface);border:1px solid var(--border-light);border-radius:var(--radius);width:100%;max-width:540px;padding:0;overflow:hidden;}
.modal-head{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.modal-title{font-family:'Cinzel',serif;font-size:14px;letter-spacing:.06em;color:var(--accent);}
.modal-close{width:24px;height:24px;border-radius:4px;font-size:17px;color:var(--text-dim);display:flex;align-items:center;justify-content:center;}
.modal-close:hover{background:var(--elevated);color:var(--text);}
.modal-body{padding:16px 20px;display:flex;flex-direction:column;gap:12px;}
.modal-body input,.modal-body textarea,.modal-body select{width:100%;background:var(--elevated);border:1px solid var(--border);color:var(--text);border-radius:var(--radius-sm);padding:8px 11px;}
.modal-body select option{background:var(--elevated2);}
.modal-foot{padding:12px 20px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;gap:8px;}
.fl{font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px;display:block;}
</style>
</head>
<body>
<div id="toast"></div>
<!-- Card detail overlay -->
<div id="card-detail" class="hidden">
  <div class="card-detail-box">
    <img id="cd-img" src="" alt="" class="card-detail-img" style="display:none">
    <div class="card-detail-body">
      <div class="card-detail-name" id="cd-name"></div>
      <div class="card-detail-desc" id="cd-desc"></div>
      <div class="card-detail-actions">
        <button class="btn-accent" id="cd-download">⬇ Download Card</button>
        <button class="btn-ghost" onclick="closeCardDetail()">Close</button>
      </div>
    </div>
  </div>
</div>
<!-- New post modal -->
<div class="modal-overlay hidden" id="modal-post">
  <div class="modal-box">
    <div class="modal-head"><span class="modal-title">New Post</span><button class="modal-close" onclick="closeModal('modal-post')">×</button></div>
    <div class="modal-body">
      <div><label class="fl">Title</label><input type="text" id="post-title-inp" placeholder="What's this post about?"></div>
      <div><label class="fl">Tag (optional)</label>
        <select id="post-tag-inp"><option value="">None</option><option value="discussion">Discussion</option><option value="showcase">Showcase</option><option value="help">Help</option><option value="meta">Meta</option></select>
      </div>
      <div><label class="fl">Content</label><textarea id="post-content-inp" rows="5" placeholder="Write your post…"></textarea></div>
    </div>
    <div class="modal-foot"><button class="btn-ghost" onclick="closeModal('modal-post')">Cancel</button><button class="btn-accent" id="btn-submit-post">Post</button></div>
  </div>
</div>
<!-- New room modal -->
<div class="modal-overlay hidden" id="modal-room">
  <div class="modal-box">
    <div class="modal-head"><span class="modal-title">New Room</span><button class="modal-close" onclick="closeModal('modal-room')">×</button></div>
    <div class="modal-body">
      <div><label class="fl">Room Name</label><input type="text" id="room-name-inp" placeholder="e.g. fantasy-roleplay"></div>
      <div><label class="fl">Description</label><input type="text" id="room-desc-inp" placeholder="What's this room for?"></div>
    </div>
    <div class="modal-foot"><button class="btn-ghost" onclick="closeModal('modal-room')">Cancel</button><button class="btn-accent" id="btn-submit-room">Create</button></div>
  </div>
</div>

<div id="login-screen" style="display:none">
  <div class="login-logo">Persona</div>
  <div class="login-sub" id="server-name-display">Community Server</div>
  <p class="login-sub" style="font-size:13px">Sign in with Discord to join the chat, browse character cards, and share your own.</p>
  <button class="discord-btn" onclick="window.location='/login'">
    <svg class="discord-logo" viewBox="0 0 127.14 96.36"><path d="M107.7,8.07A105.15,105.15,0,0,0,81.47,0a72.06,72.06,0,0,0-3.36,6.83A97.68,97.68,0,0,0,49,6.83,72.37,72.37,0,0,0,45.64,0,105.89,105.89,0,0,0,19.39,8.09C2.79,32.65-1.71,56.6.54,80.21h0A105.73,105.73,0,0,0,32.71,96.36,77.7,77.7,0,0,0,39.6,85.25a68.42,68.42,0,0,1-10.85-5.18c.91-.66,1.8-1.34,2.66-2a75.57,75.57,0,0,0,64.32,0c.87.71,1.76,1.39,2.66,2a68.68,68.68,0,0,1-10.87,5.19,77,77,0,0,0,6.89,11.1A105.25,105.25,0,0,0,126.6,80.22h0C129.24,52.84,122.09,29.11,107.7,8.07ZM42.45,65.69C36.18,65.69,31,60,31,53s5-12.74,11.43-12.74S54,46,53.89,53,48.84,65.69,42.45,65.69Zm42.24,0C78.41,65.69,73.25,60,73.25,53s5-12.74,11.44-12.74S96.23,46,96.12,53,91.08,65.69,84.69,65.69Z"/></svg>
    Login with Discord
  </button>
  <div class="guest-note">Your Discord account is only used for display name and avatar.</div>
</div>

<div id="app" style="display:none">
  <aside id="sidebar">
    <div id="sidebar-header">
      <div class="logo" id="sidebar-server-name">Persona</div>
    </div>
    <div id="user-pill">
      <div class="user-ava" id="nav-ava">?</div>
      <div class="user-name" id="nav-username">…</div>
      <button onclick="window.location='/logout'" style="font-size:11px;color:var(--text-dim)" title="Logout">⏻</button>
    </div>
    <div class="nav-section-label">Rooms</div>
    <div id="rooms-nav"></div>
    <div class="nav-section-label">Direct Messages</div>
    <div id="dms-nav"></div>
    <div style="padding:0 10px;margin:4px 0">
      <button class="nav-item" style="width:100%;justify-content:center;color:var(--accent)" onclick="showView('upload')">⬆ Upload Card</button>
    </div>
    <div id="online-panel">
      <div class="online-label">Online</div>
      <div id="online-list"></div>
    </div>
  </aside>

  <main id="main">
    <div id="main-header">
      <div>
        <div class="main-title" id="view-title">general</div>
        <div class="main-sub" id="view-sub"></div>
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn-ghost" id="btn-gallery" onclick="showView('gallery')" style="padding:5px 10px;font-size:12px">◈ Cards</button>
        <button class="btn-ghost" id="btn-forum" onclick="loadForumPosts()" style="padding:5px 10px;font-size:12px">📌 Posts</button>
        <button class="btn-ghost" id="btn-new-post" onclick="openModal('modal-post')" style="padding:5px 10px;font-size:12px;display:none">+ Post</button>
        <button class="btn-ghost" id="btn-new-room" onclick="openModal('modal-room')" style="padding:5px 10px;font-size:12px">+ Room</button>
      </div>
    </div>

    <!-- Chat view -->
    <div class="view active" id="view-chat">
      <div id="chat-messages"></div>
      <div id="typing-bar" class="typing-indicator" style="min-height:20px"></div>
      <div id="chat-input-area">
        <div class="chat-input-row">
          <textarea id="chat-input" rows="1" placeholder="Message…"></textarea>
          <button class="send-btn" id="btn-send">➤</button>
        </div>
      </div>
    </div>

    <!-- Cards gallery view -->
    <div class="view" id="view-gallery">
      <div id="cards-grid"></div>
    </div>

    <!-- Forum view -->
    <div class="view" id="view-forum">
      <div id="posts-view"></div>
    </div>

    <!-- Post detail view -->
    <div class="view" id="view-post-detail">
      <div id="post-detail-view"></div>
    </div>

    <!-- DM view -->
    <div class="view" id="view-dm">
      <div id="chat-messages" style="display:none"></div>
      <div id="dm-messages" style="flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px;"></div>
      <div id="chat-input-area">
        <div class="chat-input-row">
          <textarea id="dm-input" rows="1" placeholder="Direct message…"></textarea>
          <button class="send-btn" id="btn-dm-send">➤</button>
        </div>
      </div>
    </div>

    <!-- Upload view -->
    <div class="view" id="view-upload">
      <div id="upload-zone">
        <div class="upload-icon">⬆</div>
        <div class="upload-label">Drop a PNG or JSON character card here</div>
        <div class="upload-sub">or click to browse</div>
        <input type="file" id="upload-input" accept=".png,.json" style="display:none">
      </div>
      <div id="upload-status" style="padding:0 16px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-muted)"></div>
    </div>
  </main>
</div>

<script>
'use strict';
const BASE = window.location.origin;
let ME = null, WS = null, currentRoom = 'general', currentDmUser = null;
let typingTimer = null, rooms = [], onlineUsers = [];

// ── Toast ─────────────────────────────────────────────────────
let _tt;
function toast(msg, ms=2800) {
  const el = document.getElementById('toast');
  el.textContent = msg; el.classList.add('show');
  clearTimeout(_tt); _tt = setTimeout(() => el.classList.remove('show'), ms);
}

// ── Modal helpers ─────────────────────────────────────────────
function openModal(id)  { document.getElementById(id).classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }
document.querySelectorAll('.modal-overlay').forEach(o =>
  o.addEventListener('click', e => { if (e.target === o) o.classList.add('hidden'); })
);

// ── API helpers ───────────────────────────────────────────────
async function api(path, method='GET', body=null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' }, credentials: 'include' };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(BASE + path, opts);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

// ── Init ──────────────────────────────────────────────────────
async function init() {
  let info;
  try { info = await api('/api/info'); } catch(e) { toast('Cannot reach server.'); return; }
  document.getElementById('sidebar-server-name').textContent = info.name;
  document.getElementById('server-name-display').textContent = info.name;

  if (!info.authenticated) {
    document.getElementById('login-screen').style.display = 'flex';
    document.getElementById('app').style.display = 'none';
    return;
  }
  ME = info.user;
  document.getElementById('login-screen').style.display = 'none';
  document.getElementById('app').style.display = 'flex';

  // Set user pill
  document.getElementById('nav-username').textContent = ME.global_name || ME.username;
  const avaEl = document.getElementById('nav-ava');
  if (ME.avatar_url) avaEl.innerHTML = `<img src="${ME.avatar_url}" alt="">`;
  else avaEl.textContent = (ME.username||'?')[0].toUpperCase();

  await loadRooms();
  await loadDMs();
  connectWS();
  selectRoom('general');
}

// ── Rooms ─────────────────────────────────────────────────────
async function loadRooms() {
  rooms = await api('/api/rooms').catch(() => []);
  const nav = document.getElementById('rooms-nav');
  nav.innerHTML = rooms.map(r => `
    <div class="nav-item${r.id===currentRoom?' active':''}" id="room-nav-${r.id}" onclick="selectRoom('${r.id}')">
      <span class="nav-item-icon">#</span>${r.name}
    </div>`).join('');
}

function selectRoom(roomId) {
  currentRoom = roomId; currentDmUser = null;
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.id === `room-nav-${roomId}`);
  });
  const room = rooms.find(r => r.id === roomId);
  document.getElementById('view-title').textContent = `# ${room?.name || roomId}`;
  document.getElementById('view-sub').textContent = room?.description || '';
  document.getElementById('btn-new-post').style.display = '';
  document.getElementById('btn-forum').style.display = '';
  showView('chat');
  loadMessages(roomId);
}

// ── Messages ──────────────────────────────────────────────────
async function loadMessages(roomId) {
  const msgs = await api(`/api/rooms/${roomId}/messages?limit=50`).catch(() => []);
  const wrap = document.getElementById('chat-messages');
  wrap.innerHTML = msgs.length
    ? msgs.map(msgEl).join('')
    : '<div class="system-msg">No messages yet. Say hello!</div>';
  wrap.scrollTop = wrap.scrollHeight;
}

function msgEl(m) {
  const a    = m.author || {};
  const ava  = a.avatar_url
    ? `<img src="${a.avatar_url}" alt="">`
    : (a.global_name||a.username||'?')[0].toUpperCase();
  const time = m.created_at ? new Date(m.created_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}) : '';
  return `<div class="msg">
    <div class="msg-ava">${ava}</div>
    <div class="msg-body">
      <div class="msg-meta">
        <span class="msg-author" onclick="openDM('${a.id}','${a.global_name||a.username||'?'}')" style="cursor:pointer">${a.global_name||a.username||'Unknown'}</span>
        <span class="msg-time">${time}</span>
      </div>
      <div class="msg-content">${escHtml(m.content)}</div>
    </div>
  </div>`;
}

async function sendMessage() {
  const inp = document.getElementById('chat-input');
  const txt = inp.value.trim(); if (!txt) return;
  inp.value = ''; inp.style.height = 'auto';
  try { await api(`/api/rooms/${currentRoom}/messages`, 'POST', { content: txt }); }
  catch(e) { toast('Failed to send: ' + e.message); inp.value = txt; }
}

document.getElementById('btn-send').onclick = sendMessage;
document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  // Typing indicator via WS
  if (WS && WS.readyState === 1) {
    WS.send(JSON.stringify({ type: 'typing', room_id: currentRoom }));
    clearTimeout(typingTimer);
  }
  setTimeout(() => {
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
  }, 0);
});

// ── Forum Posts ───────────────────────────────────────────────
async function loadForumPosts() {
  showView('forum');
  document.getElementById('view-title').textContent = `📌 Posts — #${currentRoom}`;
  document.getElementById('view-sub').textContent = '';
  const posts = await api(`/api/rooms/${currentRoom}/posts`).catch(() => []);
  const el = document.getElementById('posts-view');
  if (!posts.length) {
    el.innerHTML = '<div class="system-msg" style="padding:20px">No posts yet. Create the first one!</div>';
    return;
  }
  el.innerHTML = posts.map(p => `
    <div class="post-item" onclick="openPost('${p.id}')">
      ${p.tag ? `<span class="post-tag">${p.tag}</span>` : ''}
      <div class="post-title">${escHtml(p.title)}</div>
      <div class="post-excerpt">${escHtml(p.content)}</div>
      <div class="post-meta">
        <span>by ${p.author?.global_name||p.author?.username||'?'}</span>
        <span>${p.replies?.length||0} replies</span>
        <span>${new Date(p.created_at).toLocaleDateString()}</span>
      </div>
    </div>`).join('');
}

async function openPost(postId) {
  showView('post-detail');
  const posts = await api(`/api/rooms/${currentRoom}/posts`).catch(() => []);
  const p     = posts.find(x => x.id === postId);
  if (!p) { toast('Post not found.'); return; }
  const el = document.getElementById('post-detail-view');
  el.innerHTML = `
    <button class="btn-ghost" onclick="loadForumPosts()" style="align-self:flex-start;font-size:12px">← Back</button>
    ${p.tag ? `<span class="post-tag">${p.tag}</span>` : ''}
    <div class="post-full-title">${escHtml(p.title)}</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:10.5px;color:var(--text-dim)">
      by ${p.author?.global_name||'?'} · ${new Date(p.created_at).toLocaleString()}
    </div>
    <div class="post-full-body">${escHtml(p.content)}</div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);padding-top:4px">${p.replies?.length||0} replies</div>
    ${(p.replies||[]).map(r => `
      <div class="reply-item">
        <div class="msg-ava">${(r.author?.global_name||r.author?.username||'?')[0]}</div>
        <div class="reply-body">
          <div class="msg-meta">
            <span class="msg-author">${r.author?.global_name||r.author?.username||'?'}</span>
            <span class="msg-time">${new Date(r.created_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</span>
          </div>
          <div class="msg-content">${escHtml(r.content)}</div>
        </div>
      </div>`).join('')}
    <div style="display:flex;gap:8px;margin-top:8px">
      <textarea id="reply-inp" rows="2" placeholder="Write a reply…" style="flex:1;background:var(--elevated);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);padding:8px 11px;font-size:13.5px;font-family:'Crimson Pro',serif;resize:none;outline:none;"></textarea>
      <button class="btn-accent" onclick="submitReply('${postId}')" style="align-self:flex-end">Reply</button>
    </div>`;
}

async function submitReply(postId) {
  const inp = document.getElementById('reply-inp');
  const txt = inp.value.trim(); if (!txt) return;
  try {
    await api(`/api/posts/${postId}/replies`, 'POST', { content: txt });
    inp.value = '';
    await openPost(postId);
    toast('Reply posted!');
  } catch(e) { toast('Failed: ' + e.message); }
}

document.getElementById('btn-submit-post').onclick = async () => {
  const title   = document.getElementById('post-title-inp').value.trim();
  const content = document.getElementById('post-content-inp').value.trim();
  const tag     = document.getElementById('post-tag-inp').value;
  if (!title || !content) { toast('Title and content required.'); return; }
  try {
    await api(`/api/rooms/${currentRoom}/posts`, 'POST', { title, content, tag });
    closeModal('modal-post');
    document.getElementById('post-title-inp').value = '';
    document.getElementById('post-content-inp').value = '';
    await loadForumPosts();
    toast('Post created!');
  } catch(e) { toast('Failed: ' + e.message); }
};

document.getElementById('btn-submit-room').onclick = async () => {
  const name = document.getElementById('room-name-inp').value.trim();
  const desc = document.getElementById('room-desc-inp').value.trim();
  if (!name) { toast('Room name required.'); return; }
  try {
    await api('/api/rooms', 'POST', { name, description: desc });
    closeModal('modal-room');
    document.getElementById('room-name-inp').value = '';
    await loadRooms();
    toast(`Room #${name} created!`);
  } catch(e) { toast('Failed: ' + e.message); }
};

// ── DMs ───────────────────────────────────────────────────────
async function loadDMs() {
  const dms = await api('/api/dms').catch(() => []);
  const nav = document.getElementById('dms-nav');
  nav.innerHTML = dms.map(d => `
    <div class="nav-item" onclick="openDM('${d.other_user?.id}','${d.other_user?.global_name||d.other_user?.username||'?'}')">
      <span class="nav-item-icon">@</span>${d.other_user?.global_name||d.other_user?.username||'?'}
      ${d.unread ? `<span class="unread-badge">${d.unread}</span>` : ''}
    </div>`).join('');
}

async function openDM(userId, displayName) {
  if (userId === ME?.id) return;
  currentDmUser = userId;
  showView('dm');
  document.getElementById('view-title').textContent = `@ ${displayName}`;
  document.getElementById('view-sub').textContent = 'Direct Message';
  document.getElementById('btn-new-post').style.display = 'none';
  document.getElementById('btn-forum').style.display = 'none';
  const msgs  = await api(`/api/dms/${userId}`).catch(() => []);
  const wrap  = document.getElementById('dm-messages');
  wrap.innerHTML = msgs.length ? msgs.map(msgEl).join('') : '<div class="system-msg">Start a conversation!</div>';
  wrap.scrollTop = wrap.scrollHeight;
  await loadDMs(); // refresh unread counts
}

async function sendDM() {
  const inp = document.getElementById('dm-input');
  const txt = inp.value.trim(); if (!txt || !currentDmUser) return;
  inp.value = ''; inp.style.height = 'auto';
  try { await api(`/api/dms/${currentDmUser}`, 'POST', { content: txt }); }
  catch(e) { toast('Failed: ' + e.message); inp.value = txt; }
}

document.getElementById('btn-dm-send').onclick = sendDM;
document.getElementById('dm-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendDM(); }
  setTimeout(() => { e.target.style.height='auto'; e.target.style.height=Math.min(e.target.scrollHeight,120)+'px'; }, 0);
});

// ── Card Gallery ──────────────────────────────────────────────
let _selectedCard = null;

async function loadGallery() {
  showView('gallery');
  document.getElementById('view-title').textContent = 'Character Cards';
  document.getElementById('view-sub').textContent   = 'Browse & download cards';
  document.getElementById('btn-new-post').style.display = 'none';
  const cards  = await api('/api/cards').catch(() => []);
  const grid   = document.getElementById('cards-grid');
  if (!cards.length) { grid.innerHTML = '<div class="system-msg" style="padding:30px">No cards found.</div>'; return; }
  grid.innerHTML = cards.map(c => `
    <div class="card-item" onclick="openCard(${JSON.stringify(JSON.stringify(c))})">
      ${c.has_png
        ? `<img class="card-thumb" src="${c.url_thumb}" alt="" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
        : ''}
      <div class="card-thumb-placeholder" ${c.has_png?'style="display:none"':''}>◈</div>
      <div class="card-info">
        <div class="card-name">${escHtml(c.name)}</div>
        <div class="card-meta">${(c.size/1024).toFixed(1)} KB</div>
        <div style="display:flex;gap:6px;margin-top:6px;align-items:center;">
          <span class="source-badge source-${c.source}">${c.source}</span>
          ${c.nsfw ? '<span style="font-size:9.5px;font-weight:700;color:var(--red);padding:1px 5px;background:rgba(200,74,74,0.12);border-radius:3px">18+</span>' : ''}
        </div>
      </div>
    </div>`).join('');
}

function openCard(cardJson) {
  const c = JSON.parse(cardJson);
  _selectedCard = c;
  document.getElementById('card-detail').classList.remove('hidden');
  document.getElementById('cd-name').innerHTML = escHtml(c.name) + (c.nsfw ? ' <span style="font-size:12px;font-weight:700;color:var(--red);background:rgba(200,74,74,0.12);padding:2px 6px;border-radius:3px;vertical-align:middle;margin-left:8px">18+ / NSFW</span>' : '');
  document.getElementById('cd-desc').textContent = '';
  const img = document.getElementById('cd-img');
  if (c.has_png) { img.src = c.url_thumb; img.style.display = 'block'; }
  else img.style.display = 'none';
  document.getElementById('cd-download').onclick = () => {
    const a = Object.assign(document.createElement('a'), {
      href: BASE + c.url_download, download: c.filename,
    });
    a.click();
    toast(`Downloading ${c.filename}…`);
  };
}

function closeCardDetail() {
  document.getElementById('card-detail').classList.add('hidden');
  _selectedCard = null;
}
document.getElementById('card-detail').addEventListener('click', e => {
  if (e.target === document.getElementById('card-detail')) closeCardDetail();
});

// ── Upload ────────────────────────────────────────────────────
const uploadZone  = document.getElementById('upload-zone');
const uploadInput = document.getElementById('upload-input');

uploadZone.addEventListener('click', () => uploadInput.click());
uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault(); uploadZone.classList.remove('drag');
  const f = e.dataTransfer.files[0]; if (f) doUpload(f);
});
uploadInput.addEventListener('change', e => {
  const f = e.target.files[0]; if (f) doUpload(f);
  e.target.value = '';
});

async function doUpload(file) {
  const status = document.getElementById('upload-status');
  status.textContent = `Uploading ${file.name}…`;
  const fd = new FormData();
  fd.append('card', file);
  try {
    const res = await fetch(BASE + '/api/cards/upload', {
      method: 'POST', body: fd, credentials: 'include'
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    status.textContent = `✓ ${data.filename} uploaded!`;
    toast(`Card "${data.filename}" shared with the server!`);
    setTimeout(() => loadGallery(), 500);
  } catch(e) {
    status.textContent = `✗ Upload failed: ${e.message}`;
    toast('Upload failed: ' + e.message);
  }
}

// ── View switching ────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const el = document.getElementById(`view-${name}`);
  if (el) el.classList.add('active');
  if (name === 'gallery') loadGallery();
}

// ── WebSocket ─────────────────────────────────────────────────
function connectWS() {
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  const token = document.cookie.match(/persona_token=([^;]+)/)?.[1] || '';
  WS = new WebSocket(`${protocol}://${location.host}/ws?token=${token}`);

  WS.onmessage = e => {
    try { handleWS(JSON.parse(e.data)); } catch {}
  };
  WS.onclose = () => {
    setTimeout(connectWS, 3000); // auto-reconnect
  };
}

function handleWS(msg) {
  switch(msg.type) {
    case 'hello':
      onlineUsers = msg.online || [];
      renderOnlineUsers();
      break;
    case 'user_joined':
    case 'user_left':
      onlineUsers = msg.online || [];
      renderOnlineUsers();
      appendSystemMsg(msg.type === 'user_joined'
        ? `${msg.user.global_name||msg.user.username} joined`
        : `${msg.user.global_name||msg.user.username} left`);
      break;
    case 'message':
      if (msg.data.room_id === currentRoom) {
        const wrap = document.getElementById('chat-messages');
        const atBottom = wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight < 80;
        wrap.insertAdjacentHTML('beforeend', msgEl(msg.data));
        if (atBottom) wrap.scrollTop = wrap.scrollHeight;
      }
      break;
    case 'dm':
      if (currentDmUser === msg.data.author?.id) {
        const wrap = document.getElementById('dm-messages');
        wrap.insertAdjacentHTML('beforeend', msgEl(msg.data));
        wrap.scrollTop = wrap.scrollHeight;
      } else {
        toast(`DM from ${msg.data.author?.global_name||'someone'}`);
        loadDMs();
      }
      break;
    case 'typing':
      if (msg.room_id === currentRoom) showTyping(msg.user);
      break;
    case 'post_created':
      if (document.getElementById('view-forum').classList.contains('active'))
        loadForumPosts();
      break;
    case 'room_created':
      loadRooms();
      toast(`New room: #${msg.room.name}`);
      break;
    case 'card_uploaded':
      toast(`${msg.data.uploaded_by?.username||'Someone'} uploaded "${msg.data.name}"`);
      if (document.getElementById('view-gallery').classList.contains('active'))
        loadGallery();
      break;
  }
}

let _typingUsers = {};
function showTyping(user) {
  _typingUsers[user.id] = Date.now();
  renderTyping();
  setTimeout(() => {
    delete _typingUsers[user.id];
    renderTyping();
  }, 3000);
}
function renderTyping() {
  const names = Object.keys(_typingUsers)
    .filter(id => Date.now() - _typingUsers[id] < 3000)
    .map(id => onlineUsers.find(u => u.id === id)?.global_name || '…');
  document.getElementById('typing-bar').textContent =
    names.length ? `${names.join(', ')} ${names.length === 1 ? 'is' : 'are'} typing…` : '';
}

function renderOnlineUsers() {
  document.getElementById('online-list').innerHTML = onlineUsers.map(u => `
    <div class="online-user" onclick="openDM('${u.id}','${u.global_name||u.username||'?'}')">
      <div class="online-dot"></div>
      <div class="online-username">${u.global_name||u.username||'?'}</div>
    </div>`).join('');
}

function appendSystemMsg(text) {
  const wrap = document.getElementById('chat-messages');
  wrap.insertAdjacentHTML('beforeend', `<div class="system-msg">${escHtml(text)}</div>`);
}

// ── Utils ─────────────────────────────────────────────────────
function escHtml(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}

init();
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════
#  SERVER LIFECYCLE
# ══════════════════════════════════════════════════════════════

_server_instance = None
_server_thread   = None
_server_running  = False


def start(cfg: dict = None) -> dict:
    """Start the community server. Returns { ok, port, error }."""
    global _server_instance, _server_thread, _server_running

    if not _BOTTLE_OK:
        return {'ok': False, 'error': 'Server dependencies not installed (eel, geventwebsocket).'}
    if _server_running:
        return {'ok': True, 'port': _config['port'], 'error': None}

    if cfg:
        configure(cfg)

    port = _config['port']

    def _run():
        global _server_running, _server_instance
        try:
            _server_running = True
            # Bind to 127.0.0.1 when running behind nginx (VPS),
            # 0.0.0.0 for direct access (local Persona community server)
            bind_host = '127.0.0.1' if os.path.exists('/etc/nginx/nginx.conf') else '0.0.0.0'
            print(f'[persona] Listening on {bind_host}:{port}')
            _server_instance = WSGIServer(
                (bind_host, port), app,
                handler_class=WebSocketHandler,
            )
            _server_instance.serve_forever()
        except Exception as e:
            print(f'[community_server] {e}')
        finally:
            _server_running = False

    _server_thread = threading.Thread(target=_run, daemon=True)
    _server_thread.start()
    time.sleep(0.4)   # give it a moment to bind

    return {'ok': _server_running, 'port': port, 'error': None}


def stop() -> bool:
    """Stop the community server."""
    global _server_instance, _server_running
    if _server_instance:
        try:
            _server_instance.stop()
        except Exception:
            pass
        _server_instance = None
    _server_running = False
    return True


def is_running() -> bool:
    return _server_running


def get_stats() -> dict:
    with _ws_lock:
        connected = len(_ws_clients)
    users = _load(USERS_FILE, {})
    rooms = _load(ROOMS_FILE, [])
    msgs  = _load(MESSAGES_FILE, {})
    total_msgs = sum(len(v) for v in msgs.values())
    uploads = _config.get('uploads_folder', '')
    upload_count = len([f for f in os.listdir(uploads) if os.path.isfile(os.path.join(uploads, f))]) if os.path.isdir(uploads) else 0
    return {
        'running':       _server_running,
        'port':          _config['port'],
        'connected':     connected,
        'total_users':   len(users),
        'rooms':         len(rooms),
        'total_messages':total_msgs,
        'uploads':       upload_count,
    }
