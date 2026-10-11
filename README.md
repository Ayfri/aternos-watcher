# 🚀 Aternos Watcher

A strictly typed Python 3.14 monitor for Aternos Minecraft servers. It intelligently filters out "Ghost Proxies" (Aternos servers that appear online but are actually in a standby/offline state).

## ✨ Features

- **Ghost Proxy Filtering**: Detects the difference between a truly online server and the Aternos "Offline" or "Preparing" MOTD.
- **Discord Notifications**: Standardized embeds for state changes (Online/Offline) with full customization.
- **ANSI MOTD Support**: Automatically converts Minecraft formatting codes (§) to ANSI for colorful MOTD display in Discord.
- **Debounce Logic**: Re-checks every open/closed change after 5 seconds, so startup flickers and intermittent connection resets never notify.
- **Dynamic Ports**: Follows the server's SRV record when no port is set, like the Minecraft client does.
- **Strictly Typed**: Checked by [Pyrefly](https://pyrefly.org) in strict mode and linted by [Ruff](https://docs.astral.sh/ruff) with every rule enabled.
- **Single Dependency**: Only [mcstatus](https://github.com/py-mine/mcstatus), Discord webhooks go through the standard library.

## 🛠️ Installation & Setup

### Prerequisites
- [uv](https://github.com/astral-sh/uv) (Recommended) or Python 3.14+

### Configuration
Set the following environment variables, or copy `.env.template` to `.env`, which docker compose and `uv run --env-file .env` load:

#### ⚙️ Core Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `ATERNOS_WATCHER_HOST` | Your Aternos server address | `localhost` |
| `ATERNOS_WATCHER_PORT` | Server port, leave unset on Aternos since its ports are dynamic | SRV record, then `25565` |
| `ATERNOS_WATCHER_UPDATE_TIME` | Polling interval in seconds | `30` |
| `ATERNOS_WATCHER_VERBOSE` | Enable debug logging | `false` |
| `ATERNOS_WATCHER_WEBHOOK_URL` | Discord Webhook URL (`https://`) | *Required* |

#### 🎨 Embed Customization
| Variable | Description | Default |
|----------|-------------|---------|
| `ATERNOS_WATCHER_OFFLINE_COLOR` | Hex color when server is offline | `ff4040` |
| `ATERNOS_WATCHER_OFFLINE_TITLE` | Title when server is offline | `🔴 Server OFFLINE` |
| `ATERNOS_WATCHER_ONLINE_COLOR` | Hex color when server is online | `30c030` |
| `ATERNOS_WATCHER_ONLINE_TITLE` | Title when server is online | `🟢 Server ONLINE!` |
| `ATERNOS_WATCHER_WAITING_COLOR` | Hex color when server is waiting | `ffff00` |
| `ATERNOS_WATCHER_WAITING_MESSAGE` | Message shown during WAITING state | `Please connect in less than 7 minutes to make it stay open!` |
| `ATERNOS_WATCHER_WAITING_TITLE` | Title when server is waiting for connection | `⏳ Server WAITING...` |

#### 📝 Embed Metadata
| Variable | Description | Default |
|----------|-------------|---------|
| `ATERNOS_WATCHER_AUTHOR_ICON` | Author icon URL | *None* |
| `ATERNOS_WATCHER_AUTHOR_NAME` | Author name in the embed | *None* |
| `ATERNOS_WATCHER_AUTHOR_URL` | Author link URL | *None* |
| `ATERNOS_WATCHER_FOOTER_ICON` | Footer icon URL | *None* |
| `ATERNOS_WATCHER_FOOTER_TEXT` | Footer text in the embed | `Aternos Watcher` |
| `ATERNOS_WATCHER_MENTION` | Content to ping (e.g. `@everyone`) | *None* |
| `ATERNOS_WATCHER_THUMBNAIL_URL` | Thumbnail image URL | *None* |

#### 🔍 Display Options
| Variable | Description | Default |
|----------|-------------|---------|
| `ATERNOS_WATCHER_SHOW_MOTD` | Show MOTD in embed | `true` |
| `ATERNOS_WATCHER_SHOW_PLAYERS` | Show player count in embed | `true` |

## 🚀 Running Locally

```bash
# Install dependencies and run with the variables from .env
uv run --env-file .env main.py
```

### Linting & Type Checking

```bash
uv run ruff format
uv run ruff check
uv run pyrefly check
```

## 🐳 Docker Deployment

The `Dockerfile` builds an Alpine image (about 90 MB) holding only Python, the locked dependencies and `main.py`, running as an unprivileged user.

### Docker Compose (Recommended)
Copy `.env.template` to `.env`, fill it, then build and run the provided `docker-compose.yml` with:
```bash
docker compose up -d --build
```
Rerun the same command after pulling new code to rebuild the image.

## ☁️ Dokploy Deployment

If you are using [Dokploy](https://dokploy.com), use the following configuration:

1. **Build Type**: Dockerfile
2. **Environment Variables**: Set the variables listed in the Configuration section.
