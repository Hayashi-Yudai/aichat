import flet as ft
from loguru import logger

from models.message import Message
from models.role import Role
from topics import Topics


class MessageInputController:
    """
    ユーザーの入力を処理するコントローラー

    ユーザーがサブミット時にチャット欄に書いた入力を受取り、処理を実行する責務をもつ
    """

    def __init__(self, page: ft.Page):
        self.role = Role("user", ft.Colors.GREEN)
        self.pubsub = page.pubsub

    def send_message(self, text: str):
        # User messageの追加
        msg = Message.construct_auto(text, self.role)
        msg.register()

        topic = Topics.SUBMIT_MESSAGE
        self.pubsub.send_all_on_topic(topic, msg)
        logger.debug(f"{self.__class__.__name__} published topic: {topic}")
