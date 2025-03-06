from datetime import datetime
from enum import StrEnum
import uuid

# from loguru import logger
from pydantic.dataclasses import dataclass

from models.model import Schema
from models.role import Role


class ContentType(StrEnum):
    TEXT = "text"
    PNG = "png"
    JPEG = "jpeg"


@dataclass
class Message:
    id: str
    chat_id: str
    created_at: datetime
    display_content: str  # UI上に表示する内容
    system_content: str  # Agentに送信する内容. base64エンコードされた画像データなど
    content_type: ContentType
    role: Role

    @classmethod
    def construct_auto(cls, chat_id: str, text: str, role: Role):
        return cls(
            str(uuid.uuid4()),
            chat_id,
            datetime.now(),
            text,
            text,
            ContentType.TEXT,
            role,
        )

    @classmethod
    def construct_auto_file(
        cls, chat_id: str, display_content: str, system_content: str, role, content_type
    ):
        return cls(
            str(uuid.uuid4()),
            chat_id,
            datetime.now(),
            display_content,
            system_content,
            content_type,
            role,
        )

    @property
    def schema(self) -> dict[str, str]:
        return [
            Schema("id", "text", is_primary_key=True, is_nullable=False),
            Schema("chat_id", "text", is_nullable=False),
            Schema("created_at", "text", is_nullable=False),
            Schema("display_content", "text", is_nullable=True),
            Schema("system_content", "text", is_nullable=True),
            Schema("content_type", "text", is_nullable=False),
            Schema("role", "text", is_nullable=False),
        ]

    @property
    def table_name(self) -> str:
        return self.__class__.__name__.lower()

    @property
    def db__id(self) -> str:
        return self.id

    @property
    def db__chat_id(self) -> str:
        return self.chat_id

    @property
    def db__created_at(self) -> datetime:
        return self.created_at

    @property
    def db__display_content(self) -> str:
        return self.display_content

    @property
    def db__system_content(self) -> str:
        return self.system_content

    @property
    def db__content_type(self) -> ContentType:
        return self.content_type

    @property
    def db__role(self) -> str:
        return self.role.name
