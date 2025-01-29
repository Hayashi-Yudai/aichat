from dataclasses import dataclass
import os
from typing import Any, Protocol

import flet as ft
from loguru import logger
import google.generativeai as genai
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam


@dataclass
class Role:
    """チャット履歴に表示される任意の登場人物を表すクラス"""

    name: str
    avatar_color: ft.Colors

    def __hash__(self):
        return hash((self.name, self.avatar_color))


class User(Role):
    """アプリを利用する主体を表すクラス"""


class System(Role):
    """システムを表すクラス"""


class Agent(Protocol):
    """ユーザーと対話するエージェントを表すクラス"""

    def get_response(self, message: Any) -> str: ...

    def transform_to_agent_message(
        self, role_name: str, content_type: str, system_content: str
    ) -> Any: ...


class DummyAgent(Role):
    """ダミーのエージェントを表すクラス"""

    def __init__(self):
        super().__init__("System", ft.Colors.BLUE)
        self.org = "dummy"
        self.model_name = "Dummy"

    def get_response(self, message: Any):
        return "Test"

    def transform_to_agent_message(
        self, role_name: str, content_type: str, system_content: str
    ) -> Any:
        return {
            "role": "assistant" if role_name == "Assistant" else "user",
            "content": system_content,
        }


class OpenAIAgent(Role):
    """Agentプロトコルを実装したOpenAIのエージェントを表すクラス"""

    def __init__(self, model_name: str):
        super().__init__("Assistant", ft.Colors.BLUE)

        self.org = "openai"
        self.model_name = model_name
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def get_response(self, message: list[ChatCompletionMessageParam]):
        logger.info("Sending message to OpenAI...")
        chat_completion = self.client.chat.completions.create(
            messages=message,
            model=self.model_name,
        )
        content = chat_completion.choices[0].message.content
        if content is None:
            logger.error("OpenAI returned None")
            return ""

        return content

    def transform_to_agent_message(
        self, role_name: str, content_type: str, system_content: str
    ) -> Any:
        if content_type == "text":
            return {
                "role": "assistant" if role_name == "Assistant" else "user",
                "content": system_content,
            }
        elif content_type == "png" or content_type == "jpeg":
            return {
                "role": "assistant" if role_name == "Assistant" else "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/{content_type};base64,{system_content}"
                        },
                    }
                ],
            }


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
        logger.info("Sending message to DeepSeek...")
        chat_completion = self.client.chat.completions.create(
            messages=message,
            model=self.model_name,
        )
        content = chat_completion.choices[0].message.content
        if content is None:
            logger.error("DeepSeek returned None")
            return ""

        return content

    def transform_to_agent_message(
        self, role_name: str, content_type: str, system_content: str
    ) -> Any:
        if content_type != "text":
            logger.error("DeepSeek only supports text messages")
            return {}
        message = {
            "role": "assistant" if role_name == "Assistant" else "user",
            "content": system_content,
        }

        return message


class GeminiAgent(Role):
    def __init__(self, model_name: str):
        super().__init__("Assistant", ft.Colors.BLUE)

        self.org = "google"
        self.model_name = model_name
        self.client = OpenAI(
            api_key=os.environ.get("GEMINI_API_KEY"),
            base_url="https://generativelanguage.googleapis.com/v1beta/",
        )
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel(model_name=model_name)

    def get_response(self, message: list[ChatCompletionMessageParam]):
        logger.info("Sending message to Gemini...")
        logger.debug(f"Message: {message}")

        return self.model.generate_content(message).text

    def transform_to_agent_message(
        self, role_name: str, content_type: str, system_content: str
    ) -> Any:
        if content_type == "text":
            return {
                "role": "model" if role_name == "Assistant" else "user",
                "parts": [{"text": system_content}],
            }
        elif content_type == "jpeg" or content_type == "png":
            return {
                "role": "model" if role_name == "Assistant" else "user",
                "parts": [
                    {
                        "mime_type": f"image/{content_type}",
                        "data": system_content,
                    }
                ],
            }
