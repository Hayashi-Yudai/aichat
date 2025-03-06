import flet as ft
from loguru import logger

from agents.agent import Agent, DummyModel
from agents.openai_agent import OpenAIModel
from database.db import DB
from topics import Topics


class NewChatButton(ft.IconButton):
    def __init__(self, page: ft.Page, db: DB):
        super().__init__()

        self.icon = ft.Icons.OPEN_IN_NEW_ROUNDED
        self.toolchip = "New Chat"
        self.color = ft.Colors.GREEN


class ModelSelector(ft.Dropdown):
    def __init__(self, page: ft.Page, default_agent: Agent, db: DB):
        super().__init__()

        dummy_model = [ft.dropdown.Option(m) for m in DummyModel]
        openai_models = [ft.dropdown.Option(m) for m in OpenAIModel]
        self.options = dummy_model + openai_models

        self.value = default_agent.model

        self.tight = True
        self.expand = True
        self.on_change = self.on_change_func

        self.pubsub = page.pubsub

    def on_change_func(self, e: ft.ControlEvent):
        logger.info(f"Agent changed to: {e.data}")

        self.pubsub.send_all_on_topic(Topics.CHANGE_AGENT, e.data)


class PastChatItem(ft.Container):
    def __init__(self, page: ft.Page, db: DB, chat_id: int, text: str):
        super().__init__()

        self.expand = True
        self.text = text

        self.content = ft.Text(text)
        self.on_click = self.on_click_func

    def on_click_func(self, e: ft.ControlEvent):
        logger.info(f"Chat ID: {self.text} clicked")


class PastChatList(ft.ListView):
    def __init__(self, page: ft.Page, db: DB):
        super().__init__()

        self.expand = True
        self.padding = 10
        self.spacing = 10

        self.controls = [
            PastChatItem(page, db, None, "test1"),
            PastChatItem(page, db, None, "test2"),
        ]


class PastChatListContainer(ft.Container):
    def __init__(self, content: ft.Control, db: DB):
        super().__init__()

        self.content = content
        self.border = ft.border.all(1, ft.Colors.OUTLINE)
        self.border_radius = 5
        self.padding = 10
        self.expand = True


class LeftSideBarArea(ft.Column):
    def __init__(self, page: ft.Page, default_agent: Agent, db: DB):
        super().__init__()

        self.expand = False
        self.width = 250
        self.spacing = 10

        # Widgets
        new_chat_button = NewChatButton(page, db)
        model_selector = ModelSelector(page, default_agent, db)

        past_chat_list = PastChatList(page, db)
        past_chat_list_container = PastChatListContainer(content=past_chat_list, db=db)

        self.controls = [
            ft.Row([new_chat_button, model_selector], expand=False, tight=True),
            past_chat_list_container,
        ]
