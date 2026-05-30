import asyncio
import logging
import os
import random
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("musicbot")

# ── PALETTE ────────────────────────────────────────────────────────────────────
BRAND       = 0x5865F2   # Discord blurple
SUCCESS     = 0x57F287   # green
WARNING     = 0xFEE75C   # yellow
ERROR       = 0xED4245   # red
NOW_PLAYING = 0xEB459E   # pink
QUEUE_COLOR = 0x5865F2
INFO_COLOR  = 0x4F545C   # grey

VOICE_STATUS_MAX_LEN = 500
MAX_VOLUME = 2.0

YTDL_OPTIONS = {
    "format": "bestaudio[acodec!=none]/bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android_vr", "android", "web"],
        }
    },
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -loglevel error",
}


# ── ENUMS & DATACLASSES ────────────────────────────────────────────────────────
class LoopMode(str, Enum):
    OFF   = "off"
    TRACK = "track"
    QUEUE = "queue"


LOOP_EMOJI = {LoopMode.OFF: "➡️", LoopMode.TRACK: "🔂", LoopMode.QUEUE: "🔁"}


@dataclass
class Track:
    title: str
    webpage_url: str
    stream_url: str
    thumbnail: Optional[str] = None
    duration: Optional[int] = None
    uploader: Optional[str] = None
    requester_id: int = 0

    @property
    def duration_text(self) -> str:
        if not self.duration:
            return "Live"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class GuildMusicState:
    queue: list[Track] = field(default_factory=list)
    now_playing: Optional[Track] = None
    loop_mode: LoopMode = LoopMode.OFF
    shuffle: bool = False
    volume: float = 0.5
    panel_message: Optional[discord.Message] = None
    dashboard_message: Optional[discord.Message] = None
    text_channel_id: Optional[int] = None
    playback_started_at: Optional[float] = None
    autoplay: bool = False
    autoplay_history: list[str] = field(default_factory=list)
    play_history: list[Track] = field(default_factory=list)


# ── HELPERS ────────────────────────────────────────────────────────────────────
def extract_youtube_id(url: str) -> Optional[str]:
    patterns = (
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([\w-]{11})",
        r"youtube\.com/shorts/([\w-]{11})",
    )
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def resolve_thumbnail(info: dict, webpage_url: str) -> Optional[str]:
    t = info.get("thumbnail")
    if t:
        return t
    thumbs = info.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url") or thumbs[0].get("url")
    vid = info.get("id") or extract_youtube_id(webpage_url)
    if vid:
        return f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
    return None


def resolve_stream_url(info: dict) -> str:
    url = info.get("url")
    if url:
        return url
    formats = info.get("formats") or []
    candidates = [f for f in formats if f.get("url") and f.get("acodec") not in (None, "none")]
    if not candidates:
        raise ValueError("No playable audio stream found. Run: pip install -U yt-dlp")
    return max(candidates, key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0))["url"]


def percent_to_volume(p: int) -> float:
    return min(MAX_VOLUME, max(0.0, p / 100))


def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "—"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def progress_bar(elapsed: float, total: Optional[int], size: int = 15) -> str:
    if not total or total <= 0:
        return "▬" * size + " `Live`"
    ratio = max(0.0, min(1.0, elapsed / total))
    filled = int(size * ratio)
    bar = "━" * filled + "⬤" + "─" * (size - filled)
    pct = int(ratio * 100)
    return f"`{bar}` {pct}%"


def extract_audio(search_or_url: str) -> Track:
    with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
        if search_or_url.startswith(("http://", "https://")):
            info = ydl.extract_info(search_or_url, download=False)
        else:
            info = ydl.extract_info(f"ytsearch:{search_or_url}", download=False)["entries"][0]
    webpage_url = info.get("webpage_url") or info.get("original_url") or search_or_url
    return Track(
        title=info.get("title", "Unknown"),
        webpage_url=webpage_url,
        stream_url=resolve_stream_url(info),
        thumbnail=resolve_thumbnail(info, webpage_url),
        duration=info.get("duration"),
        uploader=info.get("uploader") or info.get("channel"),
    )


