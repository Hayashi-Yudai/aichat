import flet as ft
from loguru import logger

from models.message import Message

# from controllers.chat_display_controller import ChatDisplayController
from topics import Topics


class _ChatMessage(ft.Row):
    def __init__(self, message: Message):
        super().__init__()

        self.vertical_alignment = ft.CrossAxisAlignment.START
        self.controls = [
            ft.CircleAvatar(
                content=ft.Text(message.role.name[0]),
                color=ft.Colors.WHITE,
                bgcolor=message.role.avatar_color,
            ),
            ft.Column(
                [
                    ft.Text(message.role.name),
                    ft.SelectionArea(
                        ft.Markdown(
                            message.text,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        )
                    ),
                ],
                tight=True,
                spacing=5,
                expand=True,
            ),
        ]


class _ChatMessageList(ft.ListView):
    def __init__(self, pubsub: ft.PubSubClient):
        super().__init__()

        self.pubsub = pubsub

        self.expand = True
        self.spacing = 10
        self.controls = []

        self._item_builder = _ChatMessage
        # self.controller = ChatDisplayController(item_builder=self.item_builder)
        self.pubsub.subscribe_topic(Topics.SUBMIT_MESSAGE, self.update_message_list)

    def update_message_list(self, topic: Topics, message: str):
        logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        self.controls.append(self._item_builder(message))
        self.update()


class ChatMessageContainer(ft.Container):
    def __init__(self, pubsub: ft.PubSubClient):
        super().__init__()

        self.pubsub = pubsub

        self.border = ft.border.all(1, ft.Colors.OUTLINE)
        self.border_radius = 5
        self.padding = 10
        self.expand = True
        self.content = _ChatMessageList(self.pubsub)
