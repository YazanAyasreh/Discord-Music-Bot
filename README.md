# 🎵 MusicNot Bot

> A feature-rich Discord music bot built with **discord.py** and **yt-dlp** — stream any song from YouTube directly in your voice channel, controlled entirely through a sleek emoji-button panel.

---

## ✨ Features

| Category | Details |
|---|---|
| 🎧 **Playback** | Play by song name or YouTube URL, pause, resume, skip, restart, seek back |
| 📋 **Queue** | Full queue management with history, shuffle, and up to unlimited tracks |
| 🔁 **Loop Modes** | Off → Loop Track → Loop Queue, cycle with one button |
| 🔀 **Shuffle** | Randomise the queue on the fly |
| 🤖 **Autoplay** | Auto-suggests and queues related tracks when the queue runs out |
| 💾 **Playlists** | Save, load, list, and delete named playlists per server |
| 🎛️ **Dashboard Panel** | Persistent 3 × 5 custom-icon button panel — no commands needed |
| 🔊 **Volume** | Per-server volume control (1 – 200 %) |
| 📡 **Voice Status** | Live song title shown in the voice channel status bar |
| ❤️ **Liked Songs** | Like any track from the panel to save it to a Liked playlist |

---

## 🖼️ Panel Layout

The `/panel` command posts a persistent control panel to any channel.  
All buttons use **custom icons** uploaded as application emojis.

```
Row 0 │  ▶  Play    ⏮  Prev    ⏸  Pause    ⏭  Skip    📋  Queue
Row 1 │  🔄  Restart  ⏪  Back   ❤️  Like    ⏩  FF      🔊  Volume
Row 2 │  🎧  Playlist  🔀  Shuffle  ⏭⏭  Autoplay  🔁  Loop  ⤢  Help
```

Click **▶ Play** while nothing is queued and a modal opens for you to type a search or URL.  
The panel is **persistent** — it survives bot restarts automatically.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- A Discord bot application with the **Message Content** intent enabled
- FFmpeg available in `PATH`

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/YazanAyasreh/Discord-Music-Bot
cd Discord-Music-Bot

# 2. Install all dependencies (one command)
pip install -r requirements.txt

# 3. Set your bot token

# On Replit → add DISCORD_TOKEN as a Secret (Secrets tab in the sidebar)

# On Linux / macOS:
export DISCORD_TOKEN="your-token-here"

# On Windows PowerShell:
$env:DISCORD_TOKEN = "your-token-here"

# On Windows Command Prompt (cmd):
set DISCORD_TOKEN=your-token-here

# 4. Run the bot
python3 bot.py
```

On first run the bot will **automatically crop and upload** the 15 custom button icons as application emojis — subsequent starts reuse the cached IDs.

---

## 🎮 Slash Commands

### `/music` — Playback controls

| Command | Description |
|---|---|
| `/music play <query>` | Play a song by name or YouTube URL |
| `/music pause` | Pause playback |
| `/music resume` | Resume a paused track |
| `/music skip` | Skip to the next track |
| `/music stop` | Stop and disconnect the bot |
| `/music queue` | Show the current queue |
| `/music shuffle` | Toggle shuffle mode |
| `/music loop <mode>` | Set loop mode: `off` / `track` / `queue` |
| `/music volume <1-200>` | Set playback volume |
| `/music autoplay` | Toggle autoplay (auto-queues related tracks) |
| `/music panel` | Post the dashboard control panel |

### `/playlist` — Saved playlists

| Command | Description |
|---|---|
| `/playlist save <name>` | Save the current queue as a named playlist |
| `/playlist load <name>` | Load a saved playlist into the queue |
| `/playlist list` | List all saved playlists for this server |
| `/playlist delete <name>` | Delete a saved playlist |

### Standalone commands

| Command | Description |
|---|---|
| `/panel` | Post the dashboard panel (alias) |
| `/nowplaying` | Show the current track embed |
| `/ping` | Check bot latency |
| `/help` | Show the full help embed |

---

## ⚙️ Configuration

All configuration is handled through environment variables / Replit Secrets:

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ Yes | Your Discord bot token |

No database or external services required — playlists are stored in-memory per server session.

---

## 🛠️ Tech Stack

| Library | Purpose |
|---|---|
| [discord.py 2.7](https://discordpy.readthedocs.io/) | Discord API wrapper + UI components |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | YouTube audio extraction |
| [FFmpeg](https://ffmpeg.org/) | Audio streaming & encoding |
| [Pillow](https://python-pillow.org/) | Icon image processing on startup |

---

## 📁 Project Structure

```
Discord-Music-Bot/
├── bot.py              # Main bot file — all logic lives here
├── requirements.txt    # All Python dependencies
├── bot_icons/          # Cropped PNG icons (auto-generated on first run)
│   ├── p_play.png
│   ├── p_pause.png
│   └── ...             # 15 icons total
└── attached_assets/    # Source icon sheet image
```

---

## 🔐 Permissions Required

When inviting the bot to your server, ensure it has:

- `Send Messages`
- `Embed Links`
- `Connect` (voice)
- `Speak` (voice)
- `Use Application Commands`
- `Manage Messages` *(optional — for panel cleanup)*

**OAuth2 Invite URL scope:** `bot` + `applications.commands`

---

## 📝 License

MIT — free to use, modify, and distribute.

---

<div align="center">
  <sub>Built with ❤️ using discord.py · Powered by yt-dlp</sub>
</div>
