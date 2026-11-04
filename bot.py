import discord
from discord.ext import commands

from config import Config

from mydiscord.commands import DiscordCommands
from mydiscord.events import DiscordEventHandler
from mydiscord.messaging import (
    DiscordMessageService,
)

from mydiscord.reaction_roles import (
    ReactionRoleService,
)

from mylogger.discord_logger import DiscordLogger

from openwebui.chat import (
    OpenWebUIChatService,
)
from openwebui.client import (
    OpenWebUIClient,
)
from openwebui.knowledge import (
    KnowledgeDirectoryManager,
)

from storage.json_store import JsonStore

from services.daily_scheduler import (
    DailyLogScheduler,
)

from storage.user_chats import (
    UserChatStore,
)


class KoruxaBot:
    def __init__(
        self,
        config: Config,
    ):
        self.config = config

        intents = discord.Intents.default()
        intents.message_content = True

        self.bot = commands.Bot(
            command_prefix="!",
            intents=intents,
        )

        # ----------------------------------------------------
        # Storage
        # ----------------------------------------------------

        self.chat_store = UserChatStore(
            config.user_chat_map_file
        )

        # ----------------------------------------------------
        # Open WebUI
        # ----------------------------------------------------

        openwebui_client = (
            OpenWebUIClient(
                base_url=config.openwebui_url,
                api_key=config.openwebui_api_key,
            )
        )

        self.chat_service = (
            OpenWebUIChatService(
                client=openwebui_client,
                user_chats=self.chat_store,
                model=config.openwebui_model,
                knowledge_id=(
                    config.openwebui_knowledge_id
                ),
                retry_delay=(
                    config.model_retry_delay
                ),
                max_retries=(
                    config.model_max_retries
                ),
                task_poll_interval=(
                    config.task_poll_interval
                ),
                task_timeout=(
                    config.task_timeout
                ),
            )
        )

        self.knowledge = (
            KnowledgeDirectoryManager(
                client=openwebui_client,
                knowledge_id=(
                    config.openwebui_knowledge_id
                ),
            )
        )

        # ----------------------------------------------------
        # Discord logging
        # ----------------------------------------------------

        self.logger = DiscordLogger(
            root_directory=(
                config.discord_log_dir
            ),
            timezone=(
                config.discord_log_timezone
            ),
        )

        # ----------------------------------------------------
        # Services
        # ----------------------------------------------------

        self.messaging = (
            DiscordMessageService(
                self.bot
            )
        )

        self.scheduler = (
            DailyLogScheduler(
                logger=self.logger,
                knowledge=self.knowledge,
            )
        )

        self.events = (
            DiscordEventHandler(
                bot=self.bot,
                chat_service=self.chat_service,
                chat_store=self.chat_store,
                logger=self.logger,
                messaging=self.messaging,
                scheduler=self.scheduler,
            )
        )

        # ----------------------------------------------------
        # Commands
        # ----------------------------------------------------

        self.reaction_roles = ReactionRoleService(
            bot=self.bot,
            store=JsonStore(
                config.reaction_roles_file
            ),
        )

        self.commands = DiscordCommands(
            bot=self.bot,
            chat_store=self.chat_store,
            events=self.events,
            reaction_roles=self.reaction_roles,
        )

        # ----------------------------------------------------
        # Event registration
        # ----------------------------------------------------

        self.bot.event(
            self.events.on_ready
        )

        self.bot.event(
            self.events.on_message
        )

        self.bot.add_listener(
            self.reaction_roles.on_raw_reaction_add,
            "on_raw_reaction_add",
        )

        self.bot.add_listener(
            self.reaction_roles.on_raw_reaction_remove,
            "on_raw_reaction_remove",
        )

    def run(self):
        self.bot.run(
            self.config.discord_token
        )

