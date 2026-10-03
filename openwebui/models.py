import time
from dataclasses import dataclass
import uuid


@dataclass(frozen=True)
class MessageIds:
    user: str
    assistant: str


def create_message_ids() -> MessageIds:
    return MessageIds(
        user=str(uuid.uuid4()),
        assistant=str(uuid.uuid4()),
    )


def make_user_message(
    message_id: str,
    content: str,
    parent_id: str | None,
    assistant_id: str,
    model: str,
) -> dict:
    return {
        "id": message_id,
        "role": "user",
        "content": content,
        "timestamp": int(time.time()),
        "models": [model],
        "parentId": parent_id,
        "childrenIds": [assistant_id],
    }


def make_assistant_message(
    message_id: str,
    parent_id: str,
    model: str,
) -> dict:
    return {
        "id": message_id,
        "role": "assistant",
        "content": "",
        "parentId": parent_id,
        "childrenIds": [],
        "model": model,
        "modelName": model,
        "modelIdx": 0,
        "done": False,
        "timestamp": int(time.time()) + 1,
    }

