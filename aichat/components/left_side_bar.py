import uuid
import datetime
from typing import Callable

import flet as ft
from loguru import logger

from agent_config import model_agent_mapping, MODELS
from db import DB
from tables import ChatTable
from messages import Message


class PastChatItem(ft.Container):
    def __init__(self, page: ft.Page, db: DB, chat_id: str, text: str):
        super().__init__()

        self.chat_id = chat_id
        self.text = text
        self.page = page
        self.db = db

        self.content = ft.Text(self._process_text(text))
        self.on_click = self.on_click_func

    def _process_text(self, text: str):
        if len(text) > 20:
            return text[:20] + "..."

        return text

    def on_click_func(self, e: ft.ControlEvent):
        logger.info(f"Clicked {self.chat_id}")

        self.page.session.set("chat_id", self.chat_id)
        self.page.pubsub.send_all_on_topic("chat_id", self.chat_id)

        role_map = {
            self.page.session.get("user").name: self.page.session.get("user"),
            "App": self.page.session.get("app_agent"),
            "Agent": self.page.session.get("agent"),
        }
        _chat_messages = self.db.get_chat_messages_by_chat_id(
            self.page.session.get("chat_id")
        )
        _chat_messages = [Message.from_tuple(m, role_map) for m in _chat_messages]

        self.page.session.set("chat_history", _chat_messages)
        self.page.pubsub.send_all_on_topic("chat_history", None)


class PastChatList(ft.ListView):
    def __init__(self, page: ft.Page, db: DB):
        super().__init__()
        self.expand = True
        self.spacing = 10

        self.db = db
        self.page = page
        self.page.pubsub.subscribe_topic("past_chat_list", self._load_past_chat_list)

        self._load_past_chat_list()

    def _load_past_chat_list(self, topic=None, message=None):
        logger.info("Loading past chat list")
        self.controls = []
        for past_chat in self.db.get_past_chat_list():
            chat_id = past_chat[0]
            t = past_chat[1]
            self.controls.append(
                PastChatItem(self.page, self.db, chat_id=chat_id, text=t)
            )

        self.page.update()


class LeftSideBarContainer(ft.Container):
    def __init__(self, content: ft.Control):
        super().__init__()
        self.content = content
        self.border = ft.border.all(1, ft.Colors.OUTLINE)
        self.border_radius = 5
        self.padding = 10
        self.expand = True


class NewChatButton(ft.IconButton):
    def __init__(self, on_click: Callable):
        super().__init__()

        self.icon = ft.Icons.OPEN_IN_NEW_ROUNDED
        self.tooltip = "New chat"
        self.on_click = on_click


class ModelSelector(ft.Dropdown):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.expand = True

        self.options = [ft.dropdown.Option(m.model_name) for m in MODELS]
        self.value = page.session.get("agent").model_name
        self.page = page
        self.on_change = self.on_change_func

    def on_change_func(self, e: ft.ControlEvent):
        logger.info(f"Model selected: {self.value}")
        self.page.session.set("agent", model_agent_mapping(self.value))


class LeftSideBar(ft.Column):
    def __init__(self, page: ft.Page, db: DB, width: int):
        super().__init__()
        self.expand = False
        self.width = width
        self.padding = 10
        self.border = ft.border.all(1, ft.Colors.OUTLINE)
        self.border_radius = 5

        self.chat_list = PastChatList(page, db)
        self.controls = [
            ft.Row(
                [
                    NewChatButton(on_click=self.create_new_chat),
                    ModelSelector(page),
                ],
                expand=False,
            ),
            LeftSideBarContainer(content=self.chat_list),
        ]

        self.page = page
        self.db = db

    def create_new_chat(self, e: ft.ControlEvent):
        logger.info("Creating new chat")
        new_chat_id = str(uuid.uuid4())
        chat_started_at = datetime.datetime.now()

        self.page.session.set("chat_id", new_chat_id)
        self.page.pubsub.send_all_on_topic("chat_id", None)
        ChatTable(new_chat_id, chat_started_at).insert_into(self.db)