def fetch_autoplay_track(finished: Track, history: list[str]) -> Track:
    video_id = extract_youtube_id(finished.webpage_url)
    if not video_id:
        raise ValueError("Autoplay requires a YouTube track.")
    history_set = set(history)
    radio_url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"
    opts = {**YTDL_OPTIONS, "noplaylist": False, "quiet": True, "playlistend": 25, "extract_flat": "in_playlist"}
    candidates: list[str] = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        data = ydl.extract_info(radio_url, download=False)
    for entry in data.get("entries") or []:
        if not entry:
            continue
        page_url = entry.get("webpage_url") or entry.get("url")
        entry_id = entry.get("id") or extract_youtube_id(page_url or "")
        if entry_id and not page_url:
            page_url = f"https://www.youtube.com/watch?v={entry_id}"
        if not page_url or page_url in history_set or entry_id == video_id:
            continue
        candidates.append(page_url)
    if not candidates:
        return extract_audio(f"{finished.uploader or finished.title} similar songs")
    return extract_audio(random.choice(candidates))


# ── EMBED BUILDERS ─────────────────────────────────────────────────────────────
def _footer(embed: discord.Embed, guild_name: str = "") -> discord.Embed:
    embed.set_footer(
        text=f"🎵 Rhythm  {'• ' + guild_name if guild_name else ''}",
        icon_url="https://cdn.discordapp.com/emojis/1304376706498506792.gif",
    )
    return embed


def base_embed(title: str, description: str = "", *, color: int = BRAND) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=color)
    e.set_footer(text="🎵 Rhythm • Advanced Music Bot")
    return e


def error_embed(msg: str) -> discord.Embed:
    e = discord.Embed(title="❌  Something went wrong", description=msg, color=ERROR)
    e.set_footer(text="🎵 Rhythm")
    return e


def success_embed(title: str, msg: str) -> discord.Embed:
    e = discord.Embed(title=f"✅  {title}", description=msg, color=SUCCESS)
    e.set_footer(text="🎵 Rhythm")
    return e


def warning_embed(title: str, msg: str) -> discord.Embed:
    e = discord.Embed(title=f"⚠️  {title}", description=msg, color=WARNING)
    e.set_footer(text="🎵 Rhythm")
    return e


def build_now_playing_embed(
    guild: discord.Guild,
    state: "GuildMusicState",
    *,
    status: str = "Playing",
) -> discord.Embed:
    track = state.now_playing
    vc = guild.voice_client

    if not track:
        e = discord.Embed(
            title="🎵  Nothing is playing",
            description="Use `/music play` or the **▶️** button to start.",
            color=INFO_COLOR,
        )
        _footer(e, guild.name)
        return e

    elapsed = 0.0
    if state.playback_started_at and vc and (vc.is_playing() or vc.is_paused()):
        elapsed = asyncio.get_event_loop().time() - state.playback_started_at
        if vc.is_paused():
            status = "Paused"

    bar = progress_bar(elapsed, track.duration)
    elapsed_text = format_duration(int(elapsed))
    total_text = track.duration_text
    loop_em = LOOP_EMOJI[state.loop_mode]

    e = discord.Embed(
        title="",
        description=(
            f"### [{track.title}]({track.webpage_url})\n"
            f"**{status}**  •  `{elapsed_text}` / `{total_text}`\n\n"
            f"{bar}"
        ),
        color=NOW_PLAYING,
    )

    # Metadata row
    e.add_field(name="🔊 Volume",  value=f"`{int(state.volume * 100)}%`", inline=True)
    e.add_field(name="Loop",       value=f"{loop_em} `{state.loop_mode.value}`", inline=True)
    e.add_field(name="🔀 Shuffle", value=f"`{'on' if state.shuffle else 'off'}`", inline=True)

    if track.uploader:
        e.add_field(name="📺 Channel", value=track.uploader, inline=True)
    if track.requester_id:
        e.add_field(name="👤 Requested by", value=f"<@{track.requester_id}>", inline=True)

    queue_val = f"`{len(state.queue)}` track(s) in queue"
    if state.autoplay:
        queue_val += "  •  🔂 Autoplay **on**"
    e.add_field(name="📋 Queue", value=queue_val, inline=False)

    if track.thumbnail:
        e.set_thumbnail(url=track.thumbnail)

    _footer(e, guild.name)
    return e


