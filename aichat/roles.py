from dataclasses import dataclass
import os
from typing import Any, Protocol

import flet as ft
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam


@dataclass
class Role:
    """チャット履歴に表示される任意の登場人物を表すクラス"""

    name: str
    avatar_color: ft.Colors


class User(Role):
    """アプリを利用する主体を表すクラス"""


class System(Role):
    """システムを表すクラス"""


class Agent(Protocol):
    """ユーザーと対話するエージェントを表すクラス"""

    def get_response(self, message: Any) -> str: ...


class DummyAgent(Role):
    """ダミーのエージェントを表すクラス"""

    def __init__(self):
        super().__init__("System", ft.Colors.BLUE)
        self.org = "dummy"

    def get_response(self, message: Any):
        return "Test"


class OpenAIAgent(Role):
    """Agentプロトコルを実装したOpenAIのエージェントを表すクラス"""

    def __init__(self, model_name: str):
        super().__init__("Assistant", ft.Colors.BLUE)

        self.org = "openai"
        self.model_name = model_name
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def get_response(self, message: list[ChatCompletionMessageParam]):
        chat_completion = self.client.chat.completions.create(
            messages=message,
            model=self.model_name,
        )
        content = chat_completion.choices[0].message.content
        if content is None:
            return ""

        return content


class DeepSeekAgent(Role):
    def __init__(self, model_name: str):
        super().__init__("Assistant", ft.Colors.BLUE)

        self.org = "deepseek"
        self.model_name = model_name
        self.client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )

    def get_response(self, message: list[ChatCompletionMessageParam]):
        chat_completion = self.client.chat.completions.create(
            messages=message,
            model=self.model_name,
        )
        content = chat_completion.choices[0].message.content
        if content is None:
            return ""

        return content
