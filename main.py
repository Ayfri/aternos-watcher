import os
import time
import logging
import sys
from typing import NoReturn

from mcstatus import JavaServer
from discord_webhook import DiscordWebhook, DiscordEmbed
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration Constants
HOST = os.getenv("ATERNOS_WATCHER_HOST", "localhost")
PORT = int(os.getenv("ATERNOS_WATCHER_PORT", "25565"))
WEBHOOK_URL = os.getenv("ATERNOS_WATCHER_WEBHOOK_URL")
CHECK_INTERVAL = int(os.getenv("ATERNOS_WATCHER_UPDATE_TIME", "30"))

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Watcher")

def get_server_status() -> bool:
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
        motd: str = str(status.description).lower()

        if "offline" in motd:
            return False

        # Secondary check: Ghost servers often report 0 max players,
        # whereas a real server usually has 20+.
        if status.players.max == 0:
            return False

        return True

    except Exception:
        # Any connection error (Timeout, Refused, etc.) means it's down.
        return False

def send_discord_notification(is_online: bool) -> None:
    """Sends a standardized embed to Discord."""
    if not WEBHOOK_URL:
        logger.warning("No Webhook URL provided. Skipping notification.")
        return

    status_text: str = "🟢 Server ONLINE!" if is_online else "🔴 Server OFFLINE"
    color: str = "30c030" if is_online else "ff4040"

    webhook = DiscordWebhook(url=WEBHOOK_URL)
    embed = DiscordEmbed(title=status_text, description=f"Host: `{HOST}`", color=color)
    embed.set_timestamp()

    webhook.add_embed(embed)

    try:
        webhook.execute()
        logger.info(f"Notification sent: {status_text}")
    except Exception as e:
        logger.error(f"Failed to send webhook: {e}")

def main() -> NoReturn:
    logger.info(f"Starting Aternos Watcher for {HOST}:{PORT}...")
    logger.info(f"Polling every {CHECK_INTERVAL} seconds.")

    # Initialize state as False to avoid spamming "Offline" notifications on boot
    last_state: bool = False

    while True:
        current_state: bool = get_server_status()

        if current_state != last_state:
            logger.info(f"State Change Detected: {last_state} -> {current_state}")

            if current_state:
                # DEBOUNCE LOGIC
                # Aternos proxies sometimes flicker. If we detect ONLINE, wait 5s and confirm.
                time.sleep(5)
                if get_server_status():
                    send_discord_notification(True)
                    last_state = True
                else:
                    logger.info("Ghost boot detected (False Positive). Ignoring.")
            else:
                send_discord_notification(False)
                last_state = False

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Watcher stopped by user.")
        sys.exit(0)
