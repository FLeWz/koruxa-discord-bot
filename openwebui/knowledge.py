import json
from pathlib import Path

import aiohttp

from .client import OpenWebUIClient


class KnowledgeDirectoryManager:
    def __init__(
        self,
        client: OpenWebUIClient,
        knowledge_id: str,
    ):
        self.client = client
        self.knowledge_id = knowledge_id

    async def upload_daily_log(
        self,
        session: aiohttp.ClientSession,
        file_path: Path,
    ):
        if not file_path.exists():
            return

        await self._upload(
            session,
            file_path,
        )

    async def _upload(
        self,
        session: aiohttp.ClientSession,
        file_path: Path,
    ):
        url = (
            f"{self.client.base_url}"
            "/v1/files/"
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
            content_type="text/plain",
        )

        form.add_field(
            "metadata",
            json.dumps(
                {
                    "knowledge_id": (
                        self.knowledge_id
                    ),
                }
            ),
        )

        async with session.post(
            url,
            headers=headers,
            data=form,
        ) as response:

            if response.status >= 400:
                body = await response.text()

                allow = response.headers.get(
                    "Allow"
                )

                details = (
                    f"HTTP {response.status}: "
                    f"{body}"
                )

                if allow:
                    details += (
                        f" "
                        f"(Allow: {allow})"
                    )

                raise RuntimeError(details)

            data = await response.json()

        file_id = (
            data.get("id")
            or data.get("file", {}).get("id")
        )

        if not file_id:
            raise RuntimeError(
                "Open WebUI upload succeeded "
                "but did not return a file ID: "
                f"{data!r}"
            )

        print(
            f"Uploaded {file_path}"
            f" as file {file_id}"
        )

