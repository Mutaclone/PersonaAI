# ✦ PersonaAI

**AI roleplay chat app.** Create characters, talk to AI, share character cards, and chat with other users. Runs as a desktop app (Windows exe) or in any browser.

[![Python](https://img.shields.io/badge/Python-3.9+-3776ab?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Eel](https://img.shields.io/badge/Eel-Desktop_GUI-c8894a?style=for-the-badge)](https://github.com/python-eel/Eel)
[![License](https://img.shields.io/badge/License-MIT-88c470?style=for-the-badge)](LICENSE)

---

## How to Use

You have three options. Pick whichever works for you.

### Option 1 — Download the Exe (easiest)

1. Grab `persona.exe` from Releases
2. Double-click it
3. That's it. It opens a window. Go to Settings, paste your API key, start chatting.

The exe is fully self-contained. No installs, no folders, no dependencies. Just one file.

When you run it for the first time, it creates a few things next to itself:

| What | Where | Purpose |
| ---- | ----- | ------- |
| `settings.config` | Same folder as exe | Your saved settings (API key, provider, etc.) |
| `characters/` | Same folder as exe | Your character card files |
| `logs/` | Same folder as exe | Chat logs, sorted by character |
| `themes/` | Same folder as exe | Any custom themes you save |

### Option 2 — Run from Source

```bash
git clone https://github.com/Mutaclone/PersonaAI.git
cd PersonaAI
pip install eel Pillow
python main.py
```

This opens the same app window. You need Python 3.9+.

### Option 3 — Browser Only

Open `persona.html` in your browser. No Python needed. Everything works except file system stuff (no folder pickers, no saving to disk, no Discord message reading). Your data lives in the browser's IndexedDB instead.

---

## Setting Up Your AI Provider

PersonaAI doesn't come with an API key. You bring your own.

1. Open the app
2. Click **⚙ Settings** in the sidebar
3. Pick a provider from the dropdown
4. Paste your API key
5. Hit **Save Settings**

### Supported Providers

| Provider | What It Is | API Key? |
| -------- | ---------- | -------- |
| **Anthropic** | Claude models (claude-sonnet-4-20250514, etc.) | Yes |
| **OpenAI** | GPT models (gpt-4o, gpt-4o-mini, etc.) | Yes |
| **OpenRouter** | 100+ models through one API | Yes |
| **Ollama** | Run models locally on your machine — free, private, offline | No |
| **Custom** | Any OpenAI-compatible endpoint (LM Studio, text-gen-webui, etc.) | Depends |

The Base URL and Model fields auto-fill when you pick a provider. You usually just need to paste your key and save.

---

## Character Cards

Characters are the core of the app. Each one has a name, avatar, personality (system prompt), and an opening message.

### Creating a Character

Click the **+** button in the sidebar:

- **Name** — Display name
- **Avatar** — Upload an image, paste a URL, or leave blank (it'll show initials)
- **System Prompt** — Tell the AI how to act. Use `{{char}}` for the character's name and `{{user}}` for your name
- **First Message** — What the character says when you start a new chat
- **Tags** — Optional labels (fantasy, romance, sci-fi, etc.)

### Importing Cards

You can import characters from other apps. Just drag and drop a `.png` or `.json` file onto the window.

Supported formats:

- **SillyTavern V2 JSON** — Works with SillyTavern, Chub.ai, Agnai
- **TavernAI V1 JSON** — Older format, still supported
- **PNG Cards** — Character data embedded inside a PNG image (this is the standard across most AI chat apps)
- **Persona Native JSON** — The app's own format

### Exporting Cards

Click the edit button (✎) on a character → **Export Character Card**. You can export as JSON or PNG.

---

## Building the Exe

If you want to compile the app yourself into a `.exe`, here's how.

### What You Need

- **Python 3.9+** installed and added to PATH
- **8+ GB RAM** (the build compresses everything into one file, which uses 2-4 GB of memory)
- **Internet** on first run (to install dependencies automatically)

### How to Build

1. Make sure these files are in the same folder: `compile_persona.bat`, `main.py`, `app.py`, `server.py`, `persona.html`
2. **Drag `persona.html` onto `compile_persona.bat`**
3. Wait. First build takes 1-2 minutes. Subsequent builds are faster (cache).
4. When it's done, your `persona.exe` appears and Explorer opens to show it.

That's it. The output is **one single `.exe` file**. Everything — the Python runtime, the web UI, all dependencies — is packed inside it.

To give it to someone: just send them the exe. They double-click it and it works.

### What the Build Script Does

It runs 7 steps automatically. You don't need to do anything, but here's what happens:

1. **Finds Python** on your machine
2. **Installs dependencies** (`eel`, `pyinstaller`, `Pillow`) via pip — only on first run
3. **Finds or converts an icon** (looks for `icon.ico` or `icon.png`)
4. **Copies your HTML** into a `web/` folder for Eel to use
5. **Runs PyInstaller** to bundle everything into one exe
6. **Copies the exe** to the same folder as your HTML
7. **Cleans up** temp files (keeps cache for faster rebuilds)

### If the Build Fails

| Problem | Fix |
| ------- | --- |
| "Could not locate Python" | Install Python from [python.org](https://python.org) — make sure to check **"Add Python to PATH"** during setup |
| pip install failed | Check your internet. Try right-clicking the `.bat` → **Run as administrator** |
| PyInstaller failed | Temporarily disable your antivirus, then try again |
| Antivirus flags the exe | This is a [known false positive](https://github.com/pyinstaller/pyinstaller/issues/6754) with PyInstaller. Add an exclusion for the exe |
| Build crashes / out of memory | Your machine doesn't have enough RAM. Open `compile_persona.bat` in a text editor and change `--onefile` to `--onedir`. This makes a folder instead of a single exe, but uses way less memory (~500 MB) |

---

## Themes

The app comes with 8 themes: **Void** (default), **Nightshade**, **Moonrise**, **Terminal**, **Parchment**, **Rose**, **Forest**, and **Slate**.

To change themes:

1. Click **◑ Themes** in the sidebar
2. Pick a preset, or edit colours manually in the **Colors** tab
3. Write custom CSS in the **Custom CSS** tab if you want full control
4. Click **Apply & Save**

You can also save themes to a file and share them with others.

### CSS Variables

If you want to write custom CSS, these are the main variables:

```css
:root {
  --bg:           #0f0d10;   /* Page background */
  --surface:      #161419;   /* Sidebar, headers */
  --elevated:     #1d1a20;   /* Inputs, cards */
  --elevated2:    #242029;   /* Code blocks */
  --border:       #2c2830;   /* Borders */
  --border-light: #3c3840;   /* Light borders */
  --accent:       #c8894a;   /* Primary accent colour */
  --text:         #e4ddd3;   /* Main text */
  --text-muted:   #978e96;   /* Muted text */
  --text-dim:     #635e68;   /* Dim text */
  --red:          #c84a4a;   /* Errors, danger */
  --blue:         #4a8bc8;   /* User avatar accent */
  --user-msg-bg:  #172030;   /* User message bubble */
  --char-msg-bg:  #1a1720;   /* Character message bubble */
}
```

---

## Discord Integration

### Sending Messages (Webhooks)

1. In Discord: **Server Settings → Integrations → Webhooks → New Webhook**
2. Copy the webhook URL
3. In Persona: **⌘ Discord → Webhooks tab → Paste URL → Add Webhook**

### Reading Messages (Bot Token)

This lets the app read messages from a Discord channel. Desktop app only.

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create a new application → go to **Bot** → **Reset Token** → copy it
3. In Persona: **⌘ Discord → ⚙ Settings → Paste Bot Token**
4. Back in the developer portal: **OAuth2 → URL Generator** → check `bot` scope + `Read Message History` permission
5. Use the generated URL to invite the bot to your server
6. Right-click a channel in Discord → **Copy Channel ID** → paste into Persona

---

## Community Server

The app has a built-in community feature for chatting with other users and sharing character cards.

### Using the Public Server

Click **☁ Remote Server** in the sidebar. You can:

- Browse and download characters from the community gallery
- Chat in real-time with other Persona users
- Push your characters to the gallery

### Running Your Own Server

If you want to self-host:

```bash
pip install bottle gevent gevent-websocket
```

Edit `start.py` with your config:

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

Then run `python start.py`. The server supports:

- Discord OAuth2 login
- Real-time WebSocket chat with typing indicators
- Chat rooms (create, pin)
- Forums with posts and replies
- Direct messages
- Character card gallery with uploads
- Full REST API

---

## Project Structure

```
PersonaAI/
├── main.py                 ← Entry point. 10 lines. Just starts the app.
├── app.py                  ← Backend bridge. File I/O, dialogs, PNG parsing.
├── server.py               ← Community server. WebSocket, OAuth, chat, gallery.
├── persona.html            ← The entire frontend. Single-file SPA.
├── compile_persona.bat     ← Build script. Drag HTML onto it → get exe.
├── start.py                ← Entry point for running the community server on a VPS.
├── web/
│   └── index.html          ← Copy of persona.html (used by the desktop app engine)
└── community/
    └── rooms.json          ← Default chat room config
```

### How It Works

1. `main.py` starts the app by calling `app.start()`
2. `app.py` uses [Eel](https://github.com/python-eel/Eel) to open a Chromium window pointing to `web/index.html`
3. `persona.html` is the entire UI — all HTML, CSS, and JavaScript in one file
4. Python functions marked with `@eel.expose` can be called from JavaScript (this is how the UI talks to the file system)
5. If you open `persona.html` directly in a browser (no Python), it falls back to browser storage instead of disk

### Tech Stack

| What | Technology |
| ---- | ---------- |
| Desktop window | Python Eel (Chromium wrapper) |
| Backend | Python 3.9+ (standard library + Pillow) |
| Frontend | Vanilla HTML, CSS, JavaScript. No frameworks. |
| Community server | Bottle + gevent + gevent-websocket |
| Fonts | Cinzel, Crimson Pro, JetBrains Mono |
| Build | PyInstaller |

---

## Security

The codebase went through a full security audit in v1.5.2. Here's what's in place:

- **Path traversal protection** — All file operations check that paths stay inside their expected folders
- **XSS protection** — User content is escaped before being injected into the page
- **Rate limiting** — Community server limits messages per user to prevent spam
- **WebSocket auth** — Unauthenticated connections are rejected
- **Secure cookies** — OAuth cookies use `HttpOnly`, `SameSite=Lax`, and `Secure` flags
- **No hardcoded secrets** — You bring your own API key

See [CHANGELOG.md](CHANGELOG.md) for the full list of 22 fixes.

---

## Contributing

This is a hobby project. Contributions are welcome.

1. Fork the repo
2. Make a branch (`git checkout -b feature/cool-thing`)
3. Commit and push
4. Open a PR

### Ideas

- [ ] Mobile-responsive layout
- [ ] Group chat (multiple characters in one session)
- [x] Message editing and deletion *(done in v1.5.1)*
- [ ] Image generation
- [ ] Voice input/output (TTS/STT)
- [ ] Lorebook / World Info
- [ ] Greeting variations

---

## License

MIT — do whatever you want with it.

---

<div align="center">

**Made with ✦ by [Mutaclone](https://github.com/Mutaclone)**

*If you enjoy Persona, give it a ⭐ on GitHub!*

</div>
