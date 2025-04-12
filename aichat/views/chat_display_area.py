import flet as ft
from loguru import logger

import config
from models.message import Message, ContentType

from controllers.chat_display_controller import ChatDisplayController
from topics import Topics


class _ChatMessage(ft.Row):
    def __init__(self, message: Message):
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

        self.pubsub.subscribe_topic(
            Topics.START_SUBMISSION,
            lambda _, msg: self.controller.add_new_message(
                self.controls, InprogressMessage(msg)
            ),
        )
        self.pubsub.subscribe_topic(
            Topics.SUBMIT_MESSAGE, self.append_new_message_to_list
        )
        self.pubsub.subscribe_topic(
            Topics.PAST_CHAT_RESTORED,
            lambda _, chat_id: self.controller.restore_past_chat(chat_id),
        )
        self.pubsub.subscribe_topic(
            Topics.NEW_CHAT, lambda _, __: self.controller.clear_controls()
        )

    def update_content_func(self, controls: list[ft.Control]):
        self.controls = controls
        self.update()

    def append_new_message_to_list(self, topic: Topics, messages: list[str]):
        logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        if len(self.controls) > 0 and isinstance(self.controls[-1], InprogressMessage):
            self.controls.pop()

        self.controller.add_new_message(
            self.controls, [self._item_builder(m) for m in messages]
        )
        if self.controls[-1].message.role.name == config.APP_ROLE_NAME:
            self.update()
            return

        self.controller.add_new_message(
            self.controls, InprogressMessage("Agent is typing...")
        )

        chat_id = self.controls[0].message.chat_id
        messages = [
            ctl.message for ctl in self.controls if not ctl.exclude_from_agent_request
        ]
        for i, agent_response in enumerate(
            self.controller.get_agent_response(chat_id, messages)
        ):
            if i == 0:
                self.controls.pop()
                self.controls.append(self._item_builder(agent_response))
            else:
                self.controls[-1] = self._item_builder(agent_response)

            self.auto_scroll = True
            self.update()

        self.auto_scroll = False
        self.update()

        logger.debug(f"{self.__class__.__name__} published topic: {Topics.UPDATE_CHAT}")
        self.pubsub.send_all_on_topic(Topics.UPDATE_CHAT, None)


class ChatMessageDisplayContainer(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub

        self.border_radius = 5
        self.expand = True
        self.border = ft.border.all(0, ft.Colors.TRANSPARENT)
        self.padding = ft.padding.only(left=15, right=20, top=0, bottom=0)
        self.content = _ChatMessageList(page)
