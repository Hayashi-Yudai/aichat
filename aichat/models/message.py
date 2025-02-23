from datetime import datetime
from enum import StrEnum
import uuid

from loguru import logger
from pydantic.dataclasses import dataclass

from models.role import Role


class ContentType(StrEnum):
    TEXT = "text"
    PNG = "png"
    JPEG = "jpeg"


@dataclass
class Message:
    id: str
    created_at: datetime
    display_content: str  # UI上に表示する内容
    system_content: str  # Agentに送信する内容. base64エンコードされた画像データなど
    content_type: ContentType
    role: Role

    def register(self):
        logger.debug(f"Message registered in {self.__class__.__name__} model")
        logger.debug(
            f"id: {self.id}, created_at: {self.created_at}, text: {self.display_content:.10}, role: {self.role}"
        )

    @classmethod
    def construct_auto(cls, text: str, role: Role):
        return cls(
            str(uuid.uuid4()), datetime.now(), text, text, ContentType.TEXT, role
        )
