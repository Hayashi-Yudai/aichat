from datetime import datetime

from loguru import logger
from pydantic.dataclasses import dataclass

from models.role import Role


@dataclass
class Message:
    id: str
    created_at: datetime
    text: str
    role: Role

    def register(self):
        logger.debug(f"Message registered in {self.__class__.__name__} model")
        logger.debug(
            f"id: {self.id}, created_at: {self.created_at}, text: {self.text:.10}, role: {self.role}"
        )
