from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord


class DiscordLogger:
    def __init__(
        self,
        root_directory: str,
        timezone: str,
    ):
        self.root = Path(root_directory)
        self.timezone = ZoneInfo(timezone)

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def now(self) -> datetime:
        return datetime.now(
            self.timezone
        )

    def daily_path(
        self,
        date_string: str,
    ) -> Path:
        return self.root / (
            f"{date_string}.md"
        )

    @staticmethod
    def format_user(
        user: discord.abc.User,
    ) -> str:
        return (
            f"{user.display_name} ({user.name}, {user.id})"
        )

    @staticmethod
    def format_channel(
        channel: discord.abc.Snowflake,
    ) -> str:
        # DM channels have no name.
        name = getattr(channel, "name", None) or "DM"

        return f"{name} ({channel.id})"

    async def get_replied_message(
        self,
        message: discord.Message,
    ) -> discord.Message | None:
        reference = message.reference

        if reference is None:
            return None

        if isinstance(
            reference.resolved,
            discord.Message,
        ):
            return reference.resolved

        if reference.message_id is None:
            return None

        try:
            return await message.channel.fetch_message(
                reference.message_id
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return None

    async def format_reply_to(
        self,
        message: discord.Message,
    ) -> str:
        reference = message.reference

        if reference is None:
            return None

        replied_message = await self.get_replied_message(
            message
        )

        if replied_message is not None:
            return self.format_user(
                replied_message.author
            )

        if reference.message_id is not None:
            return (
                f"Unknown user "
                f"(Discord message ID "
                f"`{reference.message_id}`)"
            )

        return "Unknown"

    async def format_message(
        self,
        message: discord.Message,
        timestamp: datetime,
    ) -> str:
        content = (
            message.content.strip()
            or "(no text content)"
        )

        attachments = None

        if message.attachments:
            urls = [
                attachment.url
                for attachment
                in message.attachments
            ]

            attachments = (
                "\n".join(
                    f"- {url}"
                    for url in urls
                )
            )

        stickers = None

        if message.stickers:
            stickers = (
                "\n".join(
                    f"- {sticker.url}"
                    for sticker
                    in message.stickers
                )
            )

        sent_by = self.format_user(
            message.author
        )

        reply_to = await self.format_reply_to(
            message
        )

        channel = self.format_channel(
            message.channel
        )

        msg = (
            f"Date: {timestamp.strftime('%H:%M:%S %Z')}\n"
            f"Channel: {channel}\n"
            f"Sent-By: {sent_by}\n"
        )

        if reply_to is not None:
            msg += (
                f"Reply-To: {reply_to}\n"
            )

        if attachments is not None:
            msg += (
                f"Attachments:\n{attachments}\n"
            )

        if stickers is not None:
            msg += (
                f"Stickers:\n"
                f"{stickers}\n"
            )

        msg += (
            f"\n{content}\n"
            "---\n"
        )

        return msg

    async def append(
        self,
        message: discord.Message,
    ) -> Path:
        timestamp = self.now()

        date_string = timestamp.strftime(
            "%Y-%m-%d"
        )

        formatted = await self.format_message(
            message,
            timestamp,
        )

        path = self.daily_path(
            date_string
        )

        if not path.exists():
            path.write_text(
                (
                    f"# All Discord messages — "
                    f"{date_string}\n\n"
                    "---\n\n"
                ),
                encoding="utf-8",
            )

        with path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(formatted)

        return path

    def get_old_logs(self):
        today = self.now().date()

        for path in self.root.glob("*.md"):
            try:
                date = datetime.strptime(
                    path.stem,
                    "%Y-%m-%d",
                ).date()
            except ValueError:
                continue

            if date < today:
                yield path

