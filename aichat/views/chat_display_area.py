import flet as ft
from loguru import logger

from models.message import Message, ContentType
from controllers.chat_display_controller import ChatDisplayController
from topics import Topics


class _ChatMessage(ft.Row):
    def __init__(self, page: ft.Page, message: Message):
        super().__init__()

        self.message = message
        self.exclude_from_agent_request = False

        self.vertical_alignment = ft.CrossAxisAlignment.START

        match message.content_type:
            case ContentType.TEXT:
                content = ft.Markdown(
                    message.display_content,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    md_style_sheet=ft.MarkdownStyleSheet(
                        blockquote_decoration=ft.BoxDecoration(bgcolor=ft.Colors.GREY)
                    ),
                    on_tap_link=lambda e: page.launch_url(e.data),
                )
            case ContentType.PNG | ContentType.JPEG:
                content = ft.Column(
                    [
                        ft.Text(message.display_content),
                        ft.Image(src_base64=message.system_content, width=500),
                    ]
                )

        self.controls = [
            ft.CircleAvatar(
                content=ft.Text(message.role.name[0]),
                color=ft.Colors.WHITE,
                bgcolor=message.role.avatar_color,
            ),
            ft.Column(
                [ft.Text(message.role.name), ft.SelectionArea(content)],
                tight=True,
                spacing=5,
                expand=True,
            ),
        ]


class InprogressMessage(ft.Row):
    def __init__(self, message: str):
        super().__init__()

        self.exclude_from_agent_request = True

        self.controls = [
            ft.ProgressRing(height=18, width=18, color=ft.Colors.BLUE),
            ft.Text(message, color=ft.Colors.GREY),
        ]


class _ChatMessageList(ft.ListView):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub

        self.expand = True
        self.spacing = 10
        self.auto_scroll = False
        self.controls: list[_ChatMessage] = []

        self._item_builder = _ChatMessage
        self.controller = ChatDisplayController(
            page=page,
            update_content_callback=self.update_content_func,
            item_builder=_ChatMessage,
        )

        self.pubsub.subscribe_topic(Topics.APPEND_MESSAGE, self.append_message)
        self.pubsub.subscribe_topic(
            Topics.UPDATE_MESSAGE_STREAMLY, self.update_message_streamly
        )
        self.pubsub.subscribe_topic(Topics.PAST_CHAT_RESTORED, self.restore_past_chat)
        self.pubsub.subscribe_topic(Topics.NEW_CHAT, self.new_chat)

    async def update_content_func(self, controls: list[ft.Control]):
        self.controls = controls
        self.update()

    def append_message(self, topic: Topics, message: Message):
        logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        self.controller.add_new_message(self.controls, message)

    def update_message_streamly(self, topic: Topics, message: Message):
        # logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        self.controller.update_message_streamly(self.controls, message)

    def restore_past_chat(self, topic: Topics, chat_id: str):
        logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        self.controller.restore_past_chat(chat_id)

    def new_chat(self, topic: Topics, chat_id: str):
        logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        self.controller.clear_controls()


class ChatMessageDisplayContainer(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub

        self.border_radius = 5
        self.expand = True
        self.border = ft.border.all(0, ft.Colors.TRANSPARENT)
        self.padding = ft.padding.only(left=15, right=20, top=0, bottom=0)
        self.content = _ChatMessageList(page)
