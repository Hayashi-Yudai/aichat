from datetime import datetime
from typing import Self

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

    @classmethod
    def from_tuple(cls, t: tuple):
        return cls(*t)

    @property
    def schema(self) -> list[Schema]:
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

    @classmethod
    def get_all(cls) -> list[Self]:
        db = SQLiteDB(config.IS_DEBUG)
        entities = db.get_all("chat")

        return [cls.from_tuple(e) for e in entities]
