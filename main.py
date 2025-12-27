import os
import time
import logging
import sys
from enum import Enum

from mcstatus import JavaServer
from mcstatus.responses import JavaStatusResponse
from discord_webhook import DiscordWebhook, DiscordEmbed
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# Configuration Constants
HOST = os.getenv("ATERNOS_WATCHER_HOST", "localhost")
PORT = int(os.getenv("ATERNOS_WATCHER_PORT", "25565"))
WEBHOOK_URL = os.getenv("ATERNOS_WATCHER_WEBHOOK_URL")
CHECK_INTERVAL = int(os.getenv("ATERNOS_WATCHER_UPDATE_TIME", "30"))
VERBOSE = os.getenv("ATERNOS_WATCHER_VERBOSE", "false").lower() == "true"

# Customization Constants
ONLINE_TITLE = os.getenv("ATERNOS_WATCHER_ONLINE_TITLE", "🟢 Server ONLINE!")
OFFLINE_TITLE = os.getenv("ATERNOS_WATCHER_OFFLINE_TITLE", "🔴 Server OFFLINE")
WAITING_TITLE = os.getenv("ATERNOS_WATCHER_WAITING_TITLE", "⏳ Server WAITING...")
STOPPING_TITLE = os.getenv("ATERNOS_WATCHER_STOPPING_TITLE", "🛑 Server STOPPING...")

ONLINE_COLOR = os.getenv("ATERNOS_WATCHER_ONLINE_COLOR", "30c030")
OFFLINE_COLOR = os.getenv("ATERNOS_WATCHER_OFFLINE_COLOR", "ff4040")
WAITING_COLOR = os.getenv("ATERNOS_WATCHER_WAITING_COLOR", "ffff00")
STOPPING_COLOR = os.getenv("ATERNOS_WATCHER_STOPPING_COLOR", "ff8c00")

WAITING_MESSAGE = os.getenv("ATERNOS_WATCHER_WAITING_MESSAGE", "Please connect in less than 7 minutes to make it stay open!")

FOOTER_TEXT = os.getenv("ATERNOS_WATCHER_FOOTER_TEXT", "Aternos Watcher")
FOOTER_ICON = os.getenv("ATERNOS_WATCHER_FOOTER_ICON")
THUMBNAIL_URL = os.getenv("ATERNOS_WATCHER_THUMBNAIL_URL")
AUTHOR_NAME = os.getenv("ATERNOS_WATCHER_AUTHOR_NAME")
AUTHOR_ICON = os.getenv("ATERNOS_WATCHER_AUTHOR_ICON")
AUTHOR_URL = os.getenv("ATERNOS_WATCHER_AUTHOR_URL")
MENTION = os.getenv("ATERNOS_WATCHER_MENTION")
SHOW_PLAYERS = os.getenv("ATERNOS_WATCHER_SHOW_PLAYERS", "true").lower() == "true"
SHOW_MOTD = os.getenv("ATERNOS_WATCHER_SHOW_MOTD", "true").lower() == "true"


class ServerState(Enum):
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    WAITING = "WAITING"
    ONLINE = "ONLINE"
    STOPPING = "STOPPING"


