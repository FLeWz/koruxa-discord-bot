import json

import aiohttp


class OpenWebUIClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def headers(self) -> dict[str, str]:
        return {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def read_json(
        self,
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
                "Open WebUI returned invalid JSON: "
                f"{body[:2000]}"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                "Open WebUI returned unexpected JSON."
            )

        return data

    async def get(
        self,
        session: aiohttp.ClientSession,
        path: str,
    ) -> dict:
        async with session.get(
            f"{self.base_url}{path}",
            headers=self.headers(),
        ) as response:
            return await self.read_json(response)

    async def post(
        self,
        session: aiohttp.ClientSession,
        path: str,
        payload: dict,
    ) -> dict:
        async with session.post(
            f"{self.base_url}{path}",
            headers=self.headers(),
            json=payload,
        ) as response:
            return await self.read_json(response)

