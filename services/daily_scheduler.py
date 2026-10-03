import asyncio

import aiohttp

from mylogger.discord_logger import DiscordLogger
from openwebui.knowledge import (
    KnowledgeDirectoryManager,
)


class DailyLogScheduler:
    def __init__(
        self,
        logger: DiscordLogger,
        knowledge: KnowledgeDirectoryManager,
    ):
        self.logger = logger
        self.knowledge = knowledge

    async def finalize_previous_day(self):
        timeout = aiohttp.ClientTimeout(
            total=None
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            for (
                user_id,
                username,
                path,
            ) in self.logger.get_old_user_logs():

                try:
                    await self.knowledge.upload_user_log(
                        session,
                        self._fake_user(
                            user_id,
                            username,
                        ),
                        path,
                    )
                except Exception as exc:
                    print(
                        f"Failed to upload "
                        f"{path}: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

            for path in (
                self.logger
                .get_old_aggregate_logs()
            ):
                try:
                    await (
                        self.knowledge
                        .upload_all_users_log(
                            session,
                            path,
                        )
                    )
                except Exception as exc:
                    print(
                        f"Failed to upload "
                        f"{path}: "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

    async def run(self):
        while True:
            now = self.logger.now()

            tomorrow = (
                now.date().toordinal() + 1
            )

            next_midnight = (
                __import__("datetime")
                .datetime
                .fromordinal(tomorrow)
                .replace(
                    tzinfo=self.logger.timezone
                )
            )

            seconds = (
                next_midnight - now
            ).total_seconds()

            await asyncio.sleep(
                max(1, seconds + 2)
            )

            try:
                print(
                    "Daily Discord log rollover."
                )

                await self.finalize_previous_day()

            except Exception as exc:
                print(
                    f"Daily log rollover failed: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

    @staticmethod
    def _fake_user(
        user_id: int,
        username: str,
    ):
        """
        Lightweight object providing the attributes
        required by KnowledgeDirectoryManager.
        """

        class User:
            id = user_id
            name = username

        return User()

