# Changelog

All notable changes to PersonaAI are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
