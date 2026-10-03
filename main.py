#!/usr/bin/env python3

import asyncio
import json
import os
import re
import time
import uuid
import aiohttp
import discord

from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

load_dotenv()

# ============================================================
# Configuration
# ============================================================

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]

OPENWEBUI_URL = os.environ["OPENWEBUI_URL"].rstrip("/")

OPENWEBUI_API_KEY = os.environ["OPENWEBUI_API_KEY"]

OPENWEBUI_MODEL = os.getenv(
    "OPENWEBUI_MODEL",
    "koruxa-bot",
)

OPENWEBUI_KNOWLEDGE_ID = os.getenv(
    "OPENWEBUI_KNOWLEDGE_ID",
    "9e950084-7c30-4683-8861-7ba2b2740150",
)

OPENWEBUI_KNOWLEDGE_NAME = os.getenv(
    "OPENWEBUI_KNOWLEDGE_NAME",
    "koruxa",
)

MODEL_RETRY_DELAY = int(
    os.getenv("MODEL_RETRY_DELAY", "10")
)

MODEL_MAX_RETRIES = int(
    os.getenv("MODEL_MAX_RETRIES", "30")
)

TASK_POLL_INTERVAL = float(
    os.getenv("TASK_POLL_INTERVAL", "1")
)

TASK_TIMEOUT = int(
    os.getenv("TASK_TIMEOUT", "600")
)

USER_CHAT_MAP_FILE = os.getenv(
    "USER_CHAT_MAP_FILE",
    "user_chat_ids.json",
)

DISCORD_LOG_TIMEZONE = os.getenv(
    "DISCORD_LOG_TIMEZONE",
    "Europe/Ljubljana",
)

DISCORD_LOG_DIR = os.getenv(
    "DISCORD_LOG_DIR",
    "discord_logs",
)

DISCORD_DIRECTORY_MAP_FILE = os.getenv(
    "DISCORD_DIRECTORY_MAP_FILE",
    "discord_directory_ids.json",
)


# ============================================================
# Discord
# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)


# ============================================================
# State
# ============================================================

model_lock = asyncio.Lock()

current_task: asyncio.Task | None = None
current_chat_id: str | None = None
current_channel: discord.abc.Messageable | None = None


# ============================================================
# User -> Open WebUI chat mapping
# ============================================================

