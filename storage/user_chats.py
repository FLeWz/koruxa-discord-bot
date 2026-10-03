from typing import Any

import discord

from .json_store import JsonStore


class UserChatStore:
    def __init__(self, path: str):
        self.store = JsonStore(path)

        raw = self.store.load()

        self._mappings: dict[int, str] = {
            int(user_id): str(chat_id)
            for user_id, chat_id in raw.items()
        }

        print(
            f"Loaded {len(self._mappings)} "
            f"user/chat mappings"
        )

    def get(
        self,
        user: discord.abc.User,
    ) -> str | None:
        return self._mappings.get(user.id)

    def set(
        self,
        user: discord.abc.User,
        chat_id: str,
    ) -> None:
        self._mappings[user.id] = chat_id
        self._save()

    def delete(
        self,
        user: discord.abc.User,
    ) -> str | None:
        chat_id = self._mappings.pop(
            user.id,
            None,
        )

        if chat_id is not None:
            self._save()

        return chat_id

    def _save(self) -> None:
        self.store.save(
            {
                str(user_id): chat_id
                for user_id, chat_id
                in self._mappings.items()
            }
        )

