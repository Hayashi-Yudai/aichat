from datetime import datetime

import config
from database.db import SQLiteDB
from models.model import Schema

from pydantic.dataclasses import dataclass


@dataclass
class Chat:
    id: str
    created_at: datetime
    title: str

    @classmethod
    def construct_auto(cls, id: str, title: str):
        return cls(id, datetime.now(), title)

    @property
    def schema(self) -> dict[str, str]:
        return [
            Schema("id", "text", is_primary_key=True, is_nullable=False),
            Schema("created_at", "text", is_nullable=False),
            Schema("title", "text", is_nullable=False),
        ]

    @property
    def table_name(self) -> str:
        return self.__class__.__name__.lower()

    def insert_into_db(self):
        db = SQLiteDB(config.IS_DEBUG)
        db.insert(
            table_name=self.table_name,
            schema=self.schema,
            values=[
                self.id,
                self.created_at,
                self.title,
            ],
        )
