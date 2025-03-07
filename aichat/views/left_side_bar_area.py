import flet as ft
from loguru import logger

from agents.agent import Agent, DummyModel
from agents.openai_agent import OpenAIModel
from controllers.left_side_bar_controller import PastChatListController
from topics import Topics


class NewChatButton(ft.IconButton):
    def __init__(self, page: ft.Page):
        super().__init__()

        self.icon = ft.Icons.OPEN_IN_NEW_ROUNDED
        self.toolchip = "New Chat"
        self.color = ft.Colors.GREEN


class ModelSelector(ft.Dropdown):
    def __init__(self, page: ft.Page, default_agent: Agent):
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
    def __init__(self, page: ft.Page, chat_id: int, text: str):
        super().__init__()

        self.expand = True
        self.text = text
        self.padding = 10
        self.spacing = 10

        self.content = ft.Text(text)
        self.on_click = self.on_click_func
        self.on_hover = self.on_hover_func

    def on_click_func(self, e: ft.ControlEvent):
        logger.info(f"Chat ID: {self.text} clicked")

    def on_hover_func(self, e: ft.HoverEvent):
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

    def _update_controls(self, topic: str, data: list):
        logger.debug(f"{self.__class__.__name__} received topic: {topic}")
        self.update_controls(self.page)
        self.update()


class PastChatListContainer(ft.Container):
    def __init__(self, content: ft.Control):
        super().__init__()

        self.content = content
        self.border = ft.border.all(1, ft.Colors.OUTLINE)
        self.border_radius = 5
        self.padding = 10
        self.expand = True


class LeftSideBarArea(ft.Column):
    def __init__(self, page: ft.Page, default_agent: Agent):
        super().__init__()

        self.expand = False
        self.width = 250
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
