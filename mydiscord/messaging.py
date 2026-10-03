import re

import discord


class DiscordMessageService:
    def __init__(
        self,
        bot: discord.Client,
    ):
        self.bot = bot

    def clean_message(
        self,
        message: discord.Message,
    ) -> str:
        text = message.content

        if self.bot.user:
            text = re.sub(
                rf"<@!?{self.bot.user.id}>",
                "",
                text,
                flags=re.IGNORECASE,
            )

        return text.strip()

    async def send_long_message(
        self,
        channel: discord.abc.Messageable,
        text: str,
    ):
        if not text:
            return

        while len(text) > 2000:
            split_at = text.rfind(
                "\n",
                0,
                2000,
            )

            if split_at < 1000:
                split_at = text.rfind(
                    " ",
                    0,
                    2000,
                )

            if split_at <= 0:
                split_at = 2000

            await channel.send(
                text[:split_at]
            )

            text = text[
                split_at:
            ].lstrip()

        if text:
            await channel.send(text)

