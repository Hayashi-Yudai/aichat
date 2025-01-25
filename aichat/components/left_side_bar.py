import flet as ft
from loguru import logger

from db import DB
from state import State


class PastChatItem(ft.Container):
    def __init__(self, chat_id: str, text: str, chat_id_state: State):
        super().__init__()

        self.chat_id = chat_id
        self.text = text
        self.chat_id_state = chat_id_state

        self.content = ft.Text(self._process_text(text))
        self.on_click = self.on_click_func

    def _process_text(self, text: str):
        if len(text) > 20:
            return text[:20] + "..."

        return text

    def on_click_func(self, e: ft.ControlEvent):
        logger.info(f"Clicked {self.chat_id}")

        self.chat_id_state.set_value(self.chat_id)


class PastChatList(ft.ListView):
    def __init__(self, db: DB, chat_id: State):
        super().__init__()
        self.expand = True
        self.auto_scroll = True
        self.spacing = 10

        self.db = db
        self.chat_id_state = chat_id

        self._load_past_chat_list()

    def _load_past_chat_list(self):
        for past_chat in self.db.get_past_chat_list():
            chat_id = past_chat[0]
            t = past_chat[1]
            self.controls.append(PastChatItem(chat_id=chat_id, text=t, chat_id_state=self.chat_id_state))


class LeftSideBarContainer(ft.Container):
    def __init__(self, content: ft.Control):
        super().__init__()
        self.content = content
        self.border = ft.border.all(1, ft.Colors.OUTLINE)
        self.border_radius = 5
        self.padding = 10
        self.expand = True


class LeftSideBar(ft.Column):
    def __init__(self, db: DB, chat_id: State):
        super().__init__()
        self.expand = False
        self.width = 200
        self.padding = 10
        self.border = ft.border.all(1, ft.Colors.OUTLINE)
        self.border_radius = 5

        self.controls = [LeftSideBarContainer(content=PastChatList(db, chat_id))]

        self.chat_id = chat_id