# Configure Logging
logging.basicConfig(
    level=logging.DEBUG if VERBOSE else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Watcher")


def mc_to_ansi(text: str) -> str:
    """
    Converts Minecraft formatting codes (§) to ANSI escape codes for Discord.
    Reference: https://minecraft.wiki/w/Formatting_codes
    """
    codes = {
        "0": "\u001b[30m",  # Black
        "1": "\u001b[34m",  # Dark Blue
        "2": "\u001b[32m",  # Dark Green
        "3": "\u001b[36m",  # Dark Aqua
        "4": "\u001b[31m",  # Dark Red
        "5": "\u001b[35m",  # Dark Purple
        "6": "\u001b[33m",  # Gold
        "7": "\u001b[37m",  # Gray
        "8": "\u001b[30;1m",  # Dark Gray
        "9": "\u001b[34;1m",  # Blue
        "a": "\u001b[32;1m",  # Green
        "b": "\u001b[36;1m",  # Aqua
        "c": "\u001b[31;1m",  # Red
        "d": "\u001b[35;1m",  # Light Purple
        "e": "\u001b[33;1m",  # Yellow
        "f": "\u001b[37;1m",  # White
        "k": "",  # Obfuscated (Not supported in ANSI)
        "l": "\u001b[1m",  # Bold
        "m": "",  # Strikethrough (Not supported in ANSI)
        "n": "\u001b[4m",  # Underline
        "o": "",  # Italic (Not supported in ANSI)
        "r": "\u001b[0m",  # Reset
    }

    result = ""
    i = 0
    while i < len(text):
        if text[i] == "§" and i + 1 < len(text):
            code = text[i + 1].lower()
            if code in codes:
                result += codes[code]
                i += 2
                continue
        result += text[i]
        i += 1

    return result + "\u001b[0m"


def get_server_status() -> tuple[ServerState, JavaStatusResponse | None]:
    """
    Checks the server status and returns the state and the raw status response.
    """
    try:
        # JavaServer.lookup handles DNS SRV records automatically
        server = JavaServer.lookup(f"{HOST}:{PORT}")

        # We need the full status to check the MOTD (Description)
        status = server.status()

        logger.debug(f"Raw Status: {status}")

        # --- ATERNOS FILTERING LOGIC ---
        motd = str(status.description).lower()

        if "offline" in motd:
            return ServerState.OFFLINE, status

        if "starting" in motd or "preparing" in motd:
            return ServerState.STARTING, status

        if "stopping" in motd:
            return ServerState.STOPPING, status

        if "connect to" in motd:
            return ServerState.WAITING, status

        # Secondary check: Ghost servers often report 20 max players but "Offline" in MOTD.
        # Real servers usually have 20+ max players.
        # If max players is 0, it's usually a transition state or waiting state.
        if status.players.max == 0:
            # If it's not starting/stopping/waiting, but max is 0, it's likely offline or ghost.
            return ServerState.OFFLINE, status

        return ServerState.ONLINE, status

    except Exception:
        # Any connection error (Timeout, Refused, etc.) means it's down.
        return ServerState.OFFLINE, None


def send_discord_notification(state: ServerState, status: JavaStatusResponse | None) -> None:
    """Sends a standardized embed to Discord."""
    if not WEBHOOK_URL:
        logger.warning("No Webhook URL provided. Skipping notification.")
        return

    if state == ServerState.ONLINE:
        status_text = ONLINE_TITLE
        color = ONLINE_COLOR
    elif state == ServerState.WAITING:
        status_text = WAITING_TITLE
        color = WAITING_COLOR
    elif state == ServerState.STOPPING:
        status_text = STOPPING_TITLE
        color = STOPPING_COLOR
    else:
        status_text = OFFLINE_TITLE
        color = OFFLINE_COLOR

    webhook = DiscordWebhook(url=WEBHOOK_URL, content=MENTION if MENTION else None)
    embed = DiscordEmbed(title=status_text, color=color)

    description = f"**Host:** `{HOST}`"

    if state == ServerState.WAITING:
        description += f"\n\n⚠️ **{WAITING_MESSAGE}**"

    if status:
        if SHOW_PLAYERS and state in [ServerState.ONLINE, ServerState.WAITING]:
            description += f"\n**Players:** `{status.players.online}/{status.players.max}`"

        if SHOW_MOTD:
            # Clean MOTD from formatting codes if possible, or just use it as is
            motd = status.description
            if hasattr(motd, "to_plain"):
                motd = motd.to_plain()
            elif isinstance(motd, dict):
                motd = motd.get("text", "")

            # Convert Minecraft formatting to ANSI for Discord
            ansi_motd = mc_to_ansi(str(status.description))
            description += f"\n**MOTD:**\n```ansi\n{ansi_motd}\n```"

    embed.description = description

    if AUTHOR_NAME:
        embed.set_author(name=AUTHOR_NAME, url=AUTHOR_URL, icon_url=AUTHOR_ICON)

    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)

    if FOOTER_TEXT:
        embed.set_footer(text=FOOTER_TEXT, icon_url=FOOTER_ICON)

    embed.set_timestamp()

    webhook.add_embed(embed)

    try:
        webhook.execute()
        logger.info(f"Notification sent: {status_text}")
    except Exception as e:
        logger.error(f"Failed to send webhook: {e}")


def main():
    logger.info(f"Starting Aternos Watcher for {HOST}:{PORT}...")
    logger.info(f"Polling every {CHECK_INTERVAL} seconds.")

    # Initialize state as OFFLINE to avoid spamming notifications on boot
    last_state = ServerState.OFFLINE

    while True:
        current_state, status = get_server_status()

        if current_state != last_state:
            logger.info(f"State Change Detected: {last_state.value} -> {current_state.value}")

            # Notification Logic
            # Only notify for ONLINE, WAITING, and OFFLINE
            # STARTING and STOPPING are silent transition states
            if current_state in [ServerState.ONLINE, ServerState.WAITING, ServerState.OFFLINE]:
                # DEBOUNCE LOGIC for ONLINE/WAITING
                if current_state in [ServerState.ONLINE, ServerState.WAITING]:
                    time.sleep(5)
                    confirmed_state, confirmed_status = get_server_status()
                    if confirmed_state == current_state:
                        send_discord_notification(current_state, confirmed_status)
                    else:
                        logger.info(f"State flicker detected ({current_state.value} -> {confirmed_state.value}). Ignoring.")
                        # Update current_state to the confirmed one to avoid double notification
                        current_state = confirmed_state
                else:
                    send_discord_notification(current_state, status)

            last_state = current_state

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Watcher stopped by user.")
        sys.exit(0)
