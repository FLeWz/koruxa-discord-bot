import json
import re
from pathlib import Path

import aiohttp
import discord

from .client import OpenWebUIClient
from storage.json_store import JsonStore


class KnowledgeDirectoryManager:
    def __init__(
        self,
        client: OpenWebUIClient,
        knowledge_id: str,
        mapping_file: str,
    ):
        self.client = client
        self.knowledge_id = knowledge_id

        self.store = JsonStore(mapping_file)
        self.directory_ids = {
            str(key): str(value)
            for key, value
            in self.store.load().items()
        }

    def _save(self):
        self.store.save(
            self.directory_ids
        )

    @staticmethod
    def safe_username(
        username: str,
    ) -> str:
        result = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            username,
        ).strip()

        return result or "unknown"

    async def create_directory(
        self,
        session: aiohttp.ClientSession,
        name: str,
        parent_id: str | None = None,
    ) -> str:
        payload = {
            "name": name,
        }

        if parent_id is not None:
            payload["parent_id"] = parent_id

        data = await self.client.post(
            session,
            (
                f"/api/v1/knowledge/"
                f"{self.knowledge_id}/dirs/create"
            ),
            payload,
        )

        directory = data.get(
            "directory",
            data,
        )

        if not isinstance(directory, dict):
            raise RuntimeError(
                "Unexpected directory response."
            )

        directory_id = (
            directory.get("id")
            or data.get("id")
        )

        if not directory_id:
            raise RuntimeError(
                "Open WebUI did not return "
                "a directory ID."
            )

        return str(directory_id)

    async def ensure_root(
        self,
        session: aiohttp.ClientSession,
    ) -> str:
        existing = self.directory_ids.get(
            "root"
        )

        if existing:
            return existing

        directory_id = (
            await self.create_directory(
                session,
                "discord-users",
            )
        )

        self.directory_ids["root"] = (
            directory_id
        )

        self._save()

        return directory_id

    async def ensure_user_directory(
        self,
        session: aiohttp.ClientSession,
        user: discord.abc.User,
    ) -> str:
        key = str(user.id)

        existing = self.directory_ids.get(
            key
        )

        if existing:
            return existing

        root_id = await self.ensure_root(
            session
        )

        name = (
            f"{user.id} "
            f"{self.safe_username(user.name)}"
        )

        directory_id = (
            await self.create_directory(
                session,
                name,
                root_id,
            )
        )

        self.directory_ids[key] = (
            directory_id
        )

        self._save()

        return directory_id

    async def upload_user_log(
        self,
        session,
        user_id: int,
        username: str,
        file_path: Path,
    ):
        if not file_path.exists():
            return

        directory_id = (
            await self.ensure_user_directory(
                session,
                user_id,
                username,
            )
        )

        await self._upload(
            session,
            file_path,
            directory_id,
        )

    async def upload_all_users_log(
        self,
        session: aiohttp.ClientSession,
        file_path: Path,
    ):
        if not file_path.exists():
            return

        root_id = await self.ensure_root(
            session
        )

        await self._upload(
            session,
            file_path,
            root_id,
        )

    async def _upload(
        self,
        session: aiohttp.ClientSession,
        file_path: Path,
        directory_id: str,
    ):
        url = (
            f"{self.client.base_url}"
            "/api/v1/files/"
        )

        headers = {
            "Authorization": (
                f"Bearer {self.client.api_key}"
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
                        self.knowledge_id
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
            data = await self.client.read_json(
                response
            )

        file_id = (
            data.get("id")
            or data.get("file", {}).get("id")
        )

        print(
            f"Uploaded {file_path}"
            + (
                f" as file {file_id}"
                if file_id
                else ""
            )
        )

