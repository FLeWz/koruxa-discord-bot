# koruxa-discord-bot

Discord bot that answers mentions through an Open WebUI model. It keeps one
Open WebUI chat per Discord user, logs Discord messages to daily files, and
uploads finished daily logs to an Open WebUI knowledge base.

## Features

- Reply to messages that mention the bot, using an Open WebUI model.
- Per-user chat history (user to chat ID map in `user_chat_ids.json`).
- Daily Discord message logs in `discord_logs/`. Old logs are uploaded to the
  Open WebUI knowledge base, then removed.
- Reaction roles setup.

## Commands

Prefix: `!`

- `!stop`: stop the current running task.
- `!reset`: delete your stored chat, so the next message starts a new one.
- `!reactionroles`: create reaction roles in the current channel. Needs
  `Manage Roles` for you and the bot, and the bot role must be above the
  roles it manages. Guild only.

## Requirements

- Python 3
- Packages: `discord.py`, `aiohttp`, `python-dotenv`
- A running Open WebUI instance and API key
- A Discord bot token

There is no `requirements.txt`; install the packages above manually.

## Setup

    python -m venv venv
    source venv/bin/activate
    pip install discord.py aiohttp python-dotenv
    cp .env.example .env
    # edit .env
    python main.py

## Configuration

Set in `.env` or the environment.

Required:

- `DISCORD_TOKEN`: Discord bot token.
- `OPENWEBUI_URL`: Open WebUI base URL.
- `OPENWEBUI_API_KEY`: Open WebUI API key.

Optional (default in brackets):

- `OPENWEBUI_MODEL` [`koruxa-bot`]
- `OPENWEBUI_KNOWLEDGE_ID`: knowledge base ID for log uploads.
- `OPENWEBUI_KNOWLEDGE_NAME` [`koruxa`]
- `MODEL_RETRY_DELAY` [`10`]
- `MODEL_MAX_RETRIES` [`30`]
- `TASK_POLL_INTERVAL` [`1`]
- `TASK_TIMEOUT` [`1200`]
- `USER_CHAT_MAP_FILE` [`user_chat_ids.json`]
- `DISCORD_LOG_TIMEZONE` [`Europe/Ljubljana`]
- `DISCORD_LOG_DIR` [`discord_logs`]
- `DISCORD_DIRECTORY_MAP_FILE` [`discord_directory_ids.json`]
- `REACTION_ROLES_FILE` [`reaction_roles.json`]

## Layout

- `main.py`: entry point.
- `bot.py`: bot class and wiring.
- `config.py`: environment config.
- `mydiscord/`: commands, events, messaging, reaction roles.
- `mylogger/`: Discord message logger.
- `openwebui/`: Open WebUI client, chat, knowledge upload.
- `services/`: daily log scheduler.
- `storage/`: JSON-backed stores.

## License

MIT. See `LICENSE`.
