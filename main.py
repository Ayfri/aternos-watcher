import json
import logging
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum, auto
from http.client import HTTPException
from typing import TYPE_CHECKING, NamedTuple, Self
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from mcstatus import JavaServer

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mcstatus.responses import JavaStatusResponse

logger = logging.getLogger("aternos-watcher")

CONFIRM_DELAY = 5
"""Aternos intermittently resets status connections, so every open/closed change is re-checked after this many seconds."""

CHECK_TIMEOUT = 10
"""Seconds allowed for the SRV lookup and the status ping, a booting Aternos server answers slower than mcstatus' 3 s default."""

ANSI_CODES = {
    "0": "\x1b[30m",
    "1": "\x1b[34m",
    "2": "\x1b[32m",
    "3": "\x1b[36m",
    "4": "\x1b[31m",
    "5": "\x1b[35m",
    "6": "\x1b[33m",
    "7": "\x1b[37m",
    "8": "\x1b[30;1m",
    "9": "\x1b[34;1m",
    "a": "\x1b[32;1m",
    "b": "\x1b[36;1m",
    "c": "\x1b[31;1m",
    "d": "\x1b[35;1m",
    "e": "\x1b[33;1m",
    "f": "\x1b[37;1m",
    "k": "",
    "l": "\x1b[1m",
    "m": "",
    "n": "\x1b[4m",
    "o": "",
    "r": "\x1b[0m",
}
"""Minecraft formatting codes mapped to the basic ANSI subset Discord renders, `Motd.to_ansi()` emits 24-bit colors Discord ignores."""

MC_FORMAT_CODE = re.compile(r"§([0-9a-fk-or])", re.IGNORECASE)


def mc_to_ansi(text: str) -> str:
    return MC_FORMAT_CODE.sub(lambda match: ANSI_CODES[match[1].lower()], text) + ANSI_CODES["r"]


class ServerState(StrEnum):
    OFFLINE = auto()
    STARTING = auto()
    WAITING = auto()
    ONLINE = auto()
    STOPPING = auto()

    @property
    def is_open(self) -> bool:
        return self in {ServerState.WAITING, ServerState.ONLINE}

    @property
    def is_transition(self) -> bool:
        return self in {ServerState.STARTING, ServerState.STOPPING}


class EmbedStyle(NamedTuple):
    title: str
    color: int


def env(name: str, default: str) -> str:
    return os.environ.get(f"ATERNOS_WATCHER_{name}", default)


def optional_env(name: str) -> str | None:
    return os.environ.get(f"ATERNOS_WATCHER_{name}") or None


def without_none(**fields: str | None) -> dict[str, str]:
    return {key: value for key, value in fields.items() if value is not None}


def style_env(state: str, title: str, color: str) -> EmbedStyle:
    return EmbedStyle(env(f"{state}_TITLE", title), int(env(f"{state}_COLOR", color).removeprefix("#"), 16))


@dataclass(frozen=True, slots=True, kw_only=True)
class Config:
    address: str
    webhook_url: str
    check_interval: int
    verbose: bool
    styles: Mapping[ServerState, EmbedStyle]
    waiting_message: str
    footer_text: str | None
    footer_icon: str | None
    thumbnail_url: str | None
    author_name: str | None
    author_icon: str | None
    author_url: str | None
    mention: str | None
    show_players: bool
    show_motd: bool

    @classmethod
    def from_env(cls) -> Self:
        webhook_url = optional_env("WEBHOOK_URL") or ""
        url_parts = urlsplit(webhook_url)
        if url_parts.scheme != "https" or not url_parts.netloc or any(char.isspace() for char in webhook_url):
            msg = "ATERNOS_WATCHER_WEBHOOK_URL must be set to an https:// Discord webhook URL."
            raise SystemExit(msg)

        host = optional_env("HOST") or "localhost"
        port = optional_env("PORT")
        if port is not None and not 0 < int(port) < 1 << 16:
            msg = f"ATERNOS_WATCHER_PORT must be between 1 and 65535, got {port}."
            raise SystemExit(msg)
        return cls(
            address=host if port is None else f"{host}:{port}",
            webhook_url=webhook_url,
            check_interval=int(env("UPDATE_TIME", "30")),
            verbose=env("VERBOSE", "false").lower() == "true",
            styles={
                ServerState.ONLINE: style_env("ONLINE", "🟢 Server ONLINE!", "30c030"),
                ServerState.WAITING: style_env("WAITING", "⏳ Server WAITING...", "ffff00"),
                ServerState.OFFLINE: style_env("OFFLINE", "🔴 Server OFFLINE", "ff4040"),
            },
            waiting_message=env("WAITING_MESSAGE", "Please connect in less than 7 minutes to make it stay open!"),
            footer_text=env("FOOTER_TEXT", "Aternos Watcher") or None,
            footer_icon=optional_env("FOOTER_ICON"),
            thumbnail_url=optional_env("THUMBNAIL_URL"),
            author_name=optional_env("AUTHOR_NAME"),
            author_icon=optional_env("AUTHOR_ICON"),
            author_url=optional_env("AUTHOR_URL"),
            mention=optional_env("MENTION"),
            show_players=env("SHOW_PLAYERS", "true").lower() == "true",
            show_motd=env("SHOW_MOTD", "true").lower() == "true",
        )


