import flet as ft
from loguru import logger

from controllers.message_input_controller import (
    MessageInputController,
    FileLoaderController,
)


class _MessageInputArea(ft.TextField):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub
        self.session = page.session

        self.border = ft.InputBorder.NONE
        self.focused_border_color = ft.Colors.TRANSPARENT
        self.hint_text = "Write a message..."
        self.autofocus = True
        self.shift_enter = False
        self.min_lines = 1
        self.max_lines = 5
        self.expand = True
        self.value = ""

        self.controller = MessageInputController(
            page=page, update_view_callback=self.update, focus_callback=self.focus
        )
        self.on_submit = self.on_submit_func

    def on_submit_func(self, e: ft.ControlEvent):
        self.controller.send_message(self.session.get("chat_id"), e.control.value)
        self.value = ""


class _FileLoader(ft.FilePicker):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub
        self.session = page.session

        self.expand = True
        self.on_result = self.on_result_func

        self.controller = FileLoaderController(
            pubsub=page.pubsub, update_view_callback=self.update
        )

    def on_result_func(self, e: ft.FilePickerResultEvent):
        logger.debug(f"Uploaded files: {e.files}")
        for f in e.files:
            self.controller.append_file_content_to_chatlist(
                self.session.get("chat_id"), f
            )


class UserMessageArea(ft.Row):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub

        # Widgets
        self.file_picker = _FileLoader(page=page)

        self.file_loader_icon = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip="Upload file",
            on_click=lambda _: self.file_picker.pick_files(allow_multiple=True),
            style=ft.ButtonStyle(color=ft.Colors.WHITE),
        )
        self.message_input_area = _MessageInputArea(page=page)
        self.send_message_icon = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            tooltip="Send message",
            on_click=lambda _: self.message_input_area.controller.send_message(
                page.session.get("chat_id"), self.message_input_area.value
            ),
            style=ft.ButtonStyle(color=ft.Colors.WHITE),
        )

        self.controls = [
            ft.Container(
                border_radius=30,
                padding=ft.padding.only(top=10, left=15, right=15, bottom=10),
                margin=ft.margin.only(bottom=0, top=0, right=10, left=15),
                border=ft.border.all(2.0, ft.Colors.GREY_600),
                content=ft.Column(
                    [
                        ft.Container(
                            self.message_input_area, margin=ft.margin.only(left=8)
                        ),
                        ft.Container(
                            ft.Row(
                                [
                                    self.file_loader_icon,
                                    ft.Container(expand=True),
                                    self.send_message_icon,
                                ]
                            )
                        ),
                    ]
                ),
                expand=True,
            )
        ]
