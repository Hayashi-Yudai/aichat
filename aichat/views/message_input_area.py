import flet as ft
from loguru import logger

from database.db import DB
from controllers.message_input_controller import (
    MessageInputController,
    FileLoaderController,
)


class _MessageInputArea(ft.TextField):
    def __init__(self, page: ft.Page, db: DB):
        super().__init__()

        self.pubsub = page.pubsub

        self.hint_text = "Write a message..."
        self.autofocus = True
        self.shift_enter = False
        self.min_lines = 1
        self.max_lines = 5
        self.filled = True
        self.expand = True
        self.value = ""

        self.controller = MessageInputController(page=page)
        self.on_submit = self.on_submit_func

    def on_submit_func(self, e: ft.ControlEvent):
        self.controller.send_message(e.control.value)
        self.value = ""

        self.focus()
        self.update()


class _FileLoader(ft.FilePicker):
    def __init__(self, page: ft.Page, db: DB):
        super().__init__()

        self.pubsub = page.pubsub

        self.expand = True
        self.on_result = self.on_result_func

        self.controller = FileLoaderController(pubsub=page.pubsub)

    def on_result_func(self, e: ft.ControlEvent):
        logger.debug(f"Uploaded files: {e.files}")
        for f in e.files:
            self.controller.append_file_content_to_chatlist(f)

        self.update()


class UserMessageArea(ft.Row):
    def __init__(self, page: ft.Page, db: DB):
        super().__init__()

        self.pubsub = page.pubsub

        # Widgets
        self.file_picker = _FileLoader(page=page, db=db)

        self.file_loader_icon = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip="Upload file",
            on_click=lambda _: self.file_picker.pick_files(allow_multiple=True),
        )
        self.message_input_area = _MessageInputArea(page=page, db=db)
        self.send_message_icon = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            tooltip="Send message",
            on_click=lambda _: self.message_input_area.controller.send_message(
                self.message_input_area.value
            ),
        )

        self.controls = [
            self.file_loader_icon,
            self.message_input_area,
            self.send_message_icon,
        ]