def load_user_chat_ids() -> dict[int, str]:

    if not os.path.exists(USER_CHAT_MAP_FILE):
        return {}

    try:

        with open(
            USER_CHAT_MAP_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        return {
            int(user_id): str(chat_id)
            for user_id, chat_id in data.items()
        }

    except (
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:

        print(
            f"Could not load "
            f"{USER_CHAT_MAP_FILE}: {exc}"
        )

        return {}


def save_user_chat_ids(
    mappings: dict[int, str],
):

    data = {
        str(user_id): chat_id
        for user_id, chat_id in mappings.items()
    }

    temporary_file = (
        f"{USER_CHAT_MAP_FILE}.tmp"
    )

    try:

        with open(
            temporary_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                data,
                file,
                indent=2,
                sort_keys=True,
            )

            file.write("\n")

        os.replace(
            temporary_file,
            USER_CHAT_MAP_FILE,
        )

    except OSError as exc:

        print(
            f"Could not save "
            f"{USER_CHAT_MAP_FILE}: {exc}"
        )


user_chat_ids = load_user_chat_ids()

print(
    f"Loaded {len(user_chat_ids)} user/chat "
    f"mappings from {USER_CHAT_MAP_FILE}"
)


def get_user_chat_id(
    user: discord.abc.User,
) -> str | None:

    return user_chat_ids.get(user.id)


def set_user_chat_id(
    user: discord.abc.User,
    chat_id: str,
):

    user_chat_ids[user.id] = chat_id

    save_user_chat_ids(
        user_chat_ids
    )


def delete_user_chat_id(
    user: discord.abc.User,
):

    if user.id in user_chat_ids:

        del user_chat_ids[user.id]

        save_user_chat_ids(
            user_chat_ids
        )


# ============================================================
# Discord message logging -> Open WebUI Knowledge Base
# ============================================================

log_timezone = ZoneInfo(
    DISCORD_LOG_TIMEZONE
)

discord_log_root = Path(
    DISCORD_LOG_DIR
)

discord_log_root.mkdir(
    parents=True,
    exist_ok=True,
)


def load_directory_ids() -> dict[str, str]:
    if not os.path.exists(
        DISCORD_DIRECTORY_MAP_FILE
    ):
        return {}

    try:

        with open(
            DISCORD_DIRECTORY_MAP_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):
            return {}

        return {
            str(key): str(value)
            for key, value in data.items()
        }

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:

        print(
            f"Could not load "
            f"{DISCORD_DIRECTORY_MAP_FILE}: "
            f"{exc}"
        )

        return {}


def save_directory_ids(
    mappings: dict[str, str],
):

    temporary_file = (
        f"{DISCORD_DIRECTORY_MAP_FILE}.tmp"
    )

    try:

        with open(
            temporary_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                mappings,
                file,
                indent=2,
                sort_keys=True,
            )

            file.write("\n")

        os.replace(
            temporary_file,
            DISCORD_DIRECTORY_MAP_FILE,
        )

    except OSError as exc:

        print(
            f"Could not save "
            f"{DISCORD_DIRECTORY_MAP_FILE}: "
            f"{exc}"
        )


discord_directory_ids = load_directory_ids()


def get_log_now() -> datetime:
    return datetime.now(
        log_timezone
    )


def get_user_log_directory(
    user: discord.abc.User,
) -> Path:

    # Discord usernames can contain characters that are
    # inconvenient in filenames/directories.
    safe_username = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        user.name,
    ).strip()

    if not safe_username:
        safe_username = "unknown"

    directory_name = (
        f"{user.id} {safe_username}"
    )

    path = (
        discord_log_root
        / directory_name
    )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def get_daily_log_path(
    user: discord.abc.User,
    date_string: str,
) -> Path:

    directory = get_user_log_directory(
        user
    )

    return directory / (
        f"{date_string}.md"
    )


def get_all_users_daily_log_path(
    date_string: str,
) -> Path:

    # Aggregate daily log lives directly inside
    # discord-users, NOT inside a user directory.
    return discord_log_root / (
        f"{date_string}.md"
    )


def format_discord_log_message(
    message: discord.Message,
    timestamp: datetime,
) -> str:

    username = (
        message.author.name
    )

    display_name = (
        message.author.display_name
    )

    content = message.content.strip()

    if not content:
        content = "(no text content)"

    # Keep mentions, attachments, etc. visible in the log.
    attachments = ""

    if message.attachments:

        attachment_lines = [
            attachment.url
            for attachment in message.attachments
        ]

        attachments = (
            "\n\nAttachments:\n"
            + "\n".join(
                f"- {url}"
                for url in attachment_lines
            )
        )

    return (
        f"### "
        f"{timestamp.strftime('%H:%M:%S %Z')}"
        f" — "
        f"{display_name} "
        f"(`{username}`, Discord ID "
        f"`{message.author.id}`)\n\n"
        f"{content}"
        f"{attachments}\n\n"
        f"---\n\n"
    )


def append_discord_message_to_log(
    message: discord.Message,
):

    now = get_log_now()

    date_string = now.strftime(
        "%Y-%m-%d"
    )

    # ========================================================
    # 1. Existing per-user daily log
    # ========================================================

    user_path = get_daily_log_path(
        message.author,
        date_string,
    )

    is_new_user_file = not user_path.exists()

    with open(
        user_path,
        "a",
        encoding="utf-8",
    ) as file:

        if is_new_user_file:

            file.write(
                f"# Discord messages — "
                f"{date_string}\n\n"
            )

            file.write(
                f"Discord user: "
                f"**{message.author.display_name}**\n"
            )

            file.write(
                f"Discord ID: "
                f"`{message.author.id}`\n\n"
            )

            file.write(
                "---\n\n"
            )

        file.write(
            format_discord_log_message(
                message,
                now,
            )
        )

    # ========================================================
    # 2. Aggregate daily log for ALL users
    # ========================================================

    all_users_path = (
        get_all_users_daily_log_path(
            date_string
        )
    )

    is_new_all_users_file = (
        not all_users_path.exists()
    )

    with open(
        all_users_path,
        "a",
        encoding="utf-8",
    ) as file:

        if is_new_all_users_file:

            file.write(
                f"# All Discord messages — "
                f"{date_string}\n\n"
            )

            file.write(
                "---\n\n"
            )

        file.write(
            format_discord_log_message(
                message,
                now,
            )
        )

    return user_path


# ============================================================
# Open WebUI Knowledge directories
# ============================================================

async def create_knowledge_directory(
    session: aiohttp.ClientSession,
    name: str,
    parent_id: str | None = None,
) -> str:

    url = (
        f"{OPENWEBUI_URL}"
        f"/api/v1/knowledge/"
        f"{OPENWEBUI_KNOWLEDGE_ID}"
        f"/dirs/create"
    )

    payload = {
        "name": name,
    }

    if parent_id is not None:
        payload["parent_id"] = parent_id

    async with session.post(
        url,
        headers=api_headers(),
        json=payload,
    ) as response:

        data = await read_json_response(
            response
        )

    directory = data.get(
        "directory",
        data,
    )

    if not isinstance(directory, dict):
        raise RuntimeError(
            "Open WebUI returned an unexpected "
            "directory creation response."
        )

    directory_id = (
        directory.get("id")
        or data.get("id")
    )

    if not directory_id:
        raise RuntimeError(
            "Open WebUI did not return a "
            "directory ID."
        )

    return str(
        directory_id
    )


async def ensure_discord_users_directory(
    session: aiohttp.ClientSession,
) -> str:

    key = "root"

    existing_id = discord_directory_ids.get(
        key
    )

    if existing_id:
        return existing_id

    print(
        "Creating Open WebUI knowledge "
        "directory: discord-users"
    )

    directory_id = await create_knowledge_directory(
        session=session,
        name="discord-users",
    )

    discord_directory_ids[key] = directory_id

    save_directory_ids(
        discord_directory_ids
    )

    print(
        f"Created discord-users directory "
        f"{directory_id}"
    )

    return directory_id


async def ensure_user_knowledge_directory(
    session: aiohttp.ClientSession,
    user: discord.abc.User,
) -> str:

    root_id = (
        await ensure_discord_users_directory(
            session
        )
    )

    key = str(user.id)

    existing_id = discord_directory_ids.get(
        key
    )

    if existing_id:
        return existing_id

    safe_username = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "_",
        user.name,
    ).strip()

    if not safe_username:
        safe_username = "unknown"

    directory_name = (
        f"{user.id} {safe_username}"
    )

    print(
        f"Creating Open WebUI knowledge "
        f"directory: {directory_name}"
    )

    directory_id = (
        await create_knowledge_directory(
            session=session,
            name=directory_name,
            parent_id=root_id,
        )
    )

    discord_directory_ids[key] = (
        directory_id
    )

    save_directory_ids(
        discord_directory_ids
    )

    print(
        f"Created Discord user directory "
        f"{directory_id} "
        f"for {user.id}"
    )

    return directory_id


