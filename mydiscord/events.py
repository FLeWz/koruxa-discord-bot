import asyncio

import discord
from discord.ext import commands

from mydiscord.messaging import (
    DiscordMessageService,
)
from mylogger.discord_logger import DiscordLogger
from openwebui.chat import OpenWebUIChatService
from services.daily_scheduler import (
    DailyLogScheduler,
)
from storage.user_chats import UserChatStore


class DiscordEventHandler:
    def __init__(
        self,
        bot: commands.Bot,
        chat_service: OpenWebUIChatService,
        chat_store: UserChatStore,
        logger: DiscordLogger,
        messaging: DiscordMessageService,
        scheduler: DailyLogScheduler,
        allowed_role_id: int | None = None,
    ):
        self.allowed_role_id = allowed_role_id
        self.bot = bot
        self.chat_service = chat_service
        self.chat_store = chat_store
        self.logger = logger
        self.messaging = messaging
        self.scheduler = scheduler

        self.model_lock = asyncio.Lock()

        self.current_task: asyncio.Task | None = None
        self.current_chat_id: str | None = None

        self.daily_log_task: asyncio.Task | None = None

    async def on_ready(self):
        print(
            f"Logged in as {self.bot.user}"
        )

        try:
            await (
                self.scheduler
                .finalize_previous_day()
            )
        except Exception as exc:
            print(
                f"Could not finalize old "
                f"Discord logs: "
                f"{type(exc).__name__}: {exc}"
            )

        if (
            self.daily_log_task is None
            or self.daily_log_task.done()
        ):
            self.daily_log_task = (
                asyncio.create_task(
                    self.scheduler.run()
                )
            )

    async def on_message(
        self,
        message: discord.Message,
    ):
        if message.author.bot:
            return

        await self.bot.process_commands(
            message
        )

        if message.content.startswith(
            self.bot.command_prefix
        ):
            return

        try:
            path = await self.logger.append(
                message
            )

            print(
                f"Logged Discord message "
                f"from {message.author.id} "
                f"to {path}"
            )

        except Exception as exc:
            print(
                f"Failed to log Discord message: "
                f"{type(exc).__name__}: {exc}"
            )

        if self.bot.user not in message.mentions:
            return

        prompt = self.messaging.clean_message(
            message
        )

        if not prompt:
            return

        if not self._is_permitted(message.author):
            await message.channel.send(
                f"{message.author.mention} "
                "You are not permitted to "
                "use this bot."
            )
            return

        if self.model_lock.locked():
            await message.channel.send(
                "Another query is currently "
                "being processed. Your request "
                "has been queued."
            )

        async with self.model_lock:
            await self._process_model_request(
                message,
                prompt,
            )

    def _is_permitted(
        self,
        author: discord.User | discord.Member,
    ) -> bool:
        if self.allowed_role_id is None:
            return True

        # DM authors are plain Users without roles.
        roles = getattr(author, "roles", [])

        return any(
            role.id == self.allowed_role_id
            for role in roles
        )

    async def _process_model_request(
        self,
        message: discord.Message,
        prompt: str,
    ):
        self.current_chat_id = (
            self.chat_store.get(
                message.author
            )
        )

        print(
            f"\n[{self.current_chat_id}] "
            f"Asking: {prompt}"
        )

        self.current_task = (
            asyncio.create_task(
                self.chat_service.ask(
                    (
                        "User: "
                        f"{self.logger.format_user(message.author)}\n"
                        f"Content: {prompt}"
                    ),
                    message.author,
                )
            )
        )

        try:
            response = await self.current_task

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
            self.current_task = None
            self.current_chat_id = None

        if response:
            await self.messaging.send_long_message(
                message.channel,
                response,
            )
        else:
            await message.channel.send(
                "(The model returned an empty "
                "response.)"
            )

    async def stop(self) -> str | None:
        if (
            self.current_task is None
            or self.current_task.done()
        ):
            return None

        chat_id = self.current_chat_id

        self.current_task.cancel()

        return chat_id

