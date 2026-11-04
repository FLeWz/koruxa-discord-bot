import asyncio

import discord

from storage.json_store import JsonStore


# Role name -> emoji, in display order.
REACTION_ROLES: dict[str, str] = {
    "Woodcutting": "🪓",
    "Mining": "⛏️",
    "Fishing": "🎣",
    "Cooking": "🍳",
    "Fletching": "🏹",
    "Crafting": "🧵",
    "Jewellery": "💍",
    "Herblore": "🌿",
    "Smithing": "🔨",
    "Firemaking": "🔥",
    "Alchemy": "⚗️",
    "Arcana": "🔮",
    "Construction": "🏗️",
    "Tinkering": "⚙️",
    "Combat": "⚔️",
    "ClanBoss": "👹",
}


class ReactionRoleService:
    """Posts reaction role messages and grants/removes roles.

    Persisted layout (message id as string):
        {"<message_id>": {"<emoji>": <role_id>, ...}}
    """

    def __init__(
        self,
        bot: discord.Client,
        store: JsonStore,
    ):
        self.bot = bot
        self.store = store
        self.messages: dict[
            str, dict[str, int]
        ] = store.load()

    async def setup(
        self,
        channel: discord.abc.Messageable,
        guild: discord.Guild,
    ) -> tuple[discord.Message, list[str]]:
        """Create missing roles, post message, add reactions.

        Returns the message and the names of created roles.
        """
        created: list[str] = []
        mapping: dict[str, int] = {}

        existing = {
            role.name.lower(): role
            for role in guild.roles
        }

        for name, emoji in REACTION_ROLES.items():
            role = existing.get(name.lower())

            if role is None:
                role = await guild.create_role(
                    name=name,
                    mentionable=True,
                    reason="Reaction roles setup",
                )
                created.append(name)

            mapping[emoji] = role.id

        lines = ["**React to get a role:**", ""]
        lines.extend(
            f"{emoji} {name}"
            for name, emoji in REACTION_ROLES.items()
        )
        lines.append("")
        lines.append("Remove your reaction to drop the role.")

        message = await channel.send(
            "\n".join(lines)
        )

        for emoji in mapping:
            await message.add_reaction(emoji)
            # Stay clear of the reaction rate limit.
            await asyncio.sleep(0.3)

        self.messages[str(message.id)] = mapping
        self.store.save(self.messages)

        return message, created

    def _lookup(
        self,
        payload: discord.RawReactionActionEvent,
    ) -> int | None:
        mapping = self.messages.get(
            str(payload.message_id)
        )

        if mapping is None:
            return None

        return mapping.get(str(payload.emoji))

    async def on_raw_reaction_add(
        self,
        payload: discord.RawReactionActionEvent,
    ):
        if payload.guild_id is None:
            return

        if payload.user_id == self.bot.user.id:
            return

        role_id = self._lookup(payload)

        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(role_id) if guild else None
        member = payload.member

        if role is None or member is None:
            return

        try:
            await member.add_roles(
                role,
                reason="Reaction role",
            )
        except discord.HTTPException as exc:
            print(
                f"Could not add role {role.name} "
                f"to {member.id}: {exc}"
            )

    async def on_raw_reaction_remove(
        self,
        payload: discord.RawReactionActionEvent,
    ):
        if payload.guild_id is None:
            return

        if payload.user_id == self.bot.user.id:
            return

        role_id = self._lookup(payload)

        if role_id is None:
            return

        guild = self.bot.get_guild(payload.guild_id)
        role = guild.get_role(role_id) if guild else None

        if role is None:
            return

        try:
            member = await guild.fetch_member(
                payload.user_id
            )
            await member.remove_roles(
                role,
                reason="Reaction role",
            )
        except discord.HTTPException as exc:
            print(
                f"Could not remove role {role.name} "
                f"from {payload.user_id}: {exc}"
            )
