import uuid
from datetime import datetime

import flet as ft

from models.message import Message
from models.role import Role
from topics import Topics


class MessageInputController:
    """
    ユーザーの入力を処理するコントローラー

    ユーザーがサブミット時にチャット欄に書いた入力を受取り、処理を実行する責務をもつ
    """

    def __init__(self, pubsub: ft.PubSubClient):
        self.role = Role("user", ft.Colors.GREEN)
        self.pubsub = pubsub

    def send_message(self, text: str):
        id = str(uuid.uuid4())
        created_at = datetime.now()

        msg = Message(id, created_at, text, self.role)
        msg.register()
        self.pubsub.send_all_on_topic(Topics.SUBMIT_MESSAGE, msg)
