"""
start.py — Persona Community Server (VPS entry point)
Configures server.py and starts it.  Lives in /opt/persona/start.py
"""

import os
import sys

# ── Paths ─────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CARDS_DIR   = os.path.join(BASE_DIR, 'cards')
UPLOADS_DIR = os.path.join(BASE_DIR, 'community', 'uploads')

os.makedirs(CARDS_DIR,   exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# ── Import server module ──────────────────────────────────────
sys.path.insert(0, BASE_DIR)
import server

# ── Configuration ─────────────────────────────────────────────
server.configure({
    'port':                   8765,
    'discord_client_id':      '',
    'discord_client_secret':  '',
    'redirect_uri':           'https://persona.dragonsphere.io/auth/callback',
    'server_name':            'Dragonsphere Community',
    'allow_uploads':          True,
    'chars_folder':           CARDS_DIR,
    'uploads_folder':         UPLOADS_DIR,
})

# ── Run directly (blocking) ───────────────────────────────────
from geventwebsocket.handler import WebSocketHandler
from gevent.pywsgi import WSGIServer

port = server._config['port']
print(f'[persona] Starting on port {port}...')
print(f'[persona] Cards dir : {CARDS_DIR}')
print(f'[persona] Uploads   : {UPLOADS_DIR}')
print(f'[persona] OAuth     : https://persona.dragonsphere.io/auth/callback')

srv = WSGIServer(('127.0.0.1', port), server.app, handler_class=WebSocketHandler)
print(f'[persona] Listening on 127.0.0.1:{port}')
srv.serve_forever()