# ============================================================
# Upload daily log to Open WebUI
# ============================================================

async def upload_log_file(
    session: aiohttp.ClientSession,
    user_id: int,
    username: str,
    file_path: Path,
):

    if not file_path.exists():
        return

    root_id = (
        await ensure_discord_users_directory(
            session
        )
    )

    user_key = str(user_id)

    directory_id = discord_directory_ids.get(
        user_key
    )

    if not directory_id:

        safe_username = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            username,
        ).strip()

        if not safe_username:
            safe_username = "unknown"

        directory_id = (
            await create_knowledge_directory(
                session=session,
                name=f"{user_id} {safe_username}",
                parent_id=root_id,
            )
        )

        discord_directory_ids[
            user_key
        ] = directory_id

        save_directory_ids(
            discord_directory_ids
        )

    url = (
        f"{OPENWEBUI_URL}"
        "/api/v1/files/"
    )

    headers = {
        "Authorization": (
            f"Bearer {OPENWEBUI_API_KEY}"
        ),
        "Accept": "application/json",
    }

    form = aiohttp.FormData()

    form.add_field(
        "file",
        file_path.read_bytes(),
        filename=file_path.name,
        content_type="text/markdown",
    )

    form.add_field(
        "metadata",
        json.dumps(
            {
                "knowledge_id": (
                    OPENWEBUI_KNOWLEDGE_ID
                ),
                "directory_id": directory_id,
            }
        ),
    )

    async with session.post(
        url,
        headers=headers,
        data=form,
    ) as response:

        data = await read_json_response(
            response
        )

    file_id = (
        data.get("id")
        or data.get("file", {}).get("id")
    )

    print(
        f"Uploaded Discord log "
        f"{file_path} "
        f"for user {user_id}"
        + (
            f" as file {file_id}"
            if file_id
            else ""
        )
    )


async def upload_all_users_daily_log(
    session: aiohttp.ClientSession,
    file_path: Path,
):

    if not file_path.exists():
        return

    root_id = (
        await ensure_discord_users_directory(
            session
        )
    )

    url = (
        f"{OPENWEBUI_URL}"
        "/api/v1/files/"
    )

    headers = {
        "Authorization": (
            f"Bearer {OPENWEBUI_API_KEY}"
        ),
        "Accept": "application/json",
    }

    form = aiohttp.FormData()

    form.add_field(
        "file",
        file_path.read_bytes(),
        filename=file_path.name,
        content_type="text/markdown",
    )

    form.add_field(
        "metadata",
        json.dumps(
            {
                "knowledge_id": (
                    OPENWEBUI_KNOWLEDGE_ID
                ),
                "directory_id": root_id,
            }
        ),
    )

    async with session.post(
        url,
        headers=headers,
        data=form,
    ) as response:

        data = await read_json_response(
            response
        )

    file_id = (
        data.get("id")
        or data.get("file", {}).get("id")
    )

    print(
        f"Uploaded aggregate Discord log "
        f"{file_path}"
        + (
            f" as file {file_id}"
            if file_id
            else ""
        )
    )


