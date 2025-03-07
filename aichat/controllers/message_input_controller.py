import base64
from pathlib import Path

import flet as ft
from flet.core.file_picker import FilePickerFile
from loguru import logger

import config
from models.message import Message, ContentType
from models.role import Role
from topics import Topics


class MessageInputController:
    """
    ユーザーの入力を処理するコントローラー

    ユーザーがサブミット時にチャット欄に書いた入力を受取り、処理を実行する責務をもつ
    """

    def __init__(self, page: ft.Page, chat_id: str):
        self.role = Role(config.USER_NAME, config.USER_AVATAR_COLOR)
        self.pubsub = page.pubsub

        self.chat_id = chat_id

    def send_message(self, text: str):
        # User messageの追加
        msg = Message.construct_auto(self.chat_id, text, self.role)
        msg.insert_into_db()

        topic = Topics.SUBMIT_MESSAGE
        self.pubsub.send_all_on_topic(topic, msg)
        logger.debug(f"{self.__class__.__name__} published topic: {topic}")


class FileLoaderController:
    def __init__(self, pubsub: ft.PubSubClient, chat_id: str):
        self.pubsub = pubsub

        self.chat_id = chat_id

    def append_file_content_to_chatlist(self, file: FilePickerFile):
        file_path = Path(file.path)
        match file_path.suffix.lstrip(".").lower():
            case "txt" | "py" | "md" | "json" | "yaml" | "yml":
                with open(file.path, "r") as f:
                    content = f.read()
                content_type = ContentType.TEXT
            case "png":
                with open(file.path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")
                content_type = ContentType.PNG
            case "jpg" | "jpeg":
                with open(file.path, "rb") as f:
                    content = base64.b64encode(f.read()).decode("utf-8")
                content_type = ContentType.JPEG
            case _:
                logger.error(f"Unsupported file type: {file.path}")
                raise ValueError(f"Unsupported file type: {file.path}")

        msg = Message.construct_auto_file(
            chat_id=self.chat_id,
            display_content=f"File Uploaded: {file_path.name}",
            system_content=content,
            content_type=content_type,
            role=Role("App", ft.Colors.GREY),
        )
        msg.insert_into_db()

        topic = Topics.SUBMIT_MESSAGE
        self.pubsub.send_all_on_topic(topic, msg)
        logger.debug(f"{self.__class__.__name__} published topic: {topic}")