def build_queue_embed(guild_id: int, state: "GuildMusicState") -> discord.Embed:
    e = discord.Embed(title="📋  Queue", color=QUEUE_COLOR)

    if state.now_playing:
        e.add_field(
            name="▶️  Now Playing",
            value=f"[{state.now_playing.title}]({state.now_playing.webpage_url})  `{state.now_playing.duration_text}`",
            inline=False,
        )
        if state.now_playing.thumbnail:
            e.set_thumbnail(url=state.now_playing.thumbnail)

    if not state.queue:
        e.add_field(name="Up Next", value="*Queue is empty — add a track with `/music play`*", inline=False)
    else:
        lines = []
        total_dur = 0
        for i, t in enumerate(state.queue[:10], 1):
            lines.append(f"`{i}.`  **{t.title}**  `{t.duration_text}`")
            total_dur += t.duration or 0
        if len(state.queue) > 10:
            lines.append(f"*…and {len(state.queue) - 10} more*")
        e.add_field(name=f"Up Next  ({len(state.queue)} tracks)", value="\n".join(lines), inline=False)
        if total_dur:
            e.add_field(name="⏱️ Total remaining", value=format_duration(total_dur), inline=True)

    e.add_field(name="Loop",      value=f"{LOOP_EMOJI[state.loop_mode]} `{state.loop_mode.value}`", inline=True)
    e.add_field(name="Shuffle",   value=f"`{'on' if state.shuffle else 'off'}`", inline=True)
    e.set_footer(text="🎵 Rhythm")
    return e


def build_dashboard_embed(guild: discord.Guild, state: "GuildMusicState") -> discord.Embed:
    e = discord.Embed(
        description="Click the button, and any empty bot will connect to your channel without any commands - it is managed through this panel.",
        color=BRAND,
    )
    _footer(e, guild.name)
    return e


def build_help_embed() -> discord.Embed:
    e = discord.Embed(
        title="🛟  Rhythm — Command Guide",
        description="All commands are slash commands. Type `/` to see autocomplete.",
        color=BRAND,
    )
    e.add_field(
        name="🎵 Playback",
        value=(
            "`/music play <query>` — Play or queue a track\n"
            "`/music pause` — Pause playback\n"
            "`/music resume` — Resume playback\n"
            "`/music skip` — Skip current track\n"
            "`/music stop` — Stop & disconnect\n"
        ),
        inline=False,
    )
    e.add_field(
        name="📋 Queue & Modes",
        value=(
            "`/music queue` — View the queue\n"
            "`/music shuffle` — Toggle shuffle\n"
            "`/music loop <mode>` — off / track / queue\n"
            "`/music volume <1-200>` — Set volume\n"
            "`/music autoplay` — Toggle autoplay (YouTube Radio)\n"
        ),
        inline=False,
    )
    e.add_field(
        name="🎶 Playlist",
        value=(
            "`/playlist save <name>` — Save current queue as a playlist\n"
            "`/playlist load <name>` — Load a saved playlist\n"
            "`/playlist list` — List your saved playlists\n"
            "`/playlist delete <name>` — Delete a playlist\n"
        ),
        inline=False,
    )
    e.add_field(
        name="🎛️ Dashboard",
        value=(
            "`/panel` — Post the interactive control panel\n"
            "`/nowplaying` — Show now-playing card\n"
            "`/ping` — Check bot latency\n"
            "`/help` — This message\n"
        ),
        inline=False,
    )
    e.add_field(
        name="🕹️ Button Panel",
        value=(
            "**Row 1:** ▶️ Play/Resume · ⏮️ Previous · ⏸️ Pause · ⏭️ Skip · 📋 Queue\n"
            "**Row 2:** 🔁 Loop · ⏪ Restart · ❤️ Like · ⏩ Skip · 🔊 Volume\n"
            "**Row 3:** 🎶 Playlist · 🔀 Shuffle · ⏹️ Stop · 🔂 Autoplay · 🛟 Help"
        ),
        inline=False,
    )
    e.set_footer(text="🎵 Rhythm • Advanced Music Bot")
    return e


# ── PLAYLIST STORAGE (in-memory per session) ───────────────────────────────────
# Structure: {guild_id: {playlist_name: [Track, ...]}}
_playlists: dict[int, dict[str, list[Track]]] = {}


def guild_playlists(guild_id: int) -> dict[str, list[Track]]:
    if guild_id not in _playlists:
        _playlists[guild_id] = {}
    return _playlists[guild_id]


# ── MODALS ─────────────────────────────────────────────────────────────────────
class PlayModal(discord.ui.Modal, title="🎵 Play Music"):
    query_input = discord.ui.TextInput(
        label="Song name or YouTube URL",
        placeholder="e.g. never gonna give you up",
        min_length=1,
        max_length=200,
    )

    def __init__(self, music_bot: "MusicBot"):
        super().__init__()
        self.music_bot = music_bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.music_bot.request_play(interaction, self.query_input.value.strip())


