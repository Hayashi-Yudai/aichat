from dataclasses import dataclass

from roles import Role


@dataclass
class Message:
    """チャットメッセージを表すクラス"""

    role: Role
    content_type: str
    content: str
    system_content: str

    def to_openai_message(self):
        if self.content_type == "text":
            return {
                "role": "user",
                "content": self.content,
            }
        elif self.content_type == "image_url":
            return {
                "role": "user",
                "content": [
                    {
                        "type": self.content_type,
                        "image_url": {"url": f"data:image/jpeg;base64,{self.system_content}"},
                    }
                ],
            }
