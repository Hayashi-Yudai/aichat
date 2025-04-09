import uuid

import flet as ft
from loguru import logger

from agents import Agent, all_models
from controllers.left_side_bar_controller import PastChatListController
from topics import Topics


class NewChatButton(ft.IconButton):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.pubsub = page.pubsub
        self.session = page.session

        self.icon = ft.Icons.OPEN_IN_NEW_ROUNDED
        self.toolchip = "New Chat"
        self.color = ft.Colors.GREEN

        self.on_click = self.on_click_func

    def on_click_func(self, e: ft.ControlEvent):
        logger.info(f"{self.__class__.__name__} published topic: {Topics.NEW_CHAT}")
        self.session.set("chat_id", str(uuid.uuid4()))
        self.pubsub.send_all_on_topic(Topics.NEW_CHAT, None)


class ModelSelector(ft.Dropdown):
    def __init__(self, page: ft.Page, default_agent: Agent):
        super().__init__()

        self.options = [ft.dropdown.Option(m) for m in all_models]

        self.value = default_agent.model

        self.tight = True
        self.expand = True
        self.on_change = self.on_change_func

        self.pubsub = page.pubsub

    def on_change_func(self, e: ft.ControlEvent):
        logger.info(f"Agent changed to: {e.data}")

        self.pubsub.send_all_on_topic(Topics.CHANGE_AGENT, e.data)


class PastChatItem(ft.ListTile):
    def __init__(self, page: ft.Page, chat_id: int, text: str):
        super().__init__()

        self.page = page
        self.pubsub = page.pubsub
        self.session = page.session
        self.chat_id = chat_id

        self.expand = True
        self.text = text
        self.padding = ft.padding.only(left=0, right=10, top=10, bottom=10)
        self.content_padding = 0
        self.spacing = 10

        self.leading = ft.Icon(ft.Icons.NOTES_ROUNDED, color=ft.Colors.WHITE70, size=13)
        self.title = ft.Text(text[:16], color=ft.Colors.WHITE, size=13)
        self.dense = (True,)
        self.on_click = self.on_click_func
        self.on_hover = self.on_hover_func

    def on_click_func(self, e: ft.ControlEvent):
        self.session.set("chat_id", self.chat_id)
        self.pubsub.send_all_on_topic(Topics.PAST_CHAT_RESTORED, self.chat_id)

    def on_hover_func(self, e: ft.HoverEvent):
        if self.page.theme_mode == ft.ThemeMode.LIGHT:
            self.bgcolor = ft.Colors.GREEN_50 if e.data == "true" else None
        else:
            self.bgcolor = ft.Colors.GREY_900 if e.data == "true" else None
        self.update()


class PastChatList(ft.ListView):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.page = page
        self.expand = True
        self.controller = PastChatListController()

        self.update_controls(page)
        page.pubsub.subscribe_topic(Topics.UPDATE_CHAT, self._update_controls)

    def update_controls(self, page: ft.Page):
        chats = self.controller.collect_all_chat()
        self.controls = [PastChatItem(page, c.id, c.title) for c in chats]

    def _update_controls(self, topic: Topics, data: list):
        logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        self.update_controls(self.page)
        self.update()


class PastChatListContainer(ft.Container):
    def __init__(self, content: ft.Control):
        super().__init__()

        self.content = content
        self.border = ft.border.all(0, ft.Colors.TRANSPARENT)
        self.padding = 10
        self.expand = True


class LeftSideBarArea(ft.Column):
    def __init__(self, page: ft.Page, default_agent: Agent):
        super().__init__()

        self.expand = False
        self.width = 300
        self.spacing = 10

        # Widgets
        new_chat_button = NewChatButton(page)
        model_selector = ModelSelector(page, default_agent)

        past_chat_list = PastChatList(page)
        past_chat_list_container = PastChatListContainer(content=past_chat_list)

        self.controls = [
            ft.Row([new_chat_button, model_selector], expand=False, tight=True),
            past_chat_list_container,
        ]
