from datetime import datetime
from enum import StrEnum
import uuid

from loguru import logger
from pydantic.dataclasses import dataclass


import config
from database.db import SQLiteDB
from models.model import Schema
from models.chat import Chat
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

    @classmethod
    def from_tuple(cls, t: tuple):
        if t[6] == config.USER_NAME:
            color = config.USER_AVATAR_COLOR
        elif t[6] == config.AGENT_NAME:
            color = config.AGENT_AVATAR_COLOR
        else:
            color = config.APP_AVATAR_COLOR
        return cls(t[0], t[1], t[2], t[3], t[4], t[5], Role(t[6], color))

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

    def insert_into_db(self):
        db = SQLiteDB(config.IS_DEBUG)
        if not db.entry_exist(table_name="chat", condition=f"id='{self.chat_id}'"):
            logger.info(f"chat_id={self.chat_id} does not exist. Create chat...")
            Chat.construct_auto(
                self.chat_id, self.display_content[:20]
            ).insert_into_db()

        db.insert(
            table_name=self.table_name,
            schema=self.schema,
            values=[
                self.id,
                self.chat_id,
                self.created_at,
                self.display_content,
                self.system_content,
                self.content_type,
                self.role.name,
            ],
        )

    @classmethod
    def get_all_by_chat_id(cls, chat_id: int):
        db = SQLiteDB(config.IS_DEBUG)
        entities = db.get_all("message", condition=f"chat_id='{chat_id}'")

        return [cls.from_tuple(e) for e in entities]