class VolumeModal(discord.ui.Modal, title="🔊 Set Volume"):
    level_input = discord.ui.TextInput(
        label="Volume (1–200)",
        placeholder="100",
        min_length=1,
        max_length=3,
        default="100",
    )

    def __init__(self, music_bot: "MusicBot", guild_id: int):
        super().__init__()
        self.music_bot = music_bot
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            level = int(self.level_input.value)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("Enter a number between 1 and 200."), ephemeral=True
            )
        if not 1 <= level <= 200:
            return await interaction.response.send_message(
                embed=error_embed("Volume must be between 1 and 200."), ephemeral=True
            )
        state = self.music_bot.get_state(self.guild_id)
        state.volume = percent_to_volume(level)
        vc = interaction.guild.voice_client if interaction.guild else None
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = state.volume
        await interaction.response.send_message(
            embed=success_embed("Volume updated", f"Volume set to **{level}%**."), ephemeral=True
        )
        await self.music_bot.update_panel(interaction.guild)


# ── BOT ────────────────────────────────────────────────────────────────────────
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.music_states: dict[int, GuildMusicState] = {}

    def get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.music_states:
            self.music_states[guild_id] = GuildMusicState()
        return self.music_states[guild_id]

    async def setup_hook(self) -> None:
        await self.tree.sync()
        log.info("Slash commands synced globally.")

    # ── Voice status ───────────────────────────────────────────────────────────
    def format_voice_status(self, track: Track, *, paused: bool = False) -> str:
        icon = "⏸️ " if paused else "🎵 "
        text = f"{icon}{track.title.strip()}"
        return text[:VOICE_STATUS_MAX_LEN - 1] + "…" if len(text) > VOICE_STATUS_MAX_LEN else text

    async def set_voice_channel_status(
        self, guild: discord.Guild, track: Optional[Track] = None, *, paused: bool = False
    ) -> None:
        vc = guild.voice_client
        if not vc or not isinstance(vc.channel, discord.VoiceChannel):
            return
        try:
            if track:
                await self.http.edit_voice_channel_status(
                    self.format_voice_status(track, paused=paused), channel_id=vc.channel.id
                )
            else:
                await self.http.edit_voice_channel_status(None, channel_id=vc.channel.id)
        except discord.HTTPException as exc:
            log.warning("Voice status error: %s", exc)

    async def sync_voice_status(self, guild: discord.Guild) -> None:
        state = self.get_state(guild.id)
        vc = guild.voice_client
        if not vc or not state.now_playing:
            await self.set_voice_channel_status(guild, None)
            return
        await self.set_voice_channel_status(guild, state.now_playing, paused=bool(vc.is_paused()))

    # ── Panel management ───────────────────────────────────────────────────────
    def get_panel_message(self, guild_id: int) -> Optional[discord.Message]:
        state = self.get_state(guild_id)
        return state.dashboard_message or state.panel_message

    def _bind_panel(self, state: GuildMusicState, message: discord.Message) -> None:
        state.dashboard_message = message
        state.panel_message = message

    def _clear_panel(self, state: GuildMusicState) -> None:
        state.dashboard_message = None
        state.panel_message = None

    async def update_panel(self, guild: discord.Guild) -> None:
        state = self.get_state(guild.id)
        panel = self.get_panel_message(guild.id)
        if not panel:
            return
        try:
            embed = build_dashboard_embed(guild, state)
            await panel.edit(embed=embed)
        except discord.HTTPException:
            self._clear_panel(state)

    async def update_dashboard(self, guild: discord.Guild) -> None:
        await self.update_panel(guild)

    async def ensure_panel(
        self, guild: discord.Guild, channel: discord.abc.Messageable
    ) -> Optional[discord.Message]:
        state = self.get_state(guild.id)
        existing = self.get_panel_message(guild.id)
        if existing:
            await self.update_panel(guild)
            return existing
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return None
        embed = build_dashboard_embed(guild, state)
        message = await channel.send(embed=embed)
        self._bind_panel(state, message)
        return message

    # ── Playback ───────────────────────────────────────────────────────────────
    def voice_channel_error(self, interaction: discord.Interaction) -> Optional[discord.Embed]:
        if not interaction.user or not isinstance(interaction.user, discord.Member):
            return error_embed("Could not resolve your member profile.")
        if not interaction.user.voice or not interaction.user.voice.channel:
            return error_embed("Join a voice channel first.")
        return None

    async def connect_voice(self, interaction: discord.Interaction) -> discord.VoiceClient:
        member = interaction.user
        assert isinstance(member, discord.Member)
        channel = member.voice.channel
        if interaction.guild.voice_client:
            if interaction.guild.voice_client.channel != channel:
                await interaction.guild.voice_client.move_to(channel)
            return interaction.guild.voice_client
        return await channel.connect()

    async def request_play(self, interaction: discord.Interaction, query: str) -> None:
        voice_error = self.voice_channel_error(interaction)
        if voice_error:
            return await interaction.response.send_message(embed=voice_error, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        vc = await self.connect_voice(interaction)

        try:
            track = await asyncio.to_thread(extract_audio, query)
        except Exception as exc:
            return await interaction.followup.send(
                embed=error_embed(f"Could not find that track.\n`{exc}`"), ephemeral=True
            )

        track.requester_id = interaction.user.id
        state = self.get_state(interaction.guild_id)

        if vc.is_playing() or vc.is_paused():
            state.queue.append(track)
            e = success_embed("Added to queue", f"**{track.title}**\n`{track.duration_text}`")
            if track.thumbnail:
                e.set_thumbnail(url=track.thumbnail)
            await interaction.followup.send(embed=e, ephemeral=True)
        else:
            await self.play_track(interaction.guild, interaction.channel, track)
            await interaction.followup.send(
                embed=success_embed("Now playing", f"**{track.title}**"), ephemeral=True
            )
        await self.update_dashboard(interaction.guild)

    async def play_track(
        self,
        guild: discord.Guild,
        channel: discord.abc.Messageable,
        track: Track,
        *,
        interaction: Optional[discord.Interaction] = None,
    ) -> None:
        vc = guild.voice_client
        if not vc:
            return

        state = self.get_state(guild.id)
        if state.now_playing and state.now_playing.webpage_url != track.webpage_url:
            state.play_history.append(state.now_playing)
            if len(state.play_history) > 25:
                state.play_history = state.play_history[-25:]
        state.now_playing = track
        state.playback_started_at = asyncio.get_event_loop().time()

        def after(error: Optional[Exception]) -> None:
            if error:
                log.error("Playback error in %s: %s", guild.name, error)
                asyncio.run_coroutine_threadsafe(
                    self._notify_playback_error(guild, channel, str(error)), self.loop
                )
            asyncio.run_coroutine_threadsafe(self.advance_queue(guild, channel), self.loop)

        raw = discord.FFmpegPCMAudio(track.stream_url, **FFMPEG_OPTIONS)
        source = discord.PCMVolumeTransformer(raw, volume=state.volume)
        vc.play(source, after=after)

        await self.set_voice_channel_status(guild, track, paused=False)
        state.text_channel_id = getattr(channel, "id", None)

        if self.get_panel_message(guild.id):
            await self.update_panel(guild)
        else:
            await self.ensure_panel(guild, channel)

        if interaction:
            await interaction.edit_original_response(
                embed=success_embed("Now playing", f"**{track.title}**")
            )

    async def _notify_playback_error(
        self, guild: discord.Guild, channel: discord.abc.Messageable, detail: str
    ) -> None:
        await channel.send(
            embed=error_embed(
                f"Playback failed.\nTry `/music play` again or run `pip install -U yt-dlp`.\n`{detail[:200]}`"
            )
        )
        await self.update_dashboard(guild)

    async def advance_queue(self, guild: discord.Guild, channel: discord.abc.Messageable) -> None:
        vc = guild.voice_client
        if not vc:
            return

        state = self.get_state(guild.id)
        finished = state.now_playing

        if state.loop_mode == LoopMode.TRACK and finished:
            await self.play_track(guild, channel, finished)
            return

        if state.loop_mode == LoopMode.QUEUE and finished:
            state.queue.append(finished)

        if not state.queue:
            if state.autoplay and finished:
                try:
                    next_track = await asyncio.to_thread(fetch_autoplay_track, finished, state.autoplay_history)
                    state.autoplay_history.append(next_track.webpage_url)
                    if len(state.autoplay_history) > 30:
                        state.autoplay_history = state.autoplay_history[-30:]
                    next_track.requester_id = finished.requester_id
                    await self.play_track(guild, channel, next_track)
                    return
                except Exception as exc:
                    log.warning("Autoplay failed: %s", exc)
                    await channel.send(embed=error_embed(f"Autoplay failed: `{exc}`"))

            state.now_playing = None
            state.playback_started_at = None
            await self.set_voice_channel_status(guild, None)
            await self.update_panel(guild)
            await vc.disconnect()
            return

        if state.shuffle and len(state.queue) > 1:
            track = state.queue.pop(random.randrange(len(state.queue)))
        else:
            track = state.queue.pop(0)

        try:
            fresh = await asyncio.to_thread(extract_audio, track.webpage_url)
            track.stream_url = fresh.stream_url
            track.title = fresh.title
            track.thumbnail = fresh.thumbnail or track.thumbnail or resolve_thumbnail(
                {"id": extract_youtube_id(track.webpage_url)}, track.webpage_url
            )
            track.duration = fresh.duration or track.duration
            track.uploader = fresh.uploader or track.uploader
        except Exception as exc:
            log.warning("Failed to refresh track, skipping: %s", exc)
            await channel.send(embed=error_embed(f"Skipped **{track.title}**: `{exc}`"))
            await self.advance_queue(guild, channel)
            return

        await self.play_track(guild, channel, track)


bot = MusicBot()

# ── SLASH COMMAND GROUPS ───────────────────────────────────────────────────────
music = app_commands.Group(name="music", description="Music playback controls")
playlist_group = app_commands.Group(name="playlist", description="Manage saved playlists")


# ── /music commands ────────────────────────────────────────────────────────────
@music.command(name="play", description="Play a song from YouTube (search or URL)")
@app_commands.describe(query="Song name or YouTube link")
async def music_play(interaction: discord.Interaction, query: str) -> None:
    voice_error = bot.voice_channel_error(interaction)
    if voice_error:
        return await interaction.response.send_message(embed=voice_error, ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    vc = await bot.connect_voice(interaction)

    try:
        track = await asyncio.to_thread(extract_audio, query)
    except Exception as exc:
        return await interaction.edit_original_response(
            embed=error_embed(f"Could not find that track.\n`{exc}`")
        )

    track.requester_id = interaction.user.id
    state = bot.get_state(interaction.guild_id)

    if vc.is_playing() or vc.is_paused():
        state.queue.append(track)
        e = success_embed("Added to queue", f"**{track.title}**\n`{track.duration_text}`")
        if track.thumbnail:
            e.set_thumbnail(url=track.thumbnail)
        await bot.update_dashboard(interaction.guild)
        return await interaction.edit_original_response(embed=e)

    await bot.play_track(interaction.guild, interaction.channel, track, interaction=interaction)


@music.command(name="pause", description="Pause the current track")
async def music_pause(interaction: discord.Interaction) -> None:
    vc = interaction.guild.voice_client if interaction.guild else None
    if not vc or not vc.is_playing():
        return await interaction.response.send_message(embed=error_embed("Nothing is playing."), ephemeral=True)
    vc.pause()
    await bot.sync_voice_status(interaction.guild)
    await bot.update_dashboard(interaction.guild)
    await interaction.response.send_message(embed=success_embed("Paused", "Playback paused."), ephemeral=True)


@music.command(name="resume", description="Resume paused playback")
async def music_resume(interaction: discord.Interaction) -> None:
    vc = interaction.guild.voice_client if interaction.guild else None
    if not vc or not vc.is_paused():
        return await interaction.response.send_message(embed=error_embed("Playback is not paused."), ephemeral=True)
    vc.resume()
    state = bot.get_state(interaction.guild_id)
    state.playback_started_at = asyncio.get_event_loop().time()
    await bot.sync_voice_status(interaction.guild)
    await bot.update_dashboard(interaction.guild)
    await interaction.response.send_message(embed=success_embed("Resumed", "Playback resumed."), ephemeral=True)


@music.command(name="skip", description="Skip the current track")
async def music_skip(interaction: discord.Interaction) -> None:
    vc = interaction.guild.voice_client if interaction.guild else None
    if not vc or not (vc.is_playing() or vc.is_paused()):
        return await interaction.response.send_message(embed=error_embed("Nothing is playing."), ephemeral=True)
    vc.stop()
    await interaction.response.send_message(embed=success_embed("Skipped", "Loading next track…"), ephemeral=True)


@music.command(name="stop", description="Stop playback and disconnect")
async def music_stop(interaction: discord.Interaction) -> None:
    state = bot.get_state(interaction.guild_id)
    state.queue.clear()
    state.now_playing = None
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc:
        vc.stop()
        await bot.set_voice_channel_status(interaction.guild, None)
        await vc.disconnect()
    await bot.update_panel(interaction.guild)
    await interaction.response.send_message(
        embed=success_embed("Stopped", "Disconnected and cleared the queue.")
    )


@music.command(name="queue", description="Show the current music queue")
async def music_queue(interaction: discord.Interaction) -> None:
    state = bot.get_state(interaction.guild_id)
    await interaction.response.send_message(
        embed=build_queue_embed(interaction.guild_id, state), ephemeral=True
    )


@music.command(name="shuffle", description="Toggle shuffle mode")
async def music_shuffle(interaction: discord.Interaction) -> None:
    state = bot.get_state(interaction.guild_id)
    state.shuffle = not state.shuffle
    await bot.update_dashboard(interaction.guild)
    await interaction.response.send_message(
        embed=success_embed("Shuffle", f"Shuffle is now **{'on' if state.shuffle else 'off'}**."), ephemeral=True
    )


@music.command(name="loop", description="Set loop mode")
@app_commands.describe(mode="Loop behavior")
@app_commands.choices(mode=[
    app_commands.Choice(name="Off",          value="off"),
    app_commands.Choice(name="Current track", value="track"),
    app_commands.Choice(name="Whole queue",  value="queue"),
])
async def music_loop(interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
    state = bot.get_state(interaction.guild_id)
    state.loop_mode = LoopMode(mode.value)
    await bot.update_dashboard(interaction.guild)
    await interaction.response.send_message(
        embed=success_embed("Loop mode", f"Loop set to `{mode.value}`."), ephemeral=True
    )


@music.command(name="volume", description="Set playback volume (1–200)")
@app_commands.describe(level="Volume percentage (100 = normal)")
async def music_volume(interaction: discord.Interaction, level: app_commands.Range[int, 1, 200]) -> None:
    state = bot.get_state(interaction.guild_id)
    state.volume = percent_to_volume(level)
    vc = interaction.guild.voice_client if interaction.guild else None
    if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = state.volume
    await bot.update_dashboard(interaction.guild)
    await interaction.response.send_message(
        embed=success_embed("Volume", f"Volume set to **{level}%**."), ephemeral=True
    )


@music.command(name="autoplay", description="Toggle autoplay (YouTube Radio)")
async def music_autoplay(interaction: discord.Interaction) -> None:
    state = bot.get_state(interaction.guild_id)
    state.autoplay = not state.autoplay
    if state.autoplay:
        state.autoplay_history.clear()
    await bot.update_dashboard(interaction.guild)
    await interaction.response.send_message(
        embed=success_embed("Autoplay", f"Autoplay is now **{'on' if state.autoplay else 'off'}**."), ephemeral=True
    )


@music.command(name="panel", description="Re-post the music dashboard in this channel")
async def music_panel_cmd(interaction: discord.Interaction) -> None:
    await _post_dashboard(interaction, interaction.channel)


# ── /playlist commands ─────────────────────────────────────────────────────────
@playlist_group.command(name="save", description="Save the current queue as a named playlist")
@app_commands.describe(name="Playlist name")
async def playlist_save(interaction: discord.Interaction, name: str) -> None:
    state = bot.get_state(interaction.guild_id)
    tracks = ([state.now_playing] if state.now_playing else []) + list(state.queue)
    if not tracks:
        return await interaction.response.send_message(
            embed=error_embed("Nothing to save — queue is empty."), ephemeral=True
        )
    pl = guild_playlists(interaction.guild_id)
    pl[name] = list(tracks)
    await interaction.response.send_message(
        embed=success_embed("Playlist saved", f"**{name}** — {len(tracks)} track(s)."), ephemeral=True
    )


@playlist_group.command(name="load", description="Load a saved playlist into the queue")
@app_commands.describe(name="Playlist name")
async def playlist_load(interaction: discord.Interaction, name: str) -> None:
    pl = guild_playlists(interaction.guild_id)
    if name not in pl:
        return await interaction.response.send_message(
            embed=error_embed(f"No playlist named **{name}**. Use `/playlist list` to see all."), ephemeral=True
        )
    state = bot.get_state(interaction.guild_id)
    tracks = pl[name]
    state.queue.extend(tracks)
    await bot.update_dashboard(interaction.guild)

    voice_error = bot.voice_channel_error(interaction)
    if not voice_error and not (interaction.guild.voice_client and (
        interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()
    )):
        await interaction.response.defer(ephemeral=True)
        vc = await bot.connect_voice(interaction)
        if not vc.is_playing() and state.queue:
            first = state.queue.pop(0)
            try:
                fresh = await asyncio.to_thread(extract_audio, first.webpage_url)
                first.stream_url = fresh.stream_url
            except Exception:
                pass
            await bot.play_track(interaction.guild, interaction.channel, first)
        await interaction.followup.send(
            embed=success_embed("Playlist loaded", f"**{name}** — {len(tracks)} track(s) added."), ephemeral=True
        )
    else:
        await interaction.response.send_message(
            embed=success_embed("Playlist loaded", f"**{name}** — {len(tracks)} track(s) added to queue."), ephemeral=True
        )


@playlist_group.command(name="list", description="List your saved playlists")
async def playlist_list(interaction: discord.Interaction) -> None:
    pl = guild_playlists(interaction.guild_id)
    e = discord.Embed(title="🎶  Saved Playlists", color=BRAND)
    if not pl:
        e.description = "*No playlists saved yet. Use `/playlist save <name>` to create one.*"
    else:
        lines = [f"`{i}.`  **{name}**  — {len(tracks)} track(s)" for i, (name, tracks) in enumerate(pl.items(), 1)]
        e.description = "\n".join(lines)
    e.set_footer(text="🎵 Rhythm")
    await interaction.response.send_message(embed=e, ephemeral=True)


@playlist_group.command(name="delete", description="Delete a saved playlist")
@app_commands.describe(name="Playlist name")
async def playlist_delete(interaction: discord.Interaction, name: str) -> None:
    pl = guild_playlists(interaction.guild_id)
    if name not in pl:
        return await interaction.response.send_message(
            embed=error_embed(f"No playlist named **{name}**."), ephemeral=True
        )
    del pl[name]
    await interaction.response.send_message(
        embed=success_embed("Deleted", f"Playlist **{name}** has been deleted."), ephemeral=True
    )


# ── Top-level slash commands ───────────────────────────────────────────────────
async def _post_dashboard(
    interaction: discord.Interaction,
    channel: discord.abc.GuildChannel,
) -> None:
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return await interaction.response.send_message(
            embed=error_embed("Dashboard can only be posted in a text channel."), ephemeral=True
        )
    state = bot.get_state(interaction.guild_id)
    embed = build_dashboard_embed(interaction.guild, state)
    message = await channel.send(embed=embed)
    bot._bind_panel(state, message)
    await interaction.response.send_message(
        embed=success_embed("Dashboard posted", f"Music control panel sent to {channel.mention}."),
        ephemeral=True,
    )


@bot.tree.command(name="panel", description="Post the music control panel")
@app_commands.describe(channel="Channel to post in (defaults to current channel)")
@app_commands.default_permissions(manage_messages=True)
async def panel_command(
    interaction: discord.Interaction,
    channel: Optional[discord.TextChannel] = None,
) -> None:
    await _post_dashboard(interaction, channel or interaction.channel)


@bot.tree.command(name="nowplaying", description="Show the currently playing track")
async def nowplaying_command(interaction: discord.Interaction) -> None:
    state = bot.get_state(interaction.guild_id)
    embed = build_now_playing_embed(interaction.guild, state)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction) -> None:
    ms = round(bot.latency * 1000)
    color = SUCCESS if ms < 100 else WARNING if ms < 200 else ERROR
    e = discord.Embed(
        title="🏓  Pong!",
        description=f"WebSocket latency: **{ms} ms**",
        color=color,
    )
    e.set_footer(text="🎵 Rhythm")
    await interaction.response.send_message(embed=e, ephemeral=True)


@bot.tree.command(name="help", description="Show all commands")
async def help_command(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)


bot.tree.add_command(music)
bot.tree.add_command(playlist_group)


# ── EVENTS ─────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready() -> None:
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="/music play",
        )
    )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    log.exception("Slash command error: %s", error)
    embed = error_embed(str(error))
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── ENTRY POINT ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN in your environment before running the bot.")
    bot.run(token)
