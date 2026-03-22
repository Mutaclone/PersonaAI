"""
app.py — Persona AI Roleplay
Eel bridge: file system, settings, and character card I/O.

PNG card format (SillyTavern / Chub / TavernAI standard):
  • A normal PNG image (the character portrait)
  • A 'tEXt' chunk with keyword='chara' and value=base64(JSON)
  • The JSON follows chara_card_v1 or chara_card_v2 spec

Import supports:  tEXt, iTXt, zTXt chunks  +  Pillow metadata fallback
Export supports:  embed JSON into any user-supplied artwork PNG,
                  or auto-use the character's avatar, or generate a
                  minimal placeholder if no image is available.
"""

import eel
import os
import sys
import json
import base64
import struct
import zlib

# ── Base directory ────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    # Directory containing the executable (for user data)
    APP_DIR = os.path.dirname(sys.executable)
    # Directory containing bundled PyInstaller assets (e.g. web/)
    BUNDLE_DIR = sys._MEIPASS
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR

CONFIG_FILE    = os.path.join(APP_DIR, 'settings.config')
DEFAULT_CHARS  = os.path.join(APP_DIR, 'characters')
DEFAULT_LOGS   = os.path.join(APP_DIR, 'logs')
DEFAULT_THEMES = os.path.join(APP_DIR, 'themes')

# ── Locate the web folder ─────────────────────────────────────
WEB_DIR = os.path.join(BUNDLE_DIR, 'web')
if not os.path.isdir(WEB_DIR):
    print(f'[FATAL] web/ folder not found at {WEB_DIR}')
    sys.exit(1)

eel.init(WEB_DIR)


# ══════════════════════════════════════════════════════════════
#  SETTINGS
# ══════════════════════════════════════════════════════════════

@eel.expose
def load_settings():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None
    return None


@eel.expose
def save_settings(json_str):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(json_str)
        return True
    except Exception as e:
        print(f'[save_settings] {e}')
        return False


@eel.expose
def get_default_chars_folder():
    return DEFAULT_CHARS

@eel.expose
def get_default_logs_folder():
    return DEFAULT_LOGS

@eel.expose
def get_default_themes_folder():
    return DEFAULT_THEMES


# ══════════════════════════════════════════════════════════════
#  DIALOGS
# ══════════════════════════════════════════════════════════════

def _make_tk():
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    return root


@eel.expose
def browse_for_folder(title='Select Folder'):
    try:
        from tkinter import filedialog
        root = _make_tk()
        path = filedialog.askdirectory(title=title, parent=root)
        root.destroy()
        return path if path else None
    except Exception as e:
        print(f'[browse_for_folder] {e}')
        return None


@eel.expose
def open_file_dialog(title, filetypes_json):
    try:
        from tkinter import filedialog
        filetypes = json.loads(filetypes_json)
        root = _make_tk()
        path = filedialog.askopenfilename(title=title, filetypes=filetypes, parent=root)
        root.destroy()
        return path if path else None
    except Exception as e:
        print(f'[open_file_dialog] {e}')
        return None


@eel.expose
def save_file_dialog(title, default_name, filetypes_json):
    try:
        from tkinter import filedialog
        filetypes = json.loads(filetypes_json)
        root = _make_tk()
        path = filedialog.asksaveasfilename(
            title=title, initialfile=default_name,
            filetypes=filetypes, parent=root,
        )
        root.destroy()
        return path if path else None
    except Exception as e:
        print(f'[save_file_dialog] {e}')
        return None


# ══════════════════════════════════════════════════════════════
#  PATH SAFETY
# ══════════════════════════════════════════════════════════════

def _safe_path(folder: str, filename: str) -> str:
    """
    Join folder + filename, then verify the resolved path stays within folder.
    Prevents path traversal via '../' or symlink tricks.
    Raises ValueError on violation.
    """
    resolved_folder = os.path.realpath(folder)
    resolved_path   = os.path.realpath(os.path.join(folder, filename))
    if not resolved_path.startswith(resolved_folder + os.sep) and resolved_path != resolved_folder:
        raise ValueError(f'Path traversal blocked: {filename!r}')
    return resolved_path


