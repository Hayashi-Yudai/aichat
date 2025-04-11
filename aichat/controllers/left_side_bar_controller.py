from typing import Callable, Type

# from loguru import logger
import flet as ft

from models.chat import Chat

from utils.state_store import StateDict


class PastChatListController:
    def __init__(
        self,
        update_view_callback: Callable[[list[ft.ListTile]], None],
        item_builder: Type[ft.ListTile],
        state_dict: StateDict,
    ):
        self.update_view_callback = update_view_callback
        self.item_builder = item_builder
        self.state_dict = state_dict

    def update_chat_list(self, page: ft.Page):
        chats = self.collect_all_chat()
        controls = [
            self.item_builder(page, c.id, c.title, self.state_dict) for c in chats
        ]

        self.update_view_callback(controls)

    def collect_all_chat(self) -> list[Chat]:
        chats = Chat.get_all()
        chats.sort(key=lambda x: x.created_at, reverse=True)

        return chats
