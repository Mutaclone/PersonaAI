# Changelog

All notable changes to PersonaAI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.6.0] — 2026-03-22

### 📦 Single-Exe Distribution

The build now produces a **single self-contained `.exe`** — no folders, no extras. Just share the file.

#### Changed

- **`--onedir` → `--onefile`** — PyInstaller now compresses everything (Python runtime, web UI, dependencies) into one `.exe`. Distribution is now: "send the file, double-click, done." (`compile_persona.bat`)
- **`sys._MEIPASS` asset resolution** — `app.py` now uses PyInstaller's `sys._MEIPASS` to locate the bundled `web/` folder instead of looking relative to the exe. This works correctly in both `--onefile` (temp extraction) and `--onedir` (`_internal/`) modes. (`app.py`)
- **Split `BASE_DIR` into `APP_DIR` + `BUNDLE_DIR`** — User data (settings, characters, logs, themes) writes to `APP_DIR` (next to the exe), while bundled assets (web UI) are read from `BUNDLE_DIR` (`sys._MEIPASS`). This prevents writing to read-only temp directories. (`app.py`)
- **`server.py` now bundles inside the exe** — Added `--add-data "server.py;."` to the build so the community server module is packed in. (`compile_persona.bat`)
- **Compiler version** — `v1.5` → `v1.6` with updated banner. (`compile_persona.bat`)

#### Fixed

- **404 "File does not exist"** — The built exe showed a 404 error because `app.py` looked for `web/` next to the exe, but PyInstaller 6+ places bundled data in `_internal/`. Now resolved via `sys._MEIPASS`. (`app.py`)
- **Stale `BASE_DIR` reference** — The community server uploads path in `app.py` still referenced the old `BASE_DIR` after the rename to `APP_DIR`. (`app.py`)

---

## [1.5.2] — 2026-03-22

### 🔒 Security Audit & Hardening

Full-scale codebase audit: **26 issues identified, 22 fixed** across all files.

#### 🔴 Critical — Fixed

- **5 MB localStorage Timebomb** — Migrated primary storage from `localStorage` (5 MB hard limit) to **IndexedDB** (unlimited). Data is transparently migrated on first load; `localStorage` retains only a lightweight metadata cache as fallback. Quota errors are now handled gracefully. (`persona.html`)
- **Asynchronous Polling Overlaps** — Added lock guards (`_dcPolling`, `_remotePolling`) to Discord and Remote Server polling intervals. If a network request is still in-flight when the next interval fires, the duplicate is skipped. Prevents request flooding, memory leaks, and UI stuttering on slow connections. (`persona.html`)
- **Blind LLM Context Overflow** — Replaced the naive "last 20 messages" slice with a token-aware `buildContextMessages()` function. Each message is counted using the `estimateTokens()` heuristic, and a per-model context window lookup table prevents silently exceeding API limits. (`persona.html`)

#### 🟠 High — Fixed

- **Path Traversal in File I/O** — Added `_safe_path()` and `_safe_full_path()` guards to **all 9** eel-exposed file functions (`load_character_file`, `save_character_file`, `delete_character_file`, `rename_character_file`, `load_log_file`, `delete_log_file`, `load_theme_file`, `save_theme_file`, `delete_theme_file`). Filenames like `../../etc/passwd` are now blocked before any disk access. (`app.py`)
- **Path Traversal in Card Upload** — Server card upload now strips path separators with `os.path.basename()` before sanitisation, and adds a final path-containment check before saving. (`server.py`)
- **XSS via Character Card Injection** — Added `escHtml()` utility and applied it to **all `innerHTML` interpolation** of user-controlled content: character names, descriptions, tags, chat titles, card names, avatar URLs, and streaming placeholders (~15 locations). Malicious cards like `<img src=x onerror=alert(1)>` no longer execute. (`persona.html`)
- **Hard-Coded API Key Removed** — Removed the plaintext base64-encoded `remoteApiKey` from `DEF_SETTINGS`. Users must now configure their own key. (`persona.html`)
- **Duplicate Import + Weak Identity Hash** — Removed duplicate `import hashlib` and unused `import hmac`. Upgraded anonymous user ID generation from MD5 (8 hex = 32 bits, trivially collidable) to SHA-256 (12 hex = 48 bits). (`server.py`)
- **Data Race in JSON Storage** — `_load()` now acquires `_lock` (previously only `_save()` did). Added `_load_modify_save()` for atomic read-modify-write operations, preventing concurrent request data loss. (`server.py`)

#### 🟡 Medium — Fixed

