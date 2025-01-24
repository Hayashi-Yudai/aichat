from datetime import datetime
from typing import Protocol

from loguru import logger
from pydantic.dataclasses import dataclass

from db import DB


class TableRow(Protocol):
    def insert_into(self, db: DB): ...


@dataclass
class ChatTableRow:
    id: str
    created_at: datetime

    def insert_into(self, db: DB):
        with db.get_connect() as conn:
            conn.execute(
                """
                INSERT INTO chat (id, created_at)
                VALUES (?, ?);
                """,
                (self.id, self.created_at),
            )
        logger.info(f"({self.id}, {self.created_at}) inserted into chat table")


@dataclass
class MessageTableRow:
    id: str
    created_at: datetime
    chat_id: str
    role: str
    content_type: str
    content: str
    system_content: str

    def insert_into(self, db: DB):
        with db.get_connect() as conn:
            conn.execute(
                """
                INSERT INTO message (id, created_at, chat_id, role, content_type, content, system_content)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    self.id,
                    self.created_at,
                    self.chat_id,
                    self.role,
                    self.content_type,
                    self.content,
                    self.system_content,
                ),
            )
        logger.info(
            f"({self.id}, {self.created_at}, {self.chat_id}, {self.role}, ...) inserted into message table"
        )
