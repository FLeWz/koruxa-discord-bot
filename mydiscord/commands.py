import discord
from discord.ext import commands

from storage.user_chats import UserChatStore
from mydiscord.events import DiscordEventHandler
from mydiscord.reaction_roles import (
    ReactionRoleService,
)


class DiscordCommands:
    def __init__(
        self,
        bot: commands.Bot,
        chat_store: UserChatStore,
        events: DiscordEventHandler,
        reaction_roles: ReactionRoleService,
    ):
        self.bot = bot
        self.chat_store = chat_store
        self.events = events
        self.reaction_roles = reaction_roles

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

        @self.bot.command(name="reactionroles")
        @commands.guild_only()
        @commands.has_permissions(
            manage_roles=True,
        )
        @commands.bot_has_permissions(
            manage_roles=True,
            add_reactions=True,
        )
        async def reactionroles_command(
            ctx: commands.Context,
        ):
            try:
                _, created = (
                    await self.reaction_roles.setup(
                        ctx.channel,
                        ctx.guild,
                    )
                )
            except discord.HTTPException as exc:
                await ctx.send(
                    "Reaction roles setup failed: "
                    f"{exc}. Make sure my role is "
                    "above the roles I manage."
                )
                return

            if created:
                await ctx.send(
                    "Created roles: "
                    + ", ".join(created)
                )

        @reactionroles_command.error
        async def reactionroles_error(
            ctx: commands.Context,
            error: commands.CommandError,
        ):
            if isinstance(
                error,
                (
                    commands.MissingPermissions,
                    commands.BotMissingPermissions,
                    commands.NoPrivateMessage,
                ),
            ):
                await ctx.send(str(error))
                return

            raise error

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

