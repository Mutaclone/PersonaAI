<div align="center">

# ✦ PersonaAI

**AI Roleplay Chat — Desktop & Browser**

Create characters, chat with AI, share cards, and connect with others.

[![Python](https://img.shields.io/badge/Python-3.9+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Eel](https://img.shields.io/badge/Eel-Desktop_GUI-c8894a?style=for-the-badge)](https://github.com/python-eel/Eel)
[![License](https://img.shields.io/badge/License-MIT-88c470?style=for-the-badge)](LICENSE)

*Built for fun. Powered by your favourite AI.*

---

**[Features](#-features) · [Quick Start](#-quick-start) · [Providers](#-supported-providers) · [Character Cards](#-character-cards) · [Community Server](#-community-server) · [Building](#%EF%B8%8F-building-the-exe) · [Theming](#-theming) · [Architecture](#-architecture)**

</div>

---

## ✨ Features

### 🤖 AI Chat
- **Multi-provider support** — Anthropic (Claude), OpenAI (GPT), OpenRouter, Ollama (local), or any OpenAI-compatible endpoint
- **Streaming responses** — Real-time token-by-token output with a blinking cursor
- **System prompts** — Character-specific personalities with `{{char}}` and `{{user}}` template placeholders
- **Multiple sessions** — Run separate chat sessions per character, switch between them freely
- **Regenerate & Stop** — Re-roll any AI response or cancel mid-stream
- **Configurable parameters** — Temperature, max tokens, context window size

### 🎴 Character Cards
- **Import/Export** — Full compatibility with [SillyTavern](https://github.com/SillyTavern/SillyTavern), [Chub.ai](https://chub.ai), TavernAI, OpenCharacters, and Agnai
- **PNG Card Format** — Import and export character data embedded inside PNG portrait images (tEXt/iTXt/zTXt chunks)
- **Drag & Drop** — Drop a `.png` or `.json` card anywhere on the window to import
- **Bulk operations** — Export all characters as JSON, import from JSON backup
- **Duplicate detection** — Warns before overwriting an existing character

### 🎨 Themes & Customisation
- **8 built-in themes** — Void, Nightshade, Moonrise, Terminal, Parchment, Rose, Forest, Slate
- **Live colour editor** — 14 CSS variables with real-time colour pickers
- **Custom CSS** — Inject your own styles for full control
- **Save & Share** — Export themes as JSON, import from others, save to a themes folder

### 💬 Discord Integration
- **Read messages** — Connect a Discord bot token to read channel history (desktop app only)
- **Send via Webhook** — Post messages through Discord webhooks from the chat panel
- **Card browser** — Scan a Discord channel for PNG card attachments and import them
- **Share cards** — Upload character cards as PNG files directly to Discord

### 🌐 Community Server
- **Real-time chat** — WebSocket-powered rooms with typing indicators and presence
- **Discord OAuth** — Log in with your Discord account
- **Forums** — Post and reply system per room
- **Direct messages** — Private conversations between authenticated users
- **Card gallery** — Browse, upload, and download character cards from the community
- **Self-hostable** — Run your own community server on a VPS

### 📋 Chat Logs
- **Auto-save** — Chat sessions are automatically saved as `.txt` files after each AI reply
- **Log viewer** — Built-in browser for reading, copying, and deleting saved logs
- **Organised by character** — Logs are sorted into sub-folders by character name

---

## 🚀 Quick Start

### Option 1: Run the Pre-built Exe (Windows)

1. Download **`persona.exe`** (or the output folder if built with `--onedir`)
2. Double-click to launch
3. Open **Settings** → add your API key → start chatting!

### Option 2: Run from Source

```bash
# Clone the repo
git clone https://github.com/Mutaclone/PersonaAI.git
cd PersonaAI

# Install dependencies
pip install eel Pillow

# Run
python main.py
```

### Option 3: Browser Only (No Install)

Open `persona.html` directly in your browser. Works without Python — you just won't have file system access (no folder pickers, no disk saves, no Discord message reading).

> **Note:** When running in the browser, your data is stored in **IndexedDB** (primary) with a lightweight `localStorage` fallback. The desktop app additionally saves settings and characters to disk.

---

## 🔌 Supported Providers

| Provider | Base URL | Auth | Notes |
|----------|----------|------|-------|
| **Anthropic** | `api.anthropic.com` | API Key | Claude models (claude-sonnet-4-20250514, etc.) |
| **OpenAI** | `api.openai.com` | API Key | GPT models (gpt-4o, gpt-4o-mini, etc.) |
| **OpenRouter** | `openrouter.ai/api` | API Key | Access 100+ models through one API |
| **Ollama** | `localhost:11434` | None | Run models locally — free, private, offline |
| **Custom** | Any URL | API Key | Any OpenAI-compatible endpoint (LM Studio, text-gen-webui, etc.) |

### Setting Up

1. Click **⚙ Settings** in the sidebar
2. Pick your **Provider** from the dropdown
3. Paste your **API Key** (not needed for Ollama)
4. The **Base URL** and **Model** auto-fill with sensible defaults
5. Click **Save Settings**

---

## 🎴 Character Cards

PersonaAI implements the community-standard character card format used across the AI roleplay ecosystem.

### Creating a Character

Click the **+** button in the sidebar or the **New Character** button:

- **Name** — The character's display name
- **Avatar** — Upload an image, paste a URL, or leave blank for initials
- **System Prompt** — The character's personality and behaviour instructions. Use `{{char}}` and `{{user}}` as placeholders
- **First Message** — The opening line when a new chat starts
- **Tags** — Comma-separated tags (fantasy, romance, sci-fi, etc.)

### Import Formats

| Format | Extension | Source |
|--------|-----------|--------|
| SillyTavern V2 | `.json` | SillyTavern, Chub.ai, Agnai |
| TavernAI V1 | `.json` | TavernAI, older SillyTavern |
| PNG Card | `.png` | Any app that embeds `chara` data in PNG chunks |
| Persona Native | `.json` | PersonaAI's own export format |

### Export Formats

Export from the character editor (✎ button) → **Export Character Card**:

- **SillyTavern V2 JSON** — Most widely compatible
- **TavernAI V1 JSON** — For older apps
- **Persona Native JSON** — Includes all fields
- **PNG Card** — Portrait image with embedded JSON (desktop app only)

---

## 🌐 Community Server

PersonaAI includes a full community server (`server.py`) for sharing cards and chatting in real-time.

### Connecting to the Public Server

The app comes pre-configured to connect to `persona.dragonsphere.io`. Click **☁ Remote Server** in the sidebar to:

- Browse and download community character cards
- Chat in real-time with other Persona users
- Push your characters to the community gallery

### Self-Hosting

Run your own community server:

```bash
# Install additional dependencies
pip install bottle gevent gevent-websocket

# Edit start.py with your config (port, Discord OAuth credentials, etc.)

# Run the server
python start.py
```

#### Configuration (`start.py`)

```python
server.configure({
    'port':                   8765,
    'discord_client_id':      'YOUR_CLIENT_ID',
    'discord_client_secret':  'YOUR_CLIENT_SECRET',
    'redirect_uri':           'https://yourdomain.com/auth/callback',
    'server_name':            'My Community',
    'allow_uploads':          True,
    'chars_folder':           './cards',
    'uploads_folder':         './community/uploads',
})
```

#### Features
- **Discord OAuth2** login
- **WebSocket** real-time messaging with typing indicators
- **Chat rooms** (create new rooms, pin rooms)
- **Forums** with post/reply system
- **Direct Messages** between authenticated users
- **Card gallery** with upload support
- **REST API** for all operations

---

## 🛠️ Building the Exe

Compile PersonaAI into a standalone Windows application.

### How to Build

1. Make sure **Python 3.9+** is installed and **added to PATH**
2. Place these files in the same folder: `compile_persona.bat`, `main.py`, `app.py`, `server.py`
3. **Drag `persona.html` onto `compile_persona.bat`**
4. Wait for the build to complete
5. A folder with your `.exe` will open in Explorer when done

### What the Compiler Does (7 Steps)

The build script runs these steps automatically:

| Step | What It Does | Time |
|------|-------------|------|
| **[1/7] Locate Python** | Finds your Python installation in PATH or standard folders | Instant |
| **[2/7] Install dependencies** | Installs `eel`, `pyinstaller`, `Pillow` via pip (first run only) | 30-60s first run |
| **[3/7] Locate icon** | Finds `icon.ico` or converts `icon.png` to `.ico` using Pillow | Instant |
| **[4/7] Copy HTML** | Copies your HTML into the `web/` folder for Eel | Instant |
| **[5/7] PyInstaller** | Bundles Python + dependencies into a standalone app | 30-90s |
| **[6/7] Copy output** | Copies the built folder to the same location as your HTML | Instant |
| **[7/7] Clean up** | Removes temporary files (keeps cache for faster rebuilds) | Instant |

> **Tip:** The first build takes longest. Subsequent builds reuse the PyInstaller cache and are **5-10x faster**.

### Build Requirements

- **Python 3.9+** — must be added to PATH during installation
- **Internet** — needed on first run to install dependencies
- **~500 MB RAM** — the build is designed to be safe on any machine
- Dependencies are installed automatically: `eel`, `pyinstaller`, `Pillow`

### Build Output

The compiler uses `--onedir` mode (v1.5), which produces a **folder** containing the `.exe` and its dependencies:

```
persona/
├── persona.exe          ← double-click to launch
├── _internal/           ← Python runtime + dependencies
└── web/
    └── index.html       ← the UI
```

> **To distribute:** Zip the entire `persona\` folder and share it. The recipient just unzips and double-clicks `persona.exe`.

### Troubleshooting

| Problem | Solution |
|---------|----------|
| `[ERROR] Could not locate Python` | Install Python from [python.org](https://python.org) — check **"Add Python to PATH"** during setup |
| `pip install failed` | Check your internet connection, or right-click the `.bat` → **Run as administrator** |
| `PyInstaller failed` | Temporarily disable antivirus, then retry |
| Antivirus flags the `.exe` | This is a [known false positive](https://github.com/pyinstaller/pyinstaller/issues/6754) with PyInstaller. Add an exclusion for the output folder |
| Build is slow | First build takes 1-2 minutes. Subsequent builds use cache and are much faster |

### Advanced: Single-File Exe

If you prefer a single `.exe` instead of a folder, you can edit `compile_persona.bat` and change `--onedir` back to `--onefile`. **Only do this on machines with 8+ GB RAM** — the compression step uses 2-4 GB of memory and can crash low-spec machines.

---

## 🎨 Theming

### Built-in Presets

| Theme | Style |
|-------|-------|
| **Void** | Dark with warm gold accent (default) |
| **Nightshade** | Deep purple, lavender accent |
| **Moonrise** | Navy blue, cool blue accent |
| **Terminal** | Black with neon green — hacker vibes |
| **Parchment** | Light mode, parchment paper aesthetic |
| **Rose** | Dark with soft pink accent |
| **Forest** | Deep green, natural tones |
| **Slate** | GitHub-style dark theme |

### Custom Themes

1. Click **◑ Themes** in the sidebar
2. Pick a preset or edit individual colours in the **Colors** tab
3. Write additional CSS in the **Custom CSS** tab
4. Click **Apply & Save**

### Theme Files

Themes can be saved to and loaded from a themes folder:
- **Save:** Enter a name → click 💾 Save to Folder
- **Load:** Click any saved theme in the **Saved** tab
- **Export/Import:** Download/upload theme `.json` files

### CSS Variables

```css
:root {
  --bg:           #0f0d10;   /* Page background */
  --surface:      #161419;   /* Sidebar, headers */
  --elevated:     #1d1a20;   /* Inputs, cards */
  --elevated2:    #242029;   /* Code blocks, elevated+ */
  --border:       #2c2830;   /* Borders */
  --border-light: #3c3840;   /* Light borders */
  --accent:       #c8894a;   /* Primary accent */
  --text:         #e4ddd3;   /* Primary text */
  --text-muted:   #978e96;   /* Muted text */
  --text-dim:     #635e68;   /* Dim text */
  --red:          #c84a4a;   /* Danger / errors */
  --blue:         #4a8bc8;   /* User avatar accent */
  --user-msg-bg:  #172030;   /* User message bubble */
  --char-msg-bg:  #1a1720;   /* Character message bubble */
}
```

---

## 🏗 Architecture

PersonaAI is built with just 4 core files:

```
PersonaAI/
├── main.py                 ← Entry point (10 lines)
├── app.py                  ← Eel bridge: file I/O, dialogs, PNG parsing (~1,150 lines)
├── server.py               ← Community server: WebSocket, OAuth, API (~1,725 lines)
├── persona.html            ← Complete frontend SPA (~6,280 lines)
├── compile_persona.bat     ← Build script → .exe
├── start.py                ← VPS entry point for community server
├── .gitignore              ← Git ignore rules
├── CHANGELOG.md            ← Version history
├── web/
│   └── index.html          ← Copy of persona.html (used by Eel)
└── community/
    └── rooms.json          ← Default chat room config
```

### How It Works

1. **`main.py`** imports `app` and calls `app.start()`
2. **`app.py`** initialises [Eel](https://github.com/python-eel/Eel) which opens a Chromium window pointing to `web/index.html`
3. **`persona.html`** is a single-file SPA — all CSS, HTML, and JavaScript are inline
4. Python functions decorated with `@eel.expose` are callable from JavaScript via `eel.functionName()()`
5. When running in a browser (no Eel), the app gracefully falls back to `localStorage` and browser APIs

### Technology Stack

| Layer | Technology |
|-------|-----------|
| **Desktop GUI** | Python Eel (Chromium wrapper) |
| **Backend** | Python 3.9+ (stdlib + Pillow) |
| **Frontend** | Vanilla HTML/CSS/JS (zero frameworks) |
| **Community Server** | Bottle + gevent + gevent-websocket |
| **Fonts** | Cinzel (headings), Crimson Pro (body), JetBrains Mono (UI/code) |
| **Build** | PyInstaller |

---

## 📂 Data Storage

### Desktop App

| Data | Location | Format |
|------|----------|--------|
| Settings | `settings.config` (next to exe) | JSON |
| Characters | `characters/` folder | Individual `.json` card files |
| Chat logs | `logs/` folder | `.txt` files organised by character |
| Themes | `themes/` folder | `.json` theme files |

### Browser Mode

Data is stored in **IndexedDB** (primary, no size limit) with a lightweight `localStorage` cache as fallback.

> **Migration:** Users upgrading from v1.5.1 or earlier will have their `localStorage` data automatically migrated to IndexedDB on first load. No manual action is needed.

---

## 🔑 Discord Integration Setup

### Webhooks (Send Messages)

1. In your Discord server: **Server Settings → Integrations → Webhooks → New Webhook**
2. Copy the webhook URL
3. In Persona: **⌘ Discord → Webhooks tab → Paste URL → Add Webhook**

### Bot Token (Read Messages)

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. **New Application → Bot → Reset Token → Copy**
3. In Persona: **⌘ Discord → ⚙ Settings → Paste Bot Token**
4. In the developer portal: **OAuth2 → URL Generator → select `bot` scope + `Read Message History` permission**
5. Use the generated URL to invite the bot to your server
6. Right-click a channel in Discord → **Copy Channel ID** → paste into Persona

---

## 🤝 Contributing

This project was built for fun! Contributions are welcome:

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/cool-thing`)
3. Commit your changes
4. Push and open a Pull Request

### Ideas for Contributions

- [ ] Mobile-responsive layout
- [ ] Group chat (multiple characters in one session)
- [x] Message editing and deletion *(added in v1.5.1)*
- [ ] Image generation integration
- [ ] Voice input/output (TTS/STT)
- [ ] Lorebook / World Info support
- [ ] Character Greeting variations

---

## 🔒 Security

PersonaAI v1.5.2 underwent a comprehensive security audit. Key protections:

- **Path Traversal Prevention** — All file I/O functions validate that resolved paths stay within their expected directories
- **XSS Protection** — All user-controlled content is HTML-escaped before DOM insertion
- **Rate Limiting** — Community server endpoints enforce per-user/IP message rate limits
- **WebSocket Authentication** — Unauthenticated WebSocket connections are rejected
- **Secure Cookies** — OAuth cookies use `HttpOnly`, `SameSite=Lax`, and conditional `Secure` flags
- **No Hardcoded Secrets** — API keys must be configured by the user

See the [CHANGELOG](CHANGELOG.md) for full details on all 22 fixes.

---

## 📄 License

MIT — do whatever you want with it.

---

<div align="center">

**Made with ✦ by [Mutaclone](https://github.com/Mutaclone)**

*If you enjoy Persona, give it a ⭐ on GitHub!*

</div>
