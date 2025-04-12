from typing import Callable

import flet as ft

import config
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
        self.update_content_callback([self.item_builder(m) for m in messages])

    def clear_controls(self):
        self.update_content_callback([])

    def add_new_message(self, controls: list[ft.Row], message: Message | list[Message]):
        if isinstance(message, list):
            need_agent_request = (
                message[-1].role.avatar_color == config.USER_AVATAR_COLOR
            )

            msg = [self.item_builder(m) for m in message]
            new_control = controls + msg
            self.update_content_callback(new_control)
        else:
            need_agent_request = message.role.avatar_color == config.USER_AVATAR_COLOR

            new_control = controls + [self.item_builder(message)]
            self.update_content_callback(new_control)

        if need_agent_request:
            messages = [ctl.message for ctl in new_control]
            self.page.pubsub.send_all_on_topic(Topics.REQUEST_TO_AGENT, messages)

        self.page.pubsub.send_all_on_topic(Topics.UPDATE_CHAT, None)

    def update_latest_message(self, controls: list[ft.Row], message: Message):
        controls[-1] = self.item_builder(message)
        self.update_content_callback(controls)

    def _get_all_messages_by_chat_id(self, chat_id: int) -> list[Message]:
        return Message.get_all_by_chat_id(chat_id)
