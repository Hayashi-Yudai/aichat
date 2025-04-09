import base64
import os
from pathlib import Path
from typing import Callable

import flet as ft
from flet.core.file_picker import FilePickerFile
from loguru import logger
from mistralai import Mistral
import pdfplumber

import config
from models.message import Message, ContentType
from models.role import Role
from topics import Topics


class MessageInputController:
    """
    ユーザーの入力を処理するコントローラー

    ユーザーがサブミット時にチャット欄に書いた入力を受取り、処理を実行する責務をもつ
    """

    def __init__(
        self,
        page: ft.Page,
        update_view_callback: Callable[[], None],
    ):
        self.role = Role(config.USER_NAME, config.USER_AVATAR_COLOR)
        self.pubsub = page.pubsub
        self.update_view_callback = update_view_callback

    def send_message(self, chat_id: str, text: str):
        # User messageの追加
        msg = Message.construct_auto(chat_id, text, self.role)
        msg.insert_into_db()

        topic = Topics.SUBMIT_MESSAGE
        self.pubsub.send_all_on_topic(topic, [msg])
        logger.debug(f"{self.__class__.__name__} published topic: {topic}")

        self.update_view_callback()


class FileLoaderController:
    def __init__(
        self, pubsub: ft.PubSubClient, update_view_callback: Callable[[], None]
    ):
        self.pubsub = pubsub
        self.update_view_callback = update_view_callback

    def append_files(self, e: ft.FilePickerResultEvent, chat_id: str):
        for f in e.files:
            self.append_file_content_to_chatlist(chat_id, f)

    def append_file_content_to_chatlist(self, chat_id: str, file: FilePickerFile):
        self.pubsub.send_all_on_topic(Topics.START_SUBMISSION, "Processing file...")
        file_path = Path(file.path)
        messages: list[Message] = []
        match file_path.suffix.lstrip(".").lower():
            case "png":
                msg = self._image_to_message(
                    chat_id=chat_id,
                    file_path=file_path,
                    content_type=ContentType.PNG,
                )
                msg.insert_into_db()
                messages.append(msg)
            case "jpg" | "jpeg":
                msg = self._image_to_message(
                    chat_id=chat_id,
                    file_path=file_path,
                    content_type=ContentType.JPEG,
                )
                msg.insert_into_db()
                messages.append(msg)
            case "pdf":
                messages.extend(self.parse_pdf(file.path, chat_id))
                for m in messages:
                    m.insert_into_db()
            case _:
                try:
                    with open(file.path, "r") as f:
                        content = f.read()

                    msg = Message.construct_auto_file(
                        chat_id=chat_id,
                        display_content=f"File Uploaded: {file_path.name}",
                        system_content=content,
                        content_type=ContentType.TEXT,
                        role=Role(config.APP_ROLE_NAME, config.APP_ROLE_AVATAR_COLOR),
                    )
                    msg.insert_into_db()
                    messages.append(msg)
                except UnicodeDecodeError:
                    logger.error(f"Unsupported file type: {file.path}")
                    raise ValueError(f"Unsupported file type: {file.path}")

        topic = Topics.SUBMIT_MESSAGE
        self.pubsub.send_all_on_topic(topic, messages)
        logger.debug(f"{self.__class__.__name__} published topic: {topic}")

        self.update_view_callback()

    def _image_to_message(
        self, chat_id: str, file_path: Path, content_type: ContentType
    ) -> Message:
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("utf-8")

        msg = Message.construct_auto_file(
            chat_id=chat_id,
            display_content=f"File Uploaded: {file_path.name}",
            system_content=content,
            content_type=content_type,
            role=Role(config.APP_ROLE_NAME, config.APP_ROLE_AVATAR_COLOR),
        )

        return msg

    def parse_pdf(self, file_path: str, chat_id: str) -> list[Message]:
        text = ""
        if config.USE_MISTRAL_OCR and os.environ.get("MISTRAL_API_KEY"):
            client = Mistral(api_key=os.environ.get("MISTRAL_API_KEY"))
            signed_url = self._upload_file_to_mistral_dataset(client, file_path)

            logger.info("Processing PDF with Mistral OCR...")
            ocr_response = client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "document_url",
                    "document_url": signed_url.url,
                },
                include_image_base64=True,
            )
            logger.info("OCR response received!")
            for idx, p in enumerate(ocr_response.pages):
                if idx == 0:
                    logger.debug(p.markdown)
                text += p.markdown + " "

            messages = [
                Message.construct_auto_file(
                    chat_id,
                    display_content=f"File Uploaded: {file_path.rsplit('/', 1)[-1]}",
                    system_content=text,
                    content_type=ContentType.TEXT,
                    role=Role("App", ft.Colors.GREY),
                )
            ]
            for page in ocr_response.pages:
                if len(page.images) == 0:
                    continue

                for img in page.images:
                    messages.append(
                        Message.construct_auto_file(
                            chat_id,
                            display_content=f"Image: {img.id}",
                            system_content=img.image_base64.replace(
                                "data:image/jpeg;base64,", ""
                            ),
                            content_type=ContentType.JPEG,
                            role=Role("App", ft.Colors.GREY),
                        )
                    )
        else:
            logger.info("Using pdfplumber to parse PDF")
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text()

            messages = [
                Message.construct_auto_file(
                    chat_id,
                    display_content=f"File Uploaded: {file_path.name}",
                    system_content=text,
                    content_type=ContentType.TEXT,
                    role=Role("App", ft.Colors.GREY),
                )
            ]

        return messages

    def _upload_file_to_mistral_dataset(self, client: Mistral, file_path: Path) -> str:
        logger.info("Using Mistral OCR to parse PDF")

        logger.info(f"Uploading File to Mistral...: {file_path}")
        uploaded_pdf = client.files.upload(
            file={
                "file_name": file_path.split("/")[-1],
                "content": open(file_path, "rb"),
            },
            purpose="ocr",
        )

        return client.files.get_signed_url(file_id=uploaded_pdf.id)
