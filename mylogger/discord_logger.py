import re
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

    def user_directory(
        self,
        user: discord.abc.User,
    ) -> Path:
        username = self.safe_username(
            user.name
        )

        path = self.root / (
            f"{user.id} {username}"
        )

        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        return path

    def user_daily_path(
        self,
        user: discord.abc.User,
        date_string: str,
    ) -> Path:
        return (
            self.user_directory(user)
            / f"{date_string}.md"
        )

    def all_users_daily_path(
        self,
        date_string: str,
    ) -> Path:
        return self.root / (
            f"{date_string}.md"
        )

    def format_message(
        self,
        message: discord.Message,
        timestamp: datetime,
    ) -> str:
        content = (
            message.content.strip()
            or "(no text content)"
        )

        attachments = ""

        if message.attachments:
            urls = [
                attachment.url
                for attachment
                in message.attachments
            ]

            attachments = (
                "\n\nAttachments:\n"
                + "\n".join(
                    f"- {url}"
                    for url in urls
                )
            )

        return (
            f"### "
            f"{timestamp.strftime('%H:%M:%S %Z')}"
            f" — "
            f"{message.author.display_name} "
            f"(`{message.author.name}`, "
            f"Discord ID "
            f"`{message.author.id}`)\n\n"
            f"{content}"
            f"{attachments}\n\n"
            "---\n\n"
        )

    def append(
        self,
        message: discord.Message,
    ) -> Path:
        timestamp = self.now()
        date_string = timestamp.strftime(
            "%Y-%m-%d"
        )

        formatted = self.format_message(
            message,
            timestamp,
        )

        user_path = self.user_daily_path(
            message.author,
            date_string,
        )

        if not user_path.exists():
            user_path.write_text(
                (
                    f"# Discord messages — "
                    f"{date_string}\n\n"
                    f"Discord user: "
                    f"**{message.author.display_name}**\n"
                    f"Discord ID: "
                    f"`{message.author.id}`\n\n"
                    "---\n\n"
                ),
                encoding="utf-8",
            )

        with user_path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(formatted)

        aggregate_path = (
            self.all_users_daily_path(
                date_string
            )
        )

        if not aggregate_path.exists():
            aggregate_path.write_text(
                (
                    f"# All Discord messages — "
                    f"{date_string}\n\n"
                    "---\n\n"
                ),
                encoding="utf-8",
            )

        with aggregate_path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(formatted)

        return user_path

    def get_old_user_logs(self):
        today = self.now().date()

        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue

            parsed = self.parse_user_directory(
                directory.name
            )

            if parsed is None:
                continue

            user_id, username = parsed

            for path in directory.glob("*.md"):
                try:
                    date = datetime.strptime(
                        path.stem,
                        "%Y-%m-%d",
                    ).date()
                except ValueError:
                    continue

                if date < today:
                    yield user_id, username, path

    def get_old_aggregate_logs(self):
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

    @staticmethod
    def parse_user_directory(
        directory_name: str,
    ) -> tuple[int, str] | None:
        match = re.match(
            r"^(\d+)(?:\s+(.*))?$",
            directory_name,
        )

        if not match:
            return None

        return (
            int(match.group(1)),
            match.group(2) or "unknown",
        )