def _safe_full_path(full_path: str, allowed_folder: str) -> str:
    """
    Verify that a full file path lives within the allowed folder.
    Used for functions that receive absolute paths (e.g. log file paths).
    Raises ValueError on violation.
    """
    resolved_folder = os.path.realpath(allowed_folder)
    resolved_path   = os.path.realpath(full_path)
    if not resolved_path.startswith(resolved_folder + os.sep):
        raise ValueError(f'Path traversal blocked: {full_path!r}')
    return resolved_path


# ══════════════════════════════════════════════════════════════
#  CHARACTER FILE MANAGEMENT
# ══════════════════════════════════════════════════════════════

@eel.expose
def ensure_chars_folder(folder):
    os.makedirs(folder, exist_ok=True)
    return folder


@eel.expose
def list_character_files(folder):
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
        return []
    files = [f for f in os.listdir(folder)
             if f.lower().endswith(('.json', '.png'))]
    return sorted(files)


@eel.expose
def load_character_file(folder, filename):
    try:
        path = _safe_path(folder, filename)
        # PNG card in characters folder — extract embedded JSON
        if filename.lower().endswith('.png'):
            result = _read_card_file(path)
            return result.get('raw_json')
        with open(path, encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f'[load_character_file] {e}')
        return None


@eel.expose
def save_character_file(folder, filename, json_str):
    try:
        os.makedirs(folder, exist_ok=True)
        path = _safe_path(folder, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        return path
    except Exception as e:
        print(f'[save_character_file] {e}')
        return None


@eel.expose
def delete_character_file(folder, filename):
    try:
        path = _safe_path(folder, filename)
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception as e:
        print(f'[delete_character_file] {e}')
        return False


@eel.expose
def rename_character_file(folder, old_name, new_name):
    try:
        src  = _safe_path(folder, old_name)
        dest = _safe_path(folder, new_name)
        if os.path.exists(src):
            os.rename(src, dest)
        return True
    except Exception as e:
        print(f'[rename_character_file] {e}')
        return False


# ══════════════════════════════════════════════════════════════
#  CHAT LOGS
#  Each chat session is saved as a human-readable .txt file
#  in BASE_DIR/logs/<character_name>/<session_title>.txt
# ══════════════════════════════════════════════════════════════

def _safe_filename(name: str, max_len: int = 60) -> str:
    """Sanitise a string for use as a file/folder name."""
    import re
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip('. ')
    return name[:max_len] or 'unnamed'


@eel.expose
def save_chat_log(logs_folder: str, char_name: str, session_title: str,
                  messages: list, user_name: str = 'User') -> str | None:
    """
    Write a chat session to disk as a UTF-8 text file.
    Path: <logs_folder>/<char_name>/<session_title>.txt
    Returns the written path or None on error.
    """
    try:
        from datetime import datetime
        char_dir  = os.path.join(logs_folder, _safe_filename(char_name))
        os.makedirs(char_dir, exist_ok=True)

        # Build filename: title + timestamp suffix to avoid collisions
        ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{_safe_filename(session_title)}_{ts}.txt"
        path     = os.path.join(char_dir, filename)

        lines = [
            '═' * 60,
            'PERSONA AI — CHAT LOG',
            f'Character : {char_name}',
            f'Session   : {session_title}',
            f'Saved     : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
            '═' * 60,
            '',
        ]
        for msg in messages:
            role    = msg.get('role', 'unknown')
            content = msg.get('content', '')
            speaker = char_name if role == 'assistant' else user_name
            lines.append(f'[{speaker}]')
            lines.append(content)
            lines.append('')

        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return path
    except Exception as e:
        print(f'[save_chat_log] {e}')
        return None


@eel.expose
def list_log_files(logs_folder: str) -> list:
    """
    Return a list of { char, session, filename, path, modified }
    for every .txt file found recursively under logs_folder.
    Sorted newest-first by modification time.
    """
    results = []
    if not os.path.isdir(logs_folder):
        os.makedirs(logs_folder, exist_ok=True)
        return results
    for char_dir in sorted(os.listdir(logs_folder)):
        char_path = os.path.join(logs_folder, char_dir)
        if not os.path.isdir(char_path):
            continue
        for fname in sorted(os.listdir(char_path)):
            if not fname.lower().endswith('.txt'):
                continue
            fpath    = os.path.join(char_path, fname)
            modified = os.path.getmtime(fpath)
            results.append({
                'char':     char_dir,
                'filename': fname,
                'path':     fpath,
                'modified': modified,
            })
    results.sort(key=lambda r: r['modified'], reverse=True)
    return results


@eel.expose
def load_log_file(path: str) -> str | None:
    """Read and return the contents of a log file."""
    try:
        # Validate path stays within a known logs folder
        if DEFAULT_LOGS:
            _safe_full_path(path, DEFAULT_LOGS)
        with open(path, encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f'[load_log_file] {e}')
        return None


@eel.expose
def delete_log_file(path: str) -> bool:
    """Delete a log file. Returns True on success."""
    try:
        # Validate path stays within a known logs folder
        if DEFAULT_LOGS:
            _safe_full_path(path, DEFAULT_LOGS)
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception as e:
        print(f'[delete_log_file] {e}')
        return False


@eel.expose
def open_logs_folder(logs_folder: str) -> bool:
    """Open the logs folder in the system file explorer."""
    import subprocess, platform
    try:
        os.makedirs(logs_folder, exist_ok=True)
        system = platform.system()
        if system == 'Windows':
            os.startfile(logs_folder)
        elif system == 'Darwin':
            subprocess.Popen(['open', logs_folder])
        else:
            subprocess.Popen(['xdg-open', logs_folder])
        return True
    except Exception as e:
        print(f'[open_logs_folder] {e}')
        return False


# ══════════════════════════════════════════════════════════════
#  THEMES
#  Custom themes are stored as .json files in BASE_DIR/themes/
# ══════════════════════════════════════════════════════════════

@eel.expose
def list_theme_files(themes_folder: str) -> list:
    """
    Return list of { name, filename, path } for every .json theme in folder.
    Tries to read the 'name' field from each file without loading the full CSS.
    """
    results = []
    if not os.path.isdir(themes_folder):
        os.makedirs(themes_folder, exist_ok=True)
        return results
    for fname in sorted(os.listdir(themes_folder)):
        if not fname.lower().endswith('.json'):
            continue
        fpath = os.path.join(themes_folder, fname)
        name  = fname.replace('.json', '')
        try:
            with open(fpath, encoding='utf-8') as f:
                data = json.load(f)
            name = data.get('name', name)
        except Exception:
            pass
        results.append({'name': name, 'filename': fname, 'path': fpath})
    return results


@eel.expose
def load_theme_file(themes_folder: str, filename: str) -> str | None:
    """Load a theme JSON file and return its raw string."""
    try:
        path = _safe_path(themes_folder, filename)
        with open(path, encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f'[load_theme_file] {e}')
        return None


@eel.expose
def save_theme_file(themes_folder: str, filename: str, json_str: str) -> str | None:
    """Save a theme JSON string to the themes folder. Returns path or None."""
    try:
        os.makedirs(themes_folder, exist_ok=True)
        path = _safe_path(themes_folder, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        return path
    except Exception as e:
        print(f'[save_theme_file] {e}')
        return None


@eel.expose
def delete_theme_file(themes_folder: str, filename: str) -> bool:
    """Delete a theme file."""
    try:
        path = _safe_path(themes_folder, filename)
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception as e:
        print(f'[delete_theme_file] {e}')
        return False


# ══════════════════════════════════════════════════════════════
#  DISCORD API PROXY
#  All bot-token requests are routed through Python to avoid
#  CORS restrictions that Discord enforces on browser requests.
#  Webhook sends stay in JS (Discord allows those cross-origin).
# ══════════════════════════════════════════════════════════════

import urllib.request
import urllib.error

DC_API = 'https://discord.com/api/v10'


def _dc_request(path: str, bot_token: str, method: str = 'GET',
                body: bytes | None = None) -> dict:
    """
    Make a Discord API request using urllib (no third-party deps).
    Returns the parsed JSON response or raises an exception.
    """
    url     = DC_API + path
    headers = {
        'Authorization': f'Bot {bot_token}',
        'Content-Type':  'application/json',
        'User-Agent':    'PersonaApp/1.0',
    }
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode('utf-8')
            return {'ok': True, 'data': json.loads(raw), 'status': resp.status}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        return {'ok': False, 'error': f'HTTP {e.code}: {body_text[:300]}',
                'status': e.code, 'data': None}
    except Exception as ex:
        return {'ok': False, 'error': str(ex), 'status': 0, 'data': None}


@eel.expose
def discord_fetch_messages(bot_token: str, channel_id: str,
                           limit: int = 50, after: str = '') -> dict:
    """
    Fetch messages from a Discord channel.
    Returns { ok, messages: [...], error }.
    Messages are returned oldest-first (reversed from Discord default).
    """
    if not bot_token:
        return {'ok': False, 'messages': [], 'error': 'No bot token provided.'}
    if not channel_id:
        return {'ok': False, 'messages': [], 'error': 'No channel ID provided.'}

    params = f'?limit={min(limit, 100)}'
    if after:
        params += f'&after={after}'

    result = _dc_request(f'/channels/{channel_id}/messages{params}', bot_token)

    if not result['ok']:
        # Friendly messages for common errors
        status = result.get('status', 0)
        err    = result.get('error', 'Unknown error')
        if status == 401:
            err = 'Invalid bot token. Check your token in Discord Settings.'
        elif status == 403:
            err = 'Missing permissions. Make sure the bot has "Read Message History" in that channel.'
        elif status == 404:
            err = 'Channel not found. Double-check the Channel ID.'
        return {'ok': False, 'messages': [], 'error': err}

    messages = result['data']
    if not isinstance(messages, list):
        return {'ok': False, 'messages': [], 'error': 'Unexpected response from Discord.'}

    # Reverse so oldest is first (Discord returns newest-first)
    messages.reverse()
    return {'ok': True, 'messages': messages, 'error': None}


@eel.expose
def discord_fetch_messages_batch(bot_token: str, channel_id: str,
                                  batch_count: int = 2) -> dict:
    """
    Fetch up to batch_count × 100 messages for the card scanner.
    Returns { ok, messages: [...], error }.
    """
    if not bot_token or not channel_id:
        return {'ok': False, 'messages': [],
                'error': 'Bot token and channel ID required.'}

    all_messages = []
    before = ''

    for _ in range(max(1, min(batch_count, 5))):
        params = '?limit=100'
        if before:
            params += f'&before={before}'
        result = _dc_request(f'/channels/{channel_id}/messages{params}', bot_token)
        if not result['ok']:
            if not all_messages:
                return {'ok': False, 'messages': [], 'error': result.get('error', 'API error')}
            break
        batch = result['data']
        if not isinstance(batch, list) or not batch:
            break
        all_messages.extend(batch)
        before = batch[-1]['id']   # oldest in this batch

    return {'ok': True, 'messages': all_messages, 'error': None}


@eel.expose
def discord_get_channel_info(bot_token: str, channel_id: str) -> dict:
    """
    Fetch channel info (name, guild_id, etc.).
    Returns { ok, channel, error }.
    """
    if not bot_token or not channel_id:
        return {'ok': False, 'channel': None, 'error': 'Token and channel ID required.'}
    result = _dc_request(f'/channels/{channel_id}', bot_token)
    if not result['ok']:
        return {'ok': False, 'channel': None, 'error': result.get('error')}
    return {'ok': True, 'channel': result['data'], 'error': None}


# ══════════════════════════════════════════════════════════════
#  PNG CHUNK HELPERS
# ══════════════════════════════════════════════════════════════

def _png_sig():
    return b'\x89PNG\r\n\x1a\n'

def _is_png(data: bytes) -> bool:
    return data[:8] == _png_sig()

def _is_jpeg(data: bytes) -> bool:
    return data[:2] == b'\xff\xd8'

def _make_chunk(chunk_type: bytes, chunk_data: bytes) -> bytes:
    """Assemble a valid PNG chunk: length + type + data + CRC."""
    crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
    return struct.pack('>I', len(chunk_data)) + chunk_type + chunk_data + struct.pack('>I', crc)

def _decode_chara_value(raw: bytes) -> str | None:
    """
    The 'chara' chunk value may be:
      • base64-encoded JSON  (standard — SillyTavern, Chub, TavernAI)
      • raw UTF-8 JSON       (some custom exporters)
    Returns a validated JSON string or None.
    """
    text = raw.decode('utf-8', errors='replace').strip()

    # Try base64 first (the standard)
    try:
        # Add padding just in case
        padded = text + '=' * (-len(text) % 4)
        decoded = base64.b64decode(padded).decode('utf-8')
        json.loads(decoded)
        return decoded
    except Exception:
        pass

    # Raw JSON fallback
    if text.startswith('{') or text.startswith('['):
        try:
            json.loads(text)
            return text
        except Exception:
            pass

    return None


def _walk_png_chunks(data: bytes):
    """Generator: yields (chunk_type_bytes, chunk_data_bytes) for every chunk."""
    idx = 8  # skip PNG signature
    while idx + 12 <= len(data):
        try:
            length     = struct.unpack('>I', data[idx:idx+4])[0]
            chunk_type = data[idx+4:idx+8]
            chunk_data = data[idx+8:idx+8+length]
            yield chunk_type, chunk_data
            idx += 12 + length
        except (struct.error, IndexError):
            break


def _extract_chara_from_png_bytes(data: bytes) -> str | None:
    """
    Parse PNG bytes and extract the 'chara' field from tEXt / iTXt / zTXt chunks.
    Returns a JSON string or None.
    """
    for ctype, cdata in _walk_png_chunks(data):

        # ── tEXt: keyword\0value ──────────────────────────────
        if ctype == b'tEXt':
            nul = cdata.find(b'\x00')
            if nul < 0:
                continue
            keyword = cdata[:nul].decode('latin-1').strip().lower()
            if keyword == 'chara':
                return _decode_chara_value(cdata[nul+1:])

        # ── iTXt: keyword\0comp_flag\0comp_method\0lang\0trans\0value ──
        elif ctype == b'iTXt':
            nul = cdata.find(b'\x00')
            if nul < 0:
                continue
            keyword = cdata[:nul].decode('utf-8', errors='replace').strip().lower()
            if keyword == 'chara':
                rest       = cdata[nul+1:]
                comp_flag  = rest[0] if rest else 0
                # Skip: comp_flag(1) + comp_method(1) + lang\0 + trans\0
                p = 2
                p = rest.find(b'\x00', p) + 1  # skip lang
                p = rest.find(b'\x00', p) + 1  # skip translated keyword
                payload = rest[p:]
                if comp_flag:
                    try:
                        payload = zlib.decompress(payload)
                    except Exception:
                        continue
                return _decode_chara_value(payload)

        # ── zTXt: keyword\0\x00zlib_data ─────────────────────
        elif ctype == b'zTXt':
            nul = cdata.find(b'\x00')
            if nul < 0:
                continue
            keyword = cdata[:nul].decode('latin-1').strip().lower()
            if keyword == 'chara':
                try:
                    payload = zlib.decompress(cdata[nul+2:])
                    return _decode_chara_value(payload)
                except Exception:
                    continue

    return None


def _extract_chara_with_pillow(path: str) -> str | None:
    """Pillow-based fallback — catches WebP, malformed PNGs, EXIF."""
    try:
        from PIL import Image
        img = Image.open(path)
        # Standard tEXt metadata dict
        val = img.info.get('chara') or img.info.get('Chara')
        if val:
            if isinstance(val, bytes):
                return _decode_chara_value(val)
            return _decode_chara_value(val.encode('utf-8'))
        # EXIF UserComment (some apps write here)
        exif = img._getexif() if hasattr(img, '_getexif') and img._getexif else None
        if exif:
            for tag_id, tag_val in exif.items():
                if tag_id == 0x9286 and isinstance(tag_val, bytes):
                    return _decode_chara_value(tag_val)
    except ImportError:
        pass
    except Exception as e:
        print(f'[pillow_extract] {e}')
    return None


# ══════════════════════════════════════════════════════════════
#  PNG AVATAR EXTRACTION
# ══════════════════════════════════════════════════════════════

def _png_bytes_to_avatar_b64(raw_bytes: bytes, path: str = '') -> str | None:
    """
    Convert a PNG (or any image) to a square 256×256 data URI for use as avatar.
    Crops top-center so portrait images keep the face.
    """
    try:
        from PIL import Image
        import io
        img  = Image.open(io.BytesIO(raw_bytes)).convert('RGBA')
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top  = 0  # bias top for face-heavy portraits
        img  = img.crop((left, top, left + side, top + side))
        img  = img.resize((256, 256), Image.LANCZOS)
        buf  = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        # No Pillow — return the whole file
        return 'data:image/png;base64,' + base64.b64encode(raw_bytes).decode()
    except Exception as e:
        print(f'[png_to_avatar] {e}')
        return None


# ══════════════════════════════════════════════════════════════
#  UNIVERSAL CARD FILE READER
# ══════════════════════════════════════════════════════════════

def _read_card_file(path: str) -> dict:
    """
    Read any character card file.
    Returns:
      { ok, raw_json, avatar_b64, source_format, error }
    
    source_format values: 'png_chara' | 'json' | 'png_no_data' | 'jpeg' | 'unknown'
    """
    try:
        with open(path, 'rb') as f:
            raw_bytes = f.read()
    except Exception as e:
        return _err(str(e))

    ext = os.path.splitext(path)[1].lower()

    # ── PNG / WebP image ──────────────────────────────────────
    if _is_png(raw_bytes) or ext in ('.png', '.webp'):
        # 1. Fast raw byte parser
        chara_json = _extract_chara_from_png_bytes(raw_bytes) if _is_png(raw_bytes) else None
        # 2. Pillow fallback (WebP, edge cases)
        if not chara_json:
            chara_json = _extract_chara_with_pillow(path)

        if not chara_json:
            return {
                'ok': False, 'raw_json': None,
                'avatar_b64': _png_bytes_to_avatar_b64(raw_bytes, path),
                'source_format': 'png_no_data',
                'error': (
                    'No character card data found in this PNG.\n\n'
                    'This image does not contain an embedded character card.\n'
                    'Character card PNGs are created by SillyTavern, Chub.ai,\n'
                    'or by exporting from Persona as a PNG card.\n\n'
                    'If you just want to use this as an avatar, import it\n'
                    'as a character and set the image manually.'
                ),
            }

        avatar_b64 = _png_bytes_to_avatar_b64(raw_bytes, path)
        return {
            'ok': True, 'raw_json': chara_json,
            'avatar_b64': avatar_b64, 'source_format': 'png_chara',
            'error': None,
        }

    # ── JPEG — no card data possible ──────────────────────────
    if _is_jpeg(raw_bytes):
        return {
            'ok': False, 'raw_json': None,
            'avatar_b64': None, 'source_format': 'jpeg',
            'error': (
                'JPEGs cannot store character card data.\n\n'
                'To import a character: use a PNG card exported from\n'
                'SillyTavern, Chub.ai, or Persona.\n\n'
                'To use this image as an avatar: create the character\n'
                'manually and paste the image URL or upload the file.'
            ),
        }

    # ── JSON file ──────────────────────────────────────────────
    try:
        text = raw_bytes.decode('utf-8-sig').strip()
        json.loads(text)
        return {
            'ok': True, 'raw_json': text,
            'avatar_b64': None, 'source_format': 'json',
            'error': None,
        }
    except Exception:
        pass

    return _err('Unrecognised file format. Supported: PNG card, JSON card.')


def _err(msg):
    return {'ok': False, 'raw_json': None, 'avatar_b64': None,
            'source_format': 'unknown', 'error': msg}


# ══════════════════════════════════════════════════════════════
#  CARD IMPORT  (eel-exposed)
# ══════════════════════════════════════════════════════════════

@eel.expose
def import_card_dialog():
    """
    Open a native file picker and import a character card.
    Returns { ok, raw_json, avatar_b64, source_format, source_path, error }
    """
    try:
        from tkinter import filedialog
        root = _make_tk()
        path = filedialog.askopenfilename(
            title='Import Character Card',
            filetypes=[
                ('Character Cards', '*.png *.json *.webp'),
                ('PNG Card (with embedded data)', '*.png'),
                ('JSON Card', '*.json'),
                ('All Files', '*.*'),
            ],
            parent=root,
        )
        root.destroy()
        if not path:
            return {**_err('Cancelled'), 'source_path': None}
        result = _read_card_file(path)
        result['source_path'] = path
        return result
    except Exception as e:
        return {**_err(str(e)), 'source_path': None}


@eel.expose
def read_card_from_path(path: str):
    """Read a card from a known path (drag-and-drop). Same return shape."""
    result = _read_card_file(path)
    result['source_path'] = path
    return result


@eel.expose
def read_image_as_avatar(path: str) -> str | None:
    """
    Load any image file and return it as a base64 data URI avatar.
    Used when the user drops a plain PNG (not a card) onto the character editor.
    """
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        return _png_bytes_to_avatar_b64(raw, path)
    except Exception as e:
        print(f'[read_image_as_avatar] {e}')
        return None


# ══════════════════════════════════════════════════════════════
#  CARD EXPORT  (eel-exposed)
# ══════════════════════════════════════════════════════════════

@eel.expose
def export_card_dialog(card_json_str: str, default_name: str, fmt: str):
    """
    Open a save dialog and write a card.
    fmt: 'json_v2' | 'json_v1' | 'persona' | 'png'
    For 'png': uses the avatar embedded in card_json_str as the image.
    Returns { ok, path, error }
    """
    try:
        from tkinter import filedialog
        is_png = fmt == 'png'
        root   = _make_tk()
        path   = filedialog.asksaveasfilename(
            title='Export Character Card',
            initialfile=default_name + ('.png' if is_png else '.json'),
            defaultextension='.png' if is_png else '.json',
            filetypes=[('PNG Card', '*.png')] if is_png else [('JSON Card', '*.json')],
            parent=root,
        )
        root.destroy()
        if not path:
            return {'ok': False, 'path': None, 'error': 'Cancelled'}

        if is_png:
            _write_png_card(path, card_json_str, artwork_path=None)
        else:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(card_json_str)

        return {'ok': True, 'path': path, 'error': None}
    except Exception as e:
        return {'ok': False, 'path': None, 'error': str(e)}


@eel.expose
def export_png_card_with_artwork(card_json_str: str, default_name: str):
    """
    Two-step PNG export:
      1. Ask user to pick a source artwork PNG (the portrait image).
      2. Ask where to save the output card PNG.
      3. Copy the artwork PNG, inject the chara tEXt chunk, save.

    If the user skips step 1, falls back to the avatar in card_json_str.
    Returns { ok, path, error }
    """
    try:
        from tkinter import filedialog

        # Step 1 — Pick artwork (optional, user can cancel to use avatar)
        root = _make_tk()
        artwork_path = filedialog.askopenfilename(
            title='Select Artwork PNG for Card (cancel to use character avatar)',
            filetypes=[
                ('PNG Images', '*.png'),
                ('All Images', '*.png *.jpg *.jpeg *.webp'),
                ('All Files',  '*.*'),
            ],
            parent=root,
        )
        root.destroy()

        # Step 2 — Pick save destination
        root = _make_tk()
        out_path = filedialog.asksaveasfilename(
            title='Save PNG Card As',
            initialfile=default_name + '.png',
            defaultextension='.png',
            filetypes=[('PNG Card', '*.png'), ('All Files', '*.*')],
            parent=root,
        )
        root.destroy()

        if not out_path:
            return {'ok': False, 'path': None, 'error': 'Cancelled'}

        _write_png_card(out_path, card_json_str,
                        artwork_path=artwork_path if artwork_path else None)

        return {'ok': True, 'path': out_path,
                'artwork_used': artwork_path or 'avatar', 'error': None}

    except Exception as e:
        return {'ok': False, 'path': None, 'error': str(e)}


def _write_png_card(out_path: str, card_json_str: str, artwork_path: str | None = None):
    """
    Write a PNG file with card JSON embedded as a tEXt 'chara' chunk.

    Priority for the image:
      1. artwork_path  — user-supplied portrait PNG
      2. avatar field  — base64 data URI inside card_json_str
      3. placeholder   — dark 400×600 rectangle
    """
    chara_b64 = base64.b64encode(card_json_str.encode('utf-8')).decode()

    # Attempt Pillow path (best quality)
    try:
        from PIL import Image, PngImagePlugin
        import io

        img = None

        # ── 1. User-supplied artwork ────────────────────────────
        if artwork_path and os.path.isfile(artwork_path):
            try:
                img = Image.open(artwork_path).convert('RGBA')
                print(f'[png_export] Using artwork: {artwork_path}')
            except Exception as e:
                print(f'[png_export] Could not open artwork: {e}')

        # ── 2. Avatar from card JSON ────────────────────────────
        if img is None:
            try:
                data   = json.loads(card_json_str)
                avatar = (data.get('avatar') or
                          (data.get('data') or {}).get('avatar') or '')
                if avatar and avatar.startswith('data:image'):
                    _, b64part = avatar.split(',', 1)
                    img = Image.open(io.BytesIO(base64.b64decode(b64part))).convert('RGBA')
                    print('[png_export] Using avatar from card JSON')
            except Exception as e:
                print(f'[png_export] Could not decode avatar: {e}')

        # ── 3. Placeholder ──────────────────────────────────────
        if img is None:
            img = Image.new('RGBA', (400, 600), (15, 10, 20, 255))
            print('[png_export] Using placeholder image')

        # Resize to portrait card dimensions
        img = img.resize((400, 600), Image.LANCZOS)

        info = PngImagePlugin.PngInfo()
        info.add_text('chara', chara_b64)
        img.save(out_path, pnginfo=info)
        return

    except ImportError:
        print('[png_export] Pillow not available, using raw PNG writer')

    # ── Raw PNG fallback (no Pillow) ──────────────────────────
    # Try to use artwork as-is if it's already a valid PNG
    if artwork_path and os.path.isfile(artwork_path):
        try:
            with open(artwork_path, 'rb') as f:
                src_bytes = f.read()
            if _is_png(src_bytes):
                _inject_chara_into_png(src_bytes, chara_b64, out_path)
                return
        except Exception as e:
            print(f'[png_export_raw] artwork read error: {e}')

    # Ultimate fallback: minimal 1×1 PNG with just the chara chunk
    _write_minimal_png(out_path, chara_b64)


def _inject_chara_into_png(src_bytes: bytes, chara_b64: str, out_path: str):
    """
    Take an existing PNG's bytes, strip any existing 'chara' tEXt chunks,
    inject a fresh one right after IHDR, and write to out_path.
    """
    text_chunk = _make_chunk(b'tEXt', b'chara\x00' + chara_b64.encode('latin-1'))

    out = bytearray(_png_sig())
    first_idat = True

    for ctype, cdata in _walk_png_chunks(src_bytes):
        # Skip any existing chara chunks
        if ctype == b'tEXt':
            nul = cdata.find(b'\x00')
            if nul >= 0 and cdata[:nul].decode('latin-1').lower() == 'chara':
                continue

        raw_chunk = _make_chunk(ctype, cdata)

        # Inject our chara chunk right before the first IDAT
        if ctype == b'IDAT' and first_idat:
            out += text_chunk
            first_idat = False

        out += raw_chunk

    with open(out_path, 'wb') as f:
        f.write(bytes(out))


def _write_minimal_png(out_path: str, chara_b64: str):
    """Write a valid 1×1 PNG with only the chara tEXt chunk as data."""
    sig  = _png_sig()
    ihdr = _make_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    text = _make_chunk(b'tEXt', b'chara\x00' + chara_b64.encode('latin-1'))
    idat = _make_chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00'))
    iend = _make_chunk(b'IEND', b'')
    with open(out_path, 'wb') as f:
        f.write(sig + ihdr + text + idat + iend)


# ══════════════════════════════════════════════════════════════
#  COMMUNITY SERVER BRIDGE
# ══════════════════════════════════════════════════════════════

import server as _community_server


@eel.expose
def community_server_start(cfg: dict) -> dict:
    """
    Start the community server with the given config.
    cfg keys: port, discord_client_id, discord_client_secret,
              redirect_uri, chars_folder, uploads_folder,
              server_name, allow_uploads
    """
    # Ensure chars folder falls back to our default
    if not cfg.get('chars_folder'):
        cfg['chars_folder'] = DEFAULT_CHARS
    if not cfg.get('uploads_folder'):
        cfg['uploads_folder'] = os.path.join(
            os.path.join(APP_DIR, 'community'), 'uploads')
    return _community_server.start(cfg)


@eel.expose
def community_server_stop() -> bool:
    """Stop the community server."""
    return _community_server.stop()


@eel.expose
def community_server_stats() -> dict:
    """Return live server stats: running, port, connected, etc."""
    return _community_server.get_stats()


@eel.expose
def community_server_is_running() -> bool:
    return _community_server.is_running()


@eel.expose
def get_local_ip() -> str:
    """Return the machine's LAN IP address for sharing with friends."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


# ══════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════

def start():
    import sys

    def on_close(route, websockets):
        """Called when the last browser tab/window closes."""
        if not websockets:
            # Stop community server if running
            try:
                _community_server.stop()
            except Exception:
                pass
            sys.exit(0)

    eel.start(
        'index.html',
        size=(1280, 820),
        position=(80, 60),
        port=0,
        block=True,
        close_callback=on_close,
    )
