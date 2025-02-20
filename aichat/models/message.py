from datetime import datetime

from pydantic.dataclasses import dataclass

from models.role import Role


@dataclass
class Message:
    id: str
    created_at: datetime
    text: str
    role: Role

    def register(self):
        print(f"Message sent: {self.id}, {self.created_at}")
