# 🚀 Aternos Watcher

A strictly typed Python 3.13 monitor for Aternos Minecraft servers. It intelligently filters out "Ghost Proxies" (Aternos servers that appear online but are actually in a standby/offline state).

## ✨ Features

- **Ghost Proxy Filtering**: Detects the difference between a truly online server and the Aternos "Offline" MOTD.
- **Discord Notifications**: Standardized embeds for state changes (Online/Offline).
- **Debounce Logic**: Prevents notification spam during server startup flickers.
- **Strictly Typed**: Built with Python 3.13 type hints for reliability.

## 🛠️ Installation & Setup

### Prerequisites
- [uv](https://github.com/astral-sh/uv) (Recommended) or Python 3.13+

### Configuration
Create a `.env` file or set the following environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `ATERNOS_WATCHER_HOST` | Your Aternos server address | `localhost` |
| `ATERNOS_WATCHER_PORT` | Server port | `25565` |
| `ATERNOS_WATCHER_WEBHOOK_URL` | Discord Webhook URL | *Required* |
| `ATERNOS_WATCHER_UPDATE_TIME` | Polling interval in seconds | `30` |

## 🚀 Running Locally

```bash
# Install dependencies and run
uv run main.py
```

## 🐳 Docker Deployment

### Docker Compose (Recommended)
Create a `docker-compose.yml` file:

```yaml
services:
  watcher:
    image: ghcr.io/astral-sh/uv:python3.13-bookworm-slim
    container_name: aternos-watcher
    restart: unless-stopped
    volumes:
      - .:/app
    working_dir: /app
    environment:
      - ATERNOS_WATCHER_HOST=your-server.aternos.me
      - ATERNOS_WATCHER_WEBHOOK_URL=https://discord.com/api/webhooks/...
    command: uv run main.py
```

Run with:
```bash
docker compose up -d
```

## ☁️ Dokploy Deployment

If you are using [Dokploy](https://dokploy.com), use the following configuration:

1. **Build Type**: Nixpacks
2. **Environment Variables**: Set the variables listed in the Configuration section.
3. **Start Command**: `uv run main.py`