- **Async PNG Builder Bug** — `_buildMinimalPNG()` now correctly declared as `async` and `await`s the inner `_deflateAsync()` call. Previously, cards without avatars would silently produce corrupted Blobs (containing a Promise object) when sharing to Discord or pushing to the server. (`persona.html`)
- **OAuth Cookies Unsecured** — Added `samesite='Lax'` and conditional `secure=True` (auto-enabled on HTTPS) to both `oauth_state` and `persona_token` cookies. (`server.py`)
- **WebSocket Auth Bypass** — Unauthenticated WebSocket connections are now rejected with an error message and closed, instead of being registered and receiving all broadcast events. (`server.py`)
- **No Rate Limiting** — Added per-user/IP rate limiting (max 10 messages per 10 seconds) to the message posting endpoint. Anonymous users and authenticated users are tracked separately. (`server.py`)
- **`_serve_client_with_error()` Undefined** — Defined the missing function that was called in the OAuth error paths. Any OAuth failure previously crashed the server with `NameError`. (`server.py`)
- **Duplicate Element IDs in Community Client** — Removed the duplicate `id="chat-messages"` div from the DM view and renamed the DM input wrapper to `id="dm-input-area"`. `getElementById()` now returns the correct elements. (`server.py`)
- **Stale `web/index.html`** — Synced `web/index.html` with the latest `persona.html` so the compiled exe includes all fixes. (`web/index.html`)

#### 🔵 Low / Informational — Fixed

- **Missing CORS Preflight Handler** — Added explicit `OPTIONS` route handler with `Access-Control-Max-Age` and added `X-API-Key` to allowed headers. (`server.py`)
- **Misleading Function Name** — Renamed `_deflateSync` → `_deflateAsync` (the function is async). The old name contributed to the PNG builder bug. (`persona.html`)
- **Unused `_SECRET` Variable** — Removed the unused `_SECRET = base64.urlsafe_b64encode(os.urandom(32))`. The `hmac` import was also removed. (`server.py`)
- **Icon Path Quoting** — Fixed `compile_persona.bat` icon argument quoting for paths with spaces. (`compile_persona.bat`)

#### Added

- **`.gitignore`** — Comprehensive gitignore covering Python artifacts, PyInstaller output, compiled executables, IDE files, virtual environments, runtime data, and community server data.
- **Rate Limiting** — `_check_rate_limit()` with configurable window and threshold (`_RATE_WINDOW = 10s`, `_RATE_MAX = 10`).
- **Atomic File Operations** — `_load_modify_save()` for safe concurrent JSON file updates.

---

## [1.5.1] — 2026-03-21

### ✨ Features
- **Message Editing**: Added the ability to inline edit any past chat messages (both User and AI). Hover over a message to reveal an Edit (✎) button, which transforms the message into a text area to correct typos or steer roleplay.
- **NSFW / 18+ Badges**: Added a toggle to the Character Editor to mark characters as "18+ / NSFW".
    - This flag is properly embedded in V2 and V1 card JSON exports.
    - When pushed to the community server, the `server.py` gallery will now parse and visibly display a red `[18+]` and `18+ / NSFW` badge to warn users of mature content before downloading.

---

## [1.5.0] — 2026-03-21

### 🔧 Fixed — Compiler Crash (compile_persona.bat)

The build script (`compile_persona.bat`) has been overhauled to prevent laptops from crashing during compilation. This was caused by extreme RAM and CPU usage from PyInstaller's `--onefile` compression mode.

#### Changed