async def upload_old_logs(
    session: aiohttp.ClientSession,
):

    today = get_log_now().date()

    for user_directory in discord_log_root.iterdir():

        if not user_directory.is_dir():
            continue

        parsed = get_user_from_directory_name(
            user_directory.name
        )

        if parsed is None:
            continue

        user_id, username = parsed

        for log_file in user_directory.glob(
            "*.md"
        ):

            try:

                file_date = datetime.strptime(
                    log_file.stem,
                    "%Y-%m-%d",
                ).date()

            except ValueError:

                continue

            if file_date >= today:
                continue

            try:

                await upload_log_file(
                    session=session,
                    user_id=user_id,
                    username=username,
                    file_path=log_file,
                )

            except Exception as exc:

                print(
                    f"Failed to upload old Discord "
                    f"log {log_file}: "
                    f"{type(exc).__name__}: {exc}"
                )


async def upload_old_all_users_logs(
    session: aiohttp.ClientSession,
):

    today = get_log_now().date()

    for log_file in discord_log_root.glob(
        "*.md"
    ):

        try:

            file_date = datetime.strptime(
                log_file.stem,
                "%Y-%m-%d",
            ).date()

        except ValueError:

            continue

        if file_date >= today:
            continue

        try:

            await upload_all_users_daily_log(
                session=session,
                file_path=log_file,
            )

        except Exception as exc:

            print(
                f"Failed to upload old aggregate "
                f"Discord log {log_file}: "
                f"{type(exc).__name__}: {exc}"
            )


# ============================================================
# Find Discord user from local directory name
# ============================================================

def get_user_from_directory_name(
    directory_name: str,
) -> tuple[int, str] | None:

    match = re.match(
        r"^(\d+)(?:\s+(.*))?$",
        directory_name,
    )

    if not match:
        return None

    try:

        user_id = int(
            match.group(1)
        )

    except ValueError:

        return None

    username = (
        match.group(2)
        or "unknown"
    )

    return (
        user_id,
        username,
    )


# ============================================================
# Daily log finalizer
# ============================================================

