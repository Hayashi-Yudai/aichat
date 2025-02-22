import flet as ft
from loguru import logger

from models.message import Message

from controllers.chat_display_controller import ChatDisplayController
from topics import Topics


class _ChatMessage(ft.Row):
    def __init__(self, message: Message):
        super().__init__()

        self._message = message

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

    @property
    def message(self) -> Message:
        return self._message


class _ChatMessageList(ft.ListView):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub

        self.expand = True
        self.spacing = 10
        self.controls = []

        self._item_builder = _ChatMessage
        self.controller = ChatDisplayController(item_builder=self._item_builder)
        self.pubsub.subscribe_topic(
            Topics.SUBMIT_MESSAGE, self.append_new_message_to_list
        )

    def append_new_message_to_list(self, topic: Topics, message: str):
        logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        self.controls.append(self._item_builder(message))

        agent_response = self.controller.get_agent_response(self.controls)
        logger.info("Request to agent...")
        self.controls.append(agent_response)

        self.update()


class ChatMessageContainer(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub

        self.border = ft.border.all(1, ft.Colors.OUTLINE)
        self.border_radius = 5
        self.padding = 10
        self.expand = True
        self.content = _ChatMessageList(page)