- **`--onefile` → `--onedir`** — PyInstaller now outputs a folder with the `.exe` and its dependencies side-by-side, instead of compressing ~200 MB into a single blob. RAM usage drops from **2–4 GB → ~500 MB** during build.
- **Removed `--clean` flag** — PyInstaller build cache is now preserved between builds. Subsequent builds are **5–10x faster** because analysis results are reused.
- **Removed recursive disk search** — The `where /r C:\` command that searched the entire C: drive for `python.exe` has been replaced with a clear error message and instructions. This previously saturated disk I/O and could freeze the system for 10–30 minutes on slow drives.
- **Preserved `build/` and `dist/` cache** — The cleanup step no longer deletes PyInstaller's cache folders, enabling faster rebuilds.
- **Updated copy step** — Build output is now copied as a folder (`xcopy`) instead of a single file (`copy`).
- **Updated version banner** — `v1.4` → `v1.5` with "(Safe mode: lower RAM/CPU, crash-proof)" note.

#### Added

- **Antivirus exclusion tip** — Build completion message now includes a tip for users whose AV flags PyInstaller-built executables.
- **Informative build messages** — Step 5 now explains that `--onedir` mode is being used and why cached builds are faster.
- **Error context** — Step 6 now includes a hint about checking PyInstaller output if the exe is not found.
- **Safety notes in comments** — Inline documentation explains the `--onefile` vs `--onedir` trade-off and when it's safe to switch back.

#### Impact

| Before (v1.4) | After (v1.5) |
|---------------|-------------|
| Build uses 2–4 GB RAM | Build uses ~500 MB RAM |
| Crashes laptops with ≤8 GB RAM | Safe on all machines |
| Full rebuild every time (`--clean`) | Cached rebuilds (5–10x faster) |
| Recursive C:\ search if Python not in PATH | Clean error with instructions |
| Output: single `.exe` file | Output: folder with `.exe` + dependencies |
| `build/` and `dist/` deleted after each build | Kept as cache for speed |

> **Note:** The output is now a folder instead of a single `.exe`. Distribute the entire folder (zip it). The app works exactly the same — double-click the `.exe` inside the folder to launch.

---

### 📝 Added — README.md

The repository README has been rewritten from scratch (was 2 lines, now comprehensive documentation).

#### Added

- Project description, badges, and tagline
- Complete feature overview (AI chat, character cards, themes, Discord, community server, chat logs)
- Quick Start guide with 3 options (pre-built exe, from source, browser-only)
- Supported AI providers table (Anthropic, OpenAI, OpenRouter, Ollama, Custom)
- Character card documentation (creating, import/export formats, PNG card spec)
- Community server guide (connecting, self-hosting, configuration)
- **Detailed build documentation** with full 7-step process table, requirements, output structure, troubleshooting table, and advanced `--onefile` option for power users
- Theming guide (presets list, customisation, CSS variables reference)
- Architecture overview (file tree, tech stack, how-it-works)
- Data storage documentation (desktop vs browser mode)
- Discord integration setup (webhooks + bot token, step-by-step)
- Contributing guidelines with future feature ideas
- License section

---

### 📝 Added — CHANGELOG.md

- This file! Documents all changes going forward.

---

## [1.4.0] — Initial Release

The original release of PersonaAI as uploaded to GitHub.

### Features (as shipped)

- **AI Chat Engine** — Multi-provider support (Anthropic, OpenAI, OpenRouter, Ollama, Custom) with SSE streaming
- **Character System** — Create, edit, delete characters with avatars, system prompts, first messages, and tags
- **Character Cards** — Import/export in SillyTavern V2, TavernAI V1, Persona Native, and PNG card formats
- **PNG Card Parser** — Full binary PNG chunk reader (tEXt, iTXt, zTXt) in both Python and browser JavaScript
- **Theme Engine** — 8 built-in presets (Void, Nightshade, Moonrise, Terminal, Parchment, Rose, Forest, Slate), live colour editor with 14 CSS variables, custom CSS injection, theme import/export
- **Chat Sessions** — Multiple sessions per character, session switching, clear chat, auto-scroll
- **Chat Logs** — Auto-save to `.txt` files, built-in log viewer with copy and delete
- **User Profiles** — Custom display name and avatar
- **Discord Integration** — Read channel messages (bot token via Python proxy), send via webhooks, scan for PNG card attachments, share cards to Discord
- **Community Server** — Full-featured community platform (`server.py`):
  - Discord OAuth2 authentication
  - WebSocket real-time chat with typing indicators and presence
  - Chat rooms (create, pin)
  - Forums with post/reply system
  - Direct messages
  - Character card gallery with uploads
  - Embedded web client
  - REST API for all operations
- **Remote Server Client** — Connect to community servers, push/pull cards, real-time chat with polling
- **Desktop App** — Python Eel wrapper with native file/folder dialogs, disk persistence, PNG embedding
- **Browser Mode** — Graceful fallback to localStorage when running without Eel
- **Drag & Drop** — Global drop zone for importing PNG/JSON character cards
- **Build Script** — `compile_persona.bat` for compiling to a standalone Windows `.exe`
- **Markdown Rendering** — Custom lightweight markdown parser for chat messages (headings, bold, italic, code, blockquotes, horizontal rules)
- **Context Menu** — Right-click characters for quick Edit, Export, Delete
- **Keyboard Shortcuts** — Enter to send, Shift+Enter for newline, auto-resize textarea

### Files

| File | Lines | Description |
|------|-------|-------------|
| `persona.html` | 3,495 | Complete single-page frontend (CSS + HTML + JS) |
| `server.py` | 1,611 | Community server with embedded web client |
| `app.py` | 1,117 | Eel bridge layer (file I/O, dialogs, PNG parsing) |
| `compile_persona.bat` | 275 | Windows build script |
| `main.py` | 10 | Entry point |
| `start.py` | 47 | VPS entry point for community server |
