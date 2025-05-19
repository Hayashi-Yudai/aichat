from enum import StrEnum
from typing import Any, AsyncGenerator
from asyncio import sleep


import config
from models.message import Message
from models.role import Role


class DummyModel(StrEnum):
    DUMMY = "Dummy"


class DummyAgent:
    """
    デバッグ用のエージェント
    """

    def __init__(self, model: str):
        self.model = DummyModel.DUMMY
        self.role = Role(
            f"{config.AGENT_NAME} ({self.model})", config.AGENT_AVATAR_COLOR
        )

    def _construct_request(self, message: Message) -> dict[str, Any]:
        return {"role": message.role, "content": message.system_content}

    async def prepare_prompt(self, messages: list[Message]) -> list[dict[str, Any]]:
        return [self._construct_request(m) for m in messages]

    def prepare_tools(self) -> list[dict[str, Any]]:
        return []

    async def request_once(
        self, prompt: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AsyncGenerator[str, None]:
        m = prompt[-1]["content"]
        for chunk in m:
            yield chunk
            await sleep(0.05)
