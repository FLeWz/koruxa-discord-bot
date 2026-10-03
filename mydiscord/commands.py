from discord.ext import commands

from storage.user_chats import UserChatStore
from mydiscord.events import DiscordEventHandler


class DiscordCommands:
    def __init__(
        self,
        bot: commands.Bot,
        chat_store: UserChatStore,
        events: DiscordEventHandler,
    ):
        self.bot = bot
        self.chat_store = chat_store
        self.events = events

        self.register()

    def register(self):
        @self.bot.command(name="stop")
        async def stop_command(
            ctx: commands.Context,
        ):
            chat_id = await self.events.stop()

            if chat_id is None:
                await ctx.send(
                    "There is no active task."
                )
                return

            await ctx.send(
                "🛑 Stopping the current task"
                f" (`{chat_id}`)."
            )

        @self.bot.command(name="reset")
        async def reset_command(
            ctx: commands.Context,
        ):
            old_chat_id = (
                self.chat_store.delete(
                    ctx.author
                )
            )

            if old_chat_id is None:
                await ctx.send(
                    "You don't currently have "
                    "a chat memory."
                )
                return

            await ctx.send(
                "🧹 Your chat memory has been "
                "reset. Your next message will "
                "start a new conversation."
            )

            print(
                f"Reset Open WebUI chat "
                f"{old_chat_id} "
                f"for Discord user "
                f"{ctx.author.id}"
            )

