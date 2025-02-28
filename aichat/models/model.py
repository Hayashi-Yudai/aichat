from typing import Protocol

from pydantic.dataclasses import dataclass


@dataclass
class Schema:
    column_name: str
    column_type: str
    is_primary_key: bool = False
    is_nullable: bool = False

    def __post_init__(self):
        if self.is_nullable and self.is_primary_key:
            raise ValueError("Primary key cannot be nullable")


class Model(Protocol):
    @property
    def schema(self) -> list[Schema]:
        pass

    @property
    def table_name(self) -> str:
        pass
