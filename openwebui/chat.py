import asyncio
import json
import time

import aiohttp
import discord

from .client import OpenWebUIClient
from .models import (
    create_message_ids,
    make_assistant_message,
    make_user_message,
)
from storage.user_chats import UserChatStore


class OpenWebUIChatService:
    def __init__(
        self,
        client: OpenWebUIClient,
        user_chats: UserChatStore,
        model: str,
        knowledge_id: str,
        retry_delay: int,
        max_retries: int,
        task_poll_interval: float,
        task_timeout: int,
    ):
        self.client = client
        self.user_chats = user_chats

        self.model = model
        self.knowledge_id = knowledge_id

        self.retry_delay = retry_delay
        self.max_retries = max_retries

        self.task_poll_interval = (
            task_poll_interval
        )
        self.task_timeout = task_timeout

    async def ask(
        self,
        prompt: str,
        user: discord.abc.User,
    ) -> str:
        timeout = aiohttp.ClientTimeout(
            total=None
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            chat_id = self.user_chats.get(user)

            chat_data = None

            if chat_id:
                print(
                    f"[{chat_id}] "
                    "Checking existing chat"
                )

                chat_data = (
                    await self.get_existing_chat(
                        session,
                        chat_id,
                    )
                )

                if chat_data is None:
                    self.user_chats.delete(user)
                    chat_id = None

            if chat_id is None:
                (
                    chat_id,
                    ids,
                    parent_id,
                ) = await self.create_chat(
                    session,
                    prompt,
                )

                self.user_chats.set(
                    user,
                    chat_id,
                )

                print(
                    f"[{chat_id}] "
                    "Created new Open WebUI chat"
                )

            else:
                parent_id = (
                    self.get_current_message_id(
                        chat_data
                    )
                )

                ids = await self.add_message(
                    session=session,
                    chat_id=chat_id,
                    prompt=prompt,
                    parent_id=parent_id,
                )

                print(
                    f"[{chat_id}] "
                    "Continuing existing chat"
                )

            result = await self._complete_with_retry(
                session=session,
                chat_id=chat_id,
                ids=ids,
                prompt=prompt,
                parent_id=parent_id,
            )

            task_ids = result.get(
                "task_ids",
                [],
            )

            if task_ids:
                await self.wait_for_tasks(
                    session,
                    chat_id,
                    task_ids,
                )

            chat_data = await self.get_chat(
                session,
                chat_id,
            )

            response = self.extract_response(
                chat_data,
                ids.assistant,
            )

            if not response:
                print(
                    json.dumps(
                        chat_data,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

                raise RuntimeError(
                    "Open WebUI completed the "
                    "request but returned no "
                    "assistant content."
                )

            print(
                f"[{chat_id}] Final response:"
            )
            print(response)

            return response

    async def create_chat(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
    ):
        chat_id = str(
            __import__("uuid").uuid4()
        )

        ids = create_message_ids()

        user_message = make_user_message(
            ids.user,
            prompt,
            None,
            ids.assistant,
            self.model,
        )

        assistant_message = (
            make_assistant_message(
                ids.assistant,
                ids.user,
                self.model,
            )
        )

        payload = {
            "chat": {
                "id": chat_id,
                "title": prompt[:80],
                "models": [self.model],
                "history": {
                    "currentId": ids.assistant,
                    "messages": {
                        ids.user: user_message,
                        ids.assistant: assistant_message,
                    },
                },
            }
        }

        data = await self.client.post(
            session,
            "/v1/chats/new",
            payload,
        )

        returned_id = (
            data.get("id")
            or data.get("chat", {}).get("id")
            or chat_id
        )

        return (
            str(returned_id),
            ids,
            None,
        )

    async def get_chat(
        self,
        session: aiohttp.ClientSession,
        chat_id: str,
    ) -> dict:
        return await self.client.get(
            session,
            f"/v1/chats/{chat_id}",
        )

    async def get_existing_chat(
        self,
        session: aiohttp.ClientSession,
        chat_id: str,
    ) -> dict | None:
        try:
            return await self.get_chat(
                session,
                chat_id,
            )

        except RuntimeError as exc:
            error = str(exc)

            if any(
                f"HTTP {code}" in error
                for code in (401, 403, 404)
            ):
                print(
                    f"[{chat_id}] "
                    f"Existing chat inaccessible: "
                    f"{error}"
                )
                return None

            raise

    @staticmethod
    def get_current_message_id(
        chat_data: dict,
    ) -> str:
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

        current_id = history.get("currentId")

        if not current_id:
            raise RuntimeError(
                "Open WebUI chat has no currentId."
            )

        return str(current_id)

    async def add_message(
        self,
        session: aiohttp.ClientSession,
        chat_id: str,
        prompt: str,
        parent_id: str,
    ):
        ids = create_message_ids()

        user_message = make_user_message(
            ids.user,
            prompt,
            parent_id,
            ids.assistant,
            self.model,
        )

        assistant_message = (
            make_assistant_message(
                ids.assistant,
                ids.user,
                self.model,
            )
        )

        payload = {
            "chat": {
                "history": {
                    "currentId": ids.assistant,
                    "messages": {
                        ids.user: user_message,
                        ids.assistant: assistant_message,
                    },
                }
            }
        }

        await self.client.post(
            session,
            f"/v1/chats/{chat_id}",
            payload,
        )

        return ids

    async def start_completion(
        self,
        session: aiohttp.ClientSession,
        chat_id: str,
        ids,
        prompt: str,
        parent_id: str | None,
    ) -> dict:
        url = (
            f"{self.client.base_url}"
            "/chat/completions"
        )

        session_id = f"discord-{chat_id}"

        user_message = {
            "id": ids.user,
            "parentId": parent_id,
            "childrenIds": [ids.assistant],
            "role": "user",
            "content": prompt,
            "timestamp": int(time.time()),
            "models": [self.model],
        }

        payload = {
            "stream": True,
            "model": self.model,

            "params": {
                "tool_approval_mode": "full",
            },

            "tool_servers": [],

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
                "id": self.model,
                "name": self.model,
                "object": "model",
            },

            "session_id": session_id,

            "chat_id": chat_id,

            "id": ids.assistant,

            "message_ids": [
                {
                    "model_id": self.model,
                    "message_id": ids.assistant,
                    "modelIdx": 0,
                }
            ],

            "parent_id": parent_id,

            "user_message": user_message,

            "background_tasks": {
                "title_generation": False,
                "tags_generation": False,
                "follow_up_generation": True,
            },
        }

        async with session.post(
            url,
            headers=self.client.headers(),
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
                    f"HTTP {response.status}: "
                    f"{body}"
                )

            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "Invalid JSON from Open WebUI: "
                    f"{body[:2000]}"
                ) from exc

    async def _complete_with_retry(
        self,
        session,
        chat_id,
        ids,
        prompt,
        parent_id,
    ):
        for attempt in range(
            self.max_retries + 1
        ):
            try:
                return await self.start_completion(
                    session,
                    chat_id,
                    ids,
                    prompt,
                    parent_id,
                )

            except RuntimeError as exc:
                if not self._is_retryable(exc):
                    raise

                if attempt >= self.max_retries:
                    raise

                print(
                    f"[{chat_id}] {exc}"
                )

                await asyncio.sleep(
                    self.retry_delay
                )

        raise RuntimeError(
            "Completion failed."
        )

    @staticmethod
    def _is_retryable(
        exc: RuntimeError,
    ) -> bool:
        error = str(exc)

        return any(
            f"HTTP {code}" in error
            for code in (502, 503, 504)
        )

    async def wait_for_tasks(
        self,
        session,
        chat_id: str,
        task_ids: list[str],
    ):
        url = (
            f"/tasks/chat/{chat_id}"
        )

        started = time.monotonic()

        while True:
            if (
                time.monotonic() - started
                > self.task_timeout
            ):
                raise TimeoutError(
                    "Open WebUI task timed out "
                    f"after {self.task_timeout}s."
                )

            data = await self.client.get(
                session,
                url,
            )

            active = data.get(
                "task_ids",
                [],
            )

            if not active:
                return

            still_running = [
                task_id
                for task_id in task_ids
                if task_id in active
            ]

            if not still_running:
                return

            await asyncio.sleep(
                self.task_poll_interval
            )

    @staticmethod
    def extract_response(
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
            candidates = [
                item
                for item in messages.values()
                if (
                    isinstance(item, dict)
                    and item.get("role")
                    == "assistant"
                    and item.get("content")
                )
            ]

            if not candidates:
                return ""

            candidates.sort(
                key=lambda item: item.get(
                    "timestamp",
                    0,
                )
            )

            message = candidates[-1]

        content = message.get("content")

        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            return "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
                and isinstance(
                    item.get("text"),
                    str,
                )
            ).strip()

        return ""

