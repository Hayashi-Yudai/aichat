from dataclasses import dataclass

from roles import Role, Agent


@dataclass
class Message:
    """チャットメッセージを表すクラス"""

    role: Role
    content_type: str
    content: str  # チャット履歴に表示される内容
    system_content: str  # Agentが処理する内容

    def __hash__(self):
        return hash((self.role, self.content_type, self.content, self.system_content))

    def to_agent_message(self, agent: Agent):
        message = agent.transform_to_agent_message(
            self.role.name, self.content_type, self.system_content
        )

        return message

    @classmethod
    def from_tuple(cls, t: tuple, role_map: dict[str, Role]):
        return cls(
            role=role_map[t[0]],
            content_type=t[1],
            content=t[2],
            system_content=t[3],
        )
