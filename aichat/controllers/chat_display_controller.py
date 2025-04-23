from typing import Callable

import flet as ft
from loguru import logger

from topics import Topics
from models.message import Message


class ChatDisplayController:
    def __init__(
        self,
        page: ft.Page,
        update_content_callback: Callable[[list[ft.Row]], None],
        item_builder: Callable[[Message], ft.Row],
    ):
        self.page = page
        self.update_content_callback = update_content_callback
        self.item_builder = item_builder

    def restore_past_chat(self, chat_id: str):
        messages = self._get_all_messages_by_chat_id(chat_id)
        self.page.run_task(
            self.update_content_callback,
            [self.item_builder(self.page, m) for m in messages],
        )

    def clear_controls(self):
        self.page.run_task(self.update_content_callback, [])

    def add_new_message(self, controls: list[ft.Row], message: Message | list[Message]):
        message = message if isinstance(message, list) else [message]
        new_controls = controls + [self.item_builder(self.page, m) for m in message]
        self.page.run_task(self.update_content_callback, new_controls)

        self.page.pubsub.send_all_on_topic(
            Topics.REQUEST_TO_AGENT, [ctl.message for ctl in new_controls]
        )

        self.page.pubsub.send_all_on_topic(Topics.UPDATE_CHAT, None)
        logger.debug(
            f"{self.__class__.__name__} published topic: {Topics.REQUEST_TO_AGENT}"
        )

    def update_message_streamly(self, controls: list[ft.Row], message: Message):
        if controls[-1].message.role.avatar_color == message.role.avatar_color:
            controls[-1] = self.item_builder(self.page, message)
        else:
            controls.append(self.item_builder(self.page, message))
        self.page.run_task(self.update_content_callback, controls)

    def _get_all_messages_by_chat_id(self, chat_id: int) -> list[Message]:
        return Message.get_all_by_chat_id(chat_id)
