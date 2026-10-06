from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Config:
    discord_token: str

    openwebui_url: str
    openwebui_api_key: str
    openwebui_model: str
    openwebui_knowledge_id: str
    openwebui_knowledge_name: str

    model_retry_delay: int
    model_max_retries: int

    task_poll_interval: float
    task_timeout: int

    user_chat_map_file: str

    discord_log_timezone: str
    discord_log_dir: str
    discord_directory_map_file: str

    @classmethod
    def from_environment(cls) -> "Config":
        return cls(
            discord_token=os.environ["DISCORD_TOKEN"],

            openwebui_url=os.environ[
                "OPENWEBUI_URL"
            ].rstrip("/"),

            openwebui_api_key=os.environ[
                "OPENWEBUI_API_KEY"
            ],

            openwebui_model=os.getenv(
                "OPENWEBUI_MODEL",
                "koruxa-bot",
            ),

            openwebui_knowledge_id=os.getenv(
                "OPENWEBUI_KNOWLEDGE_ID",
                "e90f8d0c-9be7-4902-b31e-a58fe97e925c",
            ),

            openwebui_knowledge_name=os.getenv(
                "OPENWEBUI_KNOWLEDGE_NAME",
                "koruxa",
            ),

            model_retry_delay=int(
                os.getenv(
                    "MODEL_RETRY_DELAY",
                    "10",
                )
            ),

            model_max_retries=int(
                os.getenv(
                    "MODEL_MAX_RETRIES",
                    "30",
                )
            ),

            task_poll_interval=float(
                os.getenv(
                    "TASK_POLL_INTERVAL",
                    "1",
                )
            ),

            task_timeout=int(
                os.getenv(
                    "TASK_TIMEOUT",
                    "1200",
                )
            ),

            user_chat_map_file=os.getenv(
                "USER_CHAT_MAP_FILE",
                "user_chat_ids.json",
            ),

            discord_log_timezone=os.getenv(
                "DISCORD_LOG_TIMEZONE",
                "Europe/Ljubljana",
            ),

            discord_log_dir=os.getenv(
                "DISCORD_LOG_DIR",
                "discord_logs",
            ),

            discord_directory_map_file=os.getenv(
                "DISCORD_DIRECTORY_MAP_FILE",
                "discord_directory_ids.json",
            ),
        )

