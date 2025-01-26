from dataclasses import dataclass

from loguru import logger

from roles import Role


@dataclass
class Message:
    """チャットメッセージを表すクラス"""

    role: Role
    content_type: str
    content: str  # チャット履歴に表示される内容
    system_content: str  # Agentが処理する内容

    def to_openai_message(self):
        if self.content_type == "text":
            return {
                "role": "assistant" if self.role.name == "Assistant" else "user",
                "content": self.system_content,
            }
        elif self.content_type == "image_url":
            return {
                "role": "assistant" if self.role.name == "Assistant" else "user",
                "content": [
                    {
                        "type": self.content_type,
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{self.system_content}"
                        },
                    }
                ],
            }

    def to_deepseek_message(self):
        if self.content_type != "text":
            logger.error("DeepSeek only supports text messages")
            return {}
        message = {
            "role": "assistant" if self.role.name == "Assistant" else "user",
            "content": self.system_content,
        }

        return message

    @classmethod
    def from_tuple(cls, t: tuple, role_map: dict[str, Role]):
        return cls(
            role=role_map[t[0]],
            content_type=t[1],
            content=t[2],
            system_content=t[3],
        )
