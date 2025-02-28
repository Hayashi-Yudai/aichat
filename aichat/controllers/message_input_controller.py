import base64
from pathlib import Path

import flet as ft
from flet.core.file_picker import FilePickerFile
from loguru import logger

from database.db import DB
from models.message import Message, ContentType
from models.role import Role
from topics import Topics


class MessageInputController:
    """
    ユーザーの入力を処理するコントローラー

    ユーザーがサブミット時にチャット欄に書いた入力を受取り、処理を実行する責務をもつ
    """

    def __init__(self, page: ft.Page, db: DB):
        self.role = Role("user", ft.Colors.GREEN)
        self.pubsub = page.pubsub
        self.db = db

    def send_message(self, text: str):
        # User messageの追加
        msg = Message.construct_auto(text, self.role)
        self.db.insert_from_model(msg)

        topic = Topics.SUBMIT_MESSAGE
        self.pubsub.send_all_on_topic(topic, msg)
        logger.debug(f"{self.__class__.__name__} published topic: {topic}")


class FileLoaderController:
    def __init__(self, pubsub: ft.PubSubClient):
        self.pubsub = pubsub

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
            display_content=f"File Uploaded: {file_path.name}",
            system_content=content,
            content_type=content_type,
            role=Role("App", ft.Colors.GREY),
        )
        msg.register()

        topic = Topics.SUBMIT_MESSAGE
        self.pubsub.send_all_on_topic(topic, msg)
        logger.debug(f"{self.__class__.__name__} published topic: {topic}")