async def finalize_previous_day_logs():

    timeout = aiohttp.ClientTimeout(
        total=None
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        await upload_old_logs(
            session
        )
        await upload_old_all_users_logs(session)


async def daily_log_scheduler():

    while True:

        now = get_log_now()

        # Calculate the next local midnight.
        tomorrow = (
            now.date()
            .toordinal()
            + 1
        )

        next_midnight = datetime.fromordinal(
            tomorrow
        ).replace(
            tzinfo=log_timezone
        )

        seconds_until_midnight = (
            next_midnight - now
        ).total_seconds()

        # Wake slightly after midnight.
        await asyncio.sleep(
            max(
                1,
                seconds_until_midnight + 2,
            )
        )

        try:

            print(
                "Daily Discord log rollover: "
                "uploading previous day's logs."
            )

            await finalize_previous_day_logs()

        except Exception as exc:

            print(
                f"Daily Discord log rollover "
                f"failed: "
                f"{type(exc).__name__}: {exc}"
            )

# ============================================================
# HTTP helpers
# ============================================================

def api_headers() -> dict[str, str]:

    return {
        "Authorization": (
            f"Bearer {OPENWEBUI_API_KEY}"
        ),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def read_json_response(
    response: aiohttp.ClientResponse,
) -> dict:

    body = await response.text()

    if response.status >= 400:

        raise RuntimeError(
            f"HTTP {response.status}: {body}"
        )

    try:

        data = json.loads(body)

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            f"Open WebUI returned invalid JSON: "
            f"{body[:2000]}"
        ) from exc

    if not isinstance(data, dict):

        raise RuntimeError(
            "Open WebUI returned unexpected JSON."
        )

    return data


# ============================================================
# Discord message helpers
# ============================================================

def clean_message(
    message: discord.Message,
) -> str:

    text = message.content

    if bot.user:

        text = re.sub(
            rf"<@!?{bot.user.id}>",
            "",
            text,
            flags=re.IGNORECASE,
        )

    return text.strip()


async def send_long_message(
    channel: discord.abc.Messageable,
    text: str,
):

    if not text:
        return

    while len(text) > 2000:

        split_at = text.rfind(
            "\n",
            0,
            2000,
        )

        if split_at < 1000:

            split_at = text.rfind(
                " ",
                0,
                2000,
            )

        if split_at <= 0:

            split_at = 2000

        await channel.send(
            text[:split_at]
        )

        text = text[
            split_at:
        ].lstrip()

    if text:

        await channel.send(
            text
        )


# ============================================================
# Message construction
# ============================================================

def make_user_message(
    message_id: str,
    content: str,
    parent_id: str | None,
    assistant_id: str,
) -> dict:

    return {
        "id": message_id,
        "role": "user",
        "content": content,
        "timestamp": int(time.time()),
        "models": [
            OPENWEBUI_MODEL
        ],
        "parentId": parent_id,
        "childrenIds": [
            assistant_id
        ],
    }


def make_assistant_message(
    message_id: str,
    parent_id: str,
) -> dict:

    return {
        "id": message_id,
        "role": "assistant",
        "content": "",
        "parentId": parent_id,
        "childrenIds": [],
        "model": OPENWEBUI_MODEL,
        "modelName": OPENWEBUI_MODEL,
        "modelIdx": 0,
        "done": False,
        "timestamp": int(time.time()) + 1,
    }


# ============================================================
# Create new Open WebUI chat
# ============================================================

async def create_chat(
    session: aiohttp.ClientSession,
    prompt: str,
) -> tuple[str, str, str]:

    chat_id = str(uuid.uuid4())

    user_message_id = str(uuid.uuid4())

    assistant_message_id = str(uuid.uuid4())

    user_message = make_user_message(
        message_id=user_message_id,
        content=prompt,
        parent_id=None,
        assistant_id=assistant_message_id,
    )

    assistant_message = make_assistant_message(
        message_id=assistant_message_id,
        parent_id=user_message_id,
    )

    payload = {
        "chat": {
            "id": chat_id,

            "title": prompt[:80],

            "models": [
                OPENWEBUI_MODEL
            ],

            "history": {
                "currentId": assistant_message_id,

                "messages": {
                    user_message_id: user_message,
                    assistant_message_id: assistant_message,
                },
            },
        }
    }

    url = (
        f"{OPENWEBUI_URL}"
        "/v1/chats/new"
    )

    async with session.post(
        url,
        headers=api_headers(),
        json=payload,
    ) as response:

        data = await read_json_response(
            response
        )

    returned_chat_id = (
        data.get("id")
        or data.get("chat", {}).get("id")
        or chat_id
    )

    returned_chat_id = str(
        returned_chat_id
    )

    return (
        returned_chat_id,
        user_message_id,
        assistant_message_id,
    )


# ============================================================
# Retrieve chat
#
# Used only when:
# - validating an existing chat
# - retrieving the completed assistant response
#
# It is NOT used to reconstruct history for the next request.
# ============================================================

async def get_chat(
    session: aiohttp.ClientSession,
    chat_id: str,
) -> dict:

    url = (
        f"{OPENWEBUI_URL}"
        f"/v1/chats/{chat_id}"
    )

    async with session.get(
        url,
        headers=api_headers(),
    ) as response:

        body = await response.text()

        if response.status >= 400:

            raise RuntimeError(
                f"Could not retrieve chat "
                f"HTTP {response.status}: "
                f"{body}"
            )

        try:

            return json.loads(body)

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "Open WebUI returned invalid "
                "chat JSON."
            ) from exc


# ============================================================
# Validate existing chat
# ============================================================

async def get_existing_chat(
    session: aiohttp.ClientSession,
    chat_id: str,
) -> dict | None:

    try:

        return await get_chat(
            session,
            chat_id,
        )

    except RuntimeError as exc:

        error = str(exc)

        if (
            "HTTP 401" in error
            or "HTTP 403" in error
            or "HTTP 404" in error
        ):

            print(
                f"[{chat_id}] "
                f"Existing chat is inaccessible: "
                f"{error}"
            )

            return None

        raise


# ============================================================
# Update existing Open WebUI chat
#
# IMPORTANT:
#
# We only send the NEW user message and NEW assistant
# placeholder here.
#
# We do NOT send the old chat history.
# ============================================================

