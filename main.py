import os
import time
import logging
import sys

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

# Customization Constants
ONLINE_TITLE = os.getenv("ATERNOS_WATCHER_ONLINE_TITLE", "🟢 Server ONLINE!")
OFFLINE_TITLE = os.getenv("ATERNOS_WATCHER_OFFLINE_TITLE", "🔴 Server OFFLINE")
ONLINE_COLOR = os.getenv("ATERNOS_WATCHER_ONLINE_COLOR", "30c030")
OFFLINE_COLOR = os.getenv("ATERNOS_WATCHER_OFFLINE_COLOR", "ff4040")
FOOTER_TEXT = os.getenv("ATERNOS_WATCHER_FOOTER_TEXT", "Aternos Watcher")
FOOTER_ICON = os.getenv("ATERNOS_WATCHER_FOOTER_ICON")
THUMBNAIL_URL = os.getenv("ATERNOS_WATCHER_THUMBNAIL_URL")
AUTHOR_NAME = os.getenv("ATERNOS_WATCHER_AUTHOR_NAME")
AUTHOR_ICON = os.getenv("ATERNOS_WATCHER_AUTHOR_ICON")
AUTHOR_URL = os.getenv("ATERNOS_WATCHER_AUTHOR_URL")
MENTION = os.getenv("ATERNOS_WATCHER_MENTION")
SHOW_PLAYERS = os.getenv("ATERNOS_WATCHER_SHOW_PLAYERS", "true").lower() == "true"
SHOW_MOTD = os.getenv("ATERNOS_WATCHER_SHOW_MOTD", "true").lower() == "true"


# Configure Logging
logging.basicConfig(
    level=logging.INFO,
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


def get_server_status() -> JavaStatusResponse | None:
    """
    Checks if the server is truly online.
    Filters out the Aternos 'Ghost Server' (proxy) which responds to ping but has 'offline' in MOTD.
    """
    try:
        # JavaServer.lookup handles DNS SRV records automatically
        server = JavaServer.lookup(f"{HOST}:{PORT}")

        # We need the full status to check the MOTD (Description)
        status = server.status()

        # --- ATERNOS FILTERING LOGIC ---
        # The Aternos proxy often stays 'pingable' even when the server is off.
        # It typically displays "Offline" or red text in the MOTD.
        motd = str(status.description).lower()

        if "offline" in motd:
            return None

        # Secondary check: Ghost servers often report 0 max players,
        # whereas a real server usually has 20+.
        if status.players.max == 0:
            return None

        return status

    except Exception:
        # Any connection error (Timeout, Refused, etc.) means it's down.
        return None


def send_discord_notification(status: JavaStatusResponse | None) -> None:
    """Sends a standardized embed to Discord."""
    if not WEBHOOK_URL:
        logger.warning("No Webhook URL provided. Skipping notification.")
        return

    is_online = status is not None
    status_text = ONLINE_TITLE if is_online else OFFLINE_TITLE
    color = ONLINE_COLOR if is_online else OFFLINE_COLOR

    webhook = DiscordWebhook(url=WEBHOOK_URL, content=MENTION if MENTION else None)
    embed = DiscordEmbed(title=status_text, color=color)

    description = f"**Host:** `{HOST}`"
    if is_online and status:
        if SHOW_PLAYERS:
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

    # Initialize state as False to avoid spamming "Offline" notifications on boot
    last_state: bool = False

    while True:
        status = get_server_status()
        current_state = status is not None

        if current_state != last_state:
            logger.info(f"State Change Detected: {last_state} -> {current_state}")

            if current_state:
                # DEBOUNCE LOGIC
                # Aternos proxies sometimes flicker. If we detect ONLINE, wait 5s and confirm.
                time.sleep(5)
                confirmed_status = get_server_status()
                if confirmed_status:
                    send_discord_notification(confirmed_status)
                    last_state = True
                else:
                    logger.info("Ghost boot detected (False Positive). Ignoring.")
            else:
                send_discord_notification(None)
                last_state = False

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Watcher stopped by user.")
        sys.exit(0)