class Watcher:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.last_state = ServerState.OFFLINE
        self.last_error: str | None = None

    def check(self) -> tuple[ServerState, JavaStatusResponse | None]:
        try:
            # Without a port, lookup resolves the SRV record each time, following Aternos' dynamic ports.
            status = JavaServer.lookup(self.config.address, timeout=CHECK_TIMEOUT).status()
            texts = (status.motd.to_plain().lower(), status.version.name.lower())
        except Exception as error:  # noqa: BLE001 - any failed or unparsable status means the server isn't reachable.
            # A reset connection is the normal offline answer, anything else (timeout, DNS, parsing) is logged once per kind.
            description = repr(error)
            if not isinstance(error, ConnectionResetError) and description != self.last_error:
                logger.warning("Status check failed, treating as offline: %s", description)
            self.last_error = description
            return ServerState.OFFLINE, None
        self.last_error = None

        logger.debug("Raw status: %s", status.raw)

        if any("offline" in text for text in texts):
            return ServerState.OFFLINE, status
        if any("starting" in text or "preparing" in text for text in texts):
            return ServerState.STARTING, status
        if any("stopping" in text for text in texts):
            return ServerState.STOPPING, status
        # The Aternos waiting proxy reports 0 max players, a real server never does.
        return ServerState.WAITING if status.players.max == 0 else ServerState.ONLINE, status

    def build_embed(self, state: ServerState, status: JavaStatusResponse | None) -> dict[str, object]:
        config = self.config
        style = config.styles[state]
        description = [f"**Host:** `{config.address}`"]

        if state is ServerState.WAITING:
            description.append(f"\n⚠️ **{config.waiting_message}**")
        if status is not None:
            if config.show_players and state is ServerState.ONLINE:
                description.append(f"**Players:** `{status.players.online}/{status.players.max}`")
            if config.show_motd:
                description.append(f"**MOTD:**\n```ansi\n{mc_to_ansi(status.motd.to_minecraft())}\n```")

        embed: dict[str, object] = {
            "title": style.title,
            "color": style.color,
            "description": "\n".join(description),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if config.author_name:
            embed["author"] = without_none(name=config.author_name, url=config.author_url, icon_url=config.author_icon)
        if config.thumbnail_url:
            embed["thumbnail"] = {"url": config.thumbnail_url}
        if config.footer_text:
            embed["footer"] = without_none(text=config.footer_text, icon_url=config.footer_icon)
        return embed

    def notify(self, state: ServerState, status: JavaStatusResponse | None) -> None:
        payload: dict[str, object] = {"embeds": [self.build_embed(state, status)]}
        if self.config.mention:
            payload["content"] = self.config.mention
        request = Request(  # noqa: S310 - the webhook URL is validated as https:// in Config.from_env.
            self.config.webhook_url,
            data=json.dumps(payload).encode(),
            # Discord's Cloudflare rejects urllib's default User-Agent with a 403.
            headers={"Content-Type": "application/json", "User-Agent": "aternos-watcher"},
        )
        try:
            with urlopen(request, timeout=10):  # noqa: S310 - same validated https:// URL.
                logger.info("Notification sent: %s", self.config.styles[state].title)
        except OSError, HTTPException:
            logger.exception("Failed to send webhook")

    def is_change(self, state: ServerState) -> bool:
        return not state.is_transition and state.is_open != self.last_state.is_open

    def tick(self) -> None:
        state, _ = self.check()
        if not self.is_change(state):
            return

        time.sleep(CONFIRM_DELAY)
        confirmed_state, status = self.check()
        if not self.is_change(confirmed_state):
            logger.info("State flicker detected (%s -> %s), ignoring.", state, confirmed_state)
            return

        logger.info("State change: %s -> %s", self.last_state, confirmed_state)
        self.notify(confirmed_state, status)
        self.last_state = confirmed_state

    def run(self) -> None:
        logger.info("Watching %s every %d seconds.", self.config.address, self.config.check_interval)
        while True:
            self.tick()
            time.sleep(self.config.check_interval)


def main() -> None:
    config = Config.from_env()
    logging.basicConfig(
        level=logging.DEBUG if config.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # `docker stop` sends SIGTERM, raising KeyboardInterrupt makes it stop as cleanly as Ctrl+C.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        Watcher(config).run()
    except KeyboardInterrupt:
        logger.info("Watcher stopped.")


if __name__ == "__main__":
    main()