async def add_message_to_chat(
    session: aiohttp.ClientSession,
    chat_id: str,
    prompt: str,
    parent_id: str,
) -> tuple[str, str]:

    user_message_id = str(
        uuid.uuid4()
    )

    assistant_message_id = str(
        uuid.uuid4()
    )

    user_message = make_user_message(
        message_id=user_message_id,
        content=prompt,
        parent_id=parent_id,
        assistant_id=assistant_message_id,
    )

    assistant_message = make_assistant_message(
        message_id=assistant_message_id,
        parent_id=user_message_id,
    )

    update_payload = {
        "chat": {
            "history": {
                "currentId": assistant_message_id,

                "messages": {
                    user_message_id: user_message,
                    assistant_message_id: assistant_message,
                },
            }
        }
    }

    url = (
        f"{OPENWEBUI_URL}"
        f"/v1/chats/{chat_id}"
    )

    async with session.post(
        url,
        headers=api_headers(),
        json=update_payload,
    ) as response:

        await read_json_response(
            response
        )

    return (
        user_message_id,
        assistant_message_id,
    )


# ============================================================
# Start completion
# ============================================================

async def start_completion(
    session: aiohttp.ClientSession,
    chat_id: str,
    user_message_id: str,
    assistant_message_id: str,
    prompt: str,
    parent_id: str | None = None,
) -> dict:

    url = (
        f"{OPENWEBUI_URL}"
        "/chat/completions"
    )

    # Keep the same session for the same Open WebUI chat.
    session_id = f"discord-{chat_id}"

    user_message = {
        "id": user_message_id,

        "parentId": parent_id,

        "childrenIds": [
            assistant_message_id
        ],

        "role": "user",

        "content": prompt,

        "timestamp": int(time.time()),

        "models": [
            OPENWEBUI_MODEL
        ],
    }

    payload = {
        "stream": True,

        "model": OPENWEBUI_MODEL,

        # ====================================================
        # IMPORTANT:
        #
        # ONLY THE CURRENT MESSAGE IS SENT.
        #
        # No previous messages.
        # ====================================================

        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],

        # Same Open WebUI chat for all turns.
        "chat_id": chat_id,

        "id": assistant_message_id,

        # Stable session ID for this chat.
        "session_id": session_id,

        "user_message": user_message,

        "params": {
            "tool_approval_mode": "full"
        },

        "features": {
            "voice": False,
            "image_generation": False,
            "code_interpreter": True,
            "web_search": False,
            "memory": True,
        },

        "variables": {},

        "chat_variables": {},

        "model_item": {
            "id": OPENWEBUI_MODEL,
            "name": OPENWEBUI_MODEL,
            "object": "model",
        },

        "files": [
            {
                "type": "collection",
                "id": OPENWEBUI_KNOWLEDGE_ID,
                "status": "processed",
            }
        ],

        "background_tasks": {
            "title_generation": False,
            "tags_generation": False,
            "follow_up_generation": False,
        },
    }

    async with session.post(
        url,
        headers=api_headers(),
        json=payload,
    ) as response:

        body = await response.text()

        if response.status in (
            502,
            503,
            504,
        ):

            raise RuntimeError(
                f"HTTP {response.status}"
            )

        if response.status >= 400:

            raise RuntimeError(
                f"Open WebUI returned "
                f"HTTP {response.status}: {body}"
            )

        try:

            data = json.loads(body)

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                f"Invalid JSON from Open WebUI: "
                f"{body[:2000]}"
            ) from exc

    return data


# ============================================================
# Poll asynchronous Open WebUI task
# ============================================================

async def wait_for_task(
    session: aiohttp.ClientSession,
    chat_id: str,
    task_ids: list[str],
):

    if not task_ids:

        return

    url = (
        f"{OPENWEBUI_URL}"
        f"/tasks/chat/{chat_id}"
    )

    started = time.monotonic()

    while True:

        elapsed = (
            time.monotonic() - started
        )

        if elapsed > TASK_TIMEOUT:

            raise TimeoutError(
                f"Open WebUI task timed out "
                f"after {TASK_TIMEOUT}s."
            )

        async with session.get(
            url,
            headers=api_headers(),
        ) as response:

            body = await response.text()

            if response.status >= 400:

                raise RuntimeError(
                    f"Task polling failed "
                    f"HTTP {response.status}: "
                    f"{body}"
                )

            try:

                data = json.loads(body)

            except json.JSONDecodeError as exc:

                raise RuntimeError(
                    f"Invalid task response: "
                    f"{body[:1000]}"
                ) from exc

        active_tasks = data.get(
            "task_ids",
            [],
        )

        if not active_tasks:

            return

        still_running = [
            task_id
            for task_id in task_ids
            if task_id in active_tasks
        ]

        if not still_running:

            return

        await asyncio.sleep(
            TASK_POLL_INTERVAL
        )


# ============================================================
# Extract final assistant content
# ============================================================

def extract_assistant_content(
    chat_data: dict,
    assistant_message_id: str,
) -> str:

    chat = chat_data.get("chat")

    if not isinstance(chat, dict):
        return ""

    history = chat.get("history")

    if not isinstance(history, dict):
        return ""

    messages = history.get("messages")

    if not isinstance(messages, dict):
        return ""

    message = messages.get(
        assistant_message_id
    )

    if not isinstance(message, dict):

        candidates = []

        for item in messages.values():

            if not isinstance(item, dict):
                continue

            if item.get("role") != "assistant":
                continue

            content = item.get("content")

            if not content:
                continue

            candidates.append(item)

        if not candidates:
            return ""

        candidates.sort(
            key=lambda item: item.get(
                "timestamp",
                0,
            )
        )

        message = candidates[-1]

    # Do not read reasoning_content.
    content = message.get(
        "content"
    )

    if isinstance(content, str):

        return content.strip()

    if isinstance(content, list):

        parts = []

        for item in content:

            if not isinstance(item, dict):
                continue

            text = item.get("text")

            if isinstance(text, str):

                parts.append(text)

        return "".join(parts).strip()

    return ""


# ============================================================
# Ask Open WebUI
# ============================================================

async def ask_openwebui(
    prompt: str,
    user: discord.abc.User,
) -> str:

    existing_chat_id = get_user_chat_id(
        user
    )

    timeout = aiohttp.ClientTimeout(
        total=None
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        chat_data = None

        # ====================================================
        # Try to reuse existing chat.
        # ====================================================

        if existing_chat_id:

            print(
                f"[{existing_chat_id}] "
                f"Checking existing chat"
            )

            chat_data = await get_existing_chat(
                session,
                existing_chat_id,
            )

            if chat_data is None:

                print(
                    f"[{existing_chat_id}] "
                    f"Removing inaccessible chat "
                    f"from local mapping."
                )

                delete_user_chat_id(
                    user
                )

                existing_chat_id = None

        # ====================================================
        # Create a new chat.
        # ====================================================

        if existing_chat_id is None:

            (
                chat_id,
                user_message_id,
                assistant_message_id,
            ) = await create_chat(
                session,
                prompt,
            )

            set_user_chat_id(
                user,
                chat_id,
            )

            # There is no parent for the first message.
            parent_id = None

            print(
                f"[{chat_id}] "
                f"Created new Open WebUI chat"
            )

        # ====================================================
        # Existing conversation.
        # ====================================================

        else:

            chat_id = existing_chat_id

            # ------------------------------------------------
            # Get the current message ID from the existing
            # chat ONLY to establish the parent relationship.
            #
            # We do not use its history for the completion.
            # ------------------------------------------------

            chat = chat_data.get("chat")

            if not isinstance(chat, dict):

                raise RuntimeError(
                    "Open WebUI chat has no chat object."
                )

            history = chat.get("history")

            if not isinstance(history, dict):

                raise RuntimeError(
                    "Open WebUI chat has no history."
                )

            parent_id = history.get(
                "currentId"
            )

            if not parent_id:

                raise RuntimeError(
                    "Open WebUI chat has no currentId."
                )

            (
                user_message_id,
                assistant_message_id,
            ) = await add_message_to_chat(
                session=session,
                chat_id=chat_id,
                prompt=prompt,
                parent_id=parent_id,
            )

            print(
                f"[{chat_id}] "
                f"Continuing existing chat"
            )

        # ====================================================
        # Start completion.
        #
        # ONLY THE CURRENT USER MESSAGE IS SENT.
        # ====================================================

        result = None

        for attempt in range(
            MODEL_MAX_RETRIES + 1
        ):

            try:

                result = await start_completion(
                    session=session,
                    chat_id=chat_id,
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                    prompt=prompt,
                    parent_id=parent_id,
                )

                break

            except RuntimeError as exc:

                error = str(exc)

                retryable = (
                    "HTTP 502" in error
                    or "HTTP 503" in error
                    or "HTTP 504" in error
                )

                if not retryable:
                    raise

                if attempt >= MODEL_MAX_RETRIES:
                    raise

                print(
                    f"[{chat_id}] "
                    f"{exc}"
                )

                print(
                    f"[{chat_id}] "
                    f"Retrying in "
                    f"{MODEL_RETRY_DELAY}s..."
                )

                await asyncio.sleep(
                    MODEL_RETRY_DELAY
                )

        if result is None:

            raise RuntimeError(
                "Open WebUI returned no completion result."
            )

        # ====================================================
        # Handle asynchronous task.
        # ====================================================

        task_ids = result.get(
            "task_ids",
            [],
        )

        if task_ids:

            await wait_for_task(
                session=session,
                chat_id=chat_id,
                task_ids=task_ids,
            )

        # ====================================================
        # Retrieve completed assistant response.
        #
        # This GET is only to retrieve the newly generated
        # answer. It is NOT used to construct the next request.
        # ====================================================

        chat_data = await get_chat(
            session,
            chat_id,
        )

        response = extract_assistant_content(
            chat_data,
            assistant_message_id,
        )

        if not response:

            print(
                f"[{chat_id}] "
                f"No assistant content found."
            )

            print(
                json.dumps(
                    chat_data,
                    indent=2,
                    ensure_ascii=False,
                )
            )

            raise RuntimeError(
                "Open WebUI completed the request "
                "but returned no assistant content."
            )

        print(
            f"[{chat_id}] "
            f"Final response:"
        )

        print(response)

        return response


# ============================================================
# Commands
# ============================================================

@bot.command(name="stop")
async def stop_command(
    ctx: commands.Context,
):

    global current_task

    if (
        current_task is None
        or current_task.done()
    ):

        await ctx.send(
            "There is no active task."
        )

        return

    stopped_chat_id = current_chat_id

    current_task.cancel()

    await ctx.send(
        "🛑 Stopping the current task"
        + (
            f" (`{stopped_chat_id}`)"
            if stopped_chat_id
            else ""
        )
        + "."
    )


@bot.command(name="reset")
async def reset_command(
    ctx: commands.Context,
):

    user_id = ctx.author.id

    old_chat_id = user_chat_ids.pop(
        user_id,
        None,
    )

    save_user_chat_ids(
        user_chat_ids
    )

    if old_chat_id is None:

        await ctx.send(
            "You don't currently have a chat memory."
        )

        return

    await ctx.send(
        "🧹 Your chat memory has been reset. "
        "Your next message will start a new conversation."
    )

    print(
        f"Reset Open WebUI chat "
        f"{old_chat_id} "
        f"for Discord user {user_id}"
    )


# ============================================================
# Discord events
# ============================================================

daily_log_task: asyncio.Task | None = None


@bot.event
async def on_ready():

    global daily_log_task

    print(
        f"Logged in as {bot.user}"
    )

    # Upload anything from previous days that was
    # left locally because of a restart/offline period.
    try:

        await finalize_previous_day_logs()

    except Exception as exc:

        print(
            f"Could not finalize old Discord logs: "
            f"{type(exc).__name__}: {exc}"
        )

    if (
        daily_log_task is None
        or daily_log_task.done()
    ):

        daily_log_task = asyncio.create_task(
            daily_log_scheduler()
        )


@bot.event
async def on_message(
    message: discord.Message,
):

    if message.author.bot:
        return

    await bot.process_commands(
        message
    )

    if message.content.startswith(
        bot.command_prefix
    ):
        return

    # ========================================================
    # Log every Discord user's message.
    # ========================================================

    try:

        log_path = (
            append_discord_message_to_log(
                message
            )
        )

        print(
            f"Logged Discord message "
            f"from {message.author.id} "
            f"to {log_path}"
        )

    except Exception as exc:

        print(
            f"Failed to log Discord message: "
            f"{type(exc).__name__}: {exc}"
        )

    if bot.user not in message.mentions:
        return

    prompt = clean_message(
        message
    )

    if not prompt:
        return

    if model_lock.locked():

        await message.channel.send(
            "Another query is currently "
            "being processed. Your request "
            "has been queued."
        )

    async with model_lock:

        global current_task
        global current_chat_id
        global current_channel

        current_chat_id = get_user_chat_id(
            message.author
        )

        current_channel = (
            message.channel
        )

        print(
            f"\n[{current_chat_id}] "
            f"Asking: "
            f"{prompt}"
        )

        current_task = asyncio.create_task(
            ask_openwebui(
                prompt,
                message.author,
            )
        )

        try:

            response = await current_task

        except asyncio.CancelledError:

            try:

                await message.channel.send(
                    "🛑 Current task stopped."
                )

            except discord.HTTPException:

                pass

            return

        except Exception as exc:

            print(
                f"Open WebUI error: "
                f"{type(exc).__name__}: {exc}"
            )

            try:

                await message.channel.send(
                    "Sorry, I couldn't get a "
                    "response from the model."
                )

            except discord.HTTPException:

                pass

            return

        finally:

            if (
                current_task
                is asyncio.current_task()
            ):

                current_task = None
                current_chat_id = None
                current_channel = None

        if response:

            await send_long_message(
                message.channel,
                response,
            )

        else:

            await message.channel.send(
                "(The model returned an empty response.)"
            )


# ============================================================
# Start
# ============================================================

bot.run(DISCORD_TOKEN)
