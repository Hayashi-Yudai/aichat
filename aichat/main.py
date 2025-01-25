from datetime import datetime
import uuid

import flet as ft

from state import ListState
from roles import Agent, DummyAgent, OpenAIAgent, User, System
from components.chat_space import MainView, FileLoader

from tables import ChatTableRow
from db import DB

USER_NAME = "Yudai"
DISABLE_AI = False
MODEL_NAME = "gpt-4o-mini"


class PastChatList(ft.ListView):
    def __init__(self):
        super().__init__()
        self.expand = True
        self.auto_scroll = True
        self.spacing = 10


def main(page: ft.Page, database: DB):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"

    chat_id = str(uuid.uuid4())
    chat_started_at = datetime.now()
    ChatTableRow(chat_id, chat_started_at).insert_into(database)

    human = User(USER_NAME, ft.Colors.GREEN)
    app_agent = System("App", ft.Colors.GREY)
    agent: Agent
    if not DISABLE_AI:
        agent = OpenAIAgent(MODEL_NAME)
    else:
        agent = DummyAgent()

    chat_history_state = ListState([])

    file_picker = FileLoader(chat_history_state, app_agent, agent)
    page.overlay.append(file_picker)

    past_chat_list = PastChatList()

    for past_chat in database.get_past_chat_list():
        t = past_chat[1]
        if len(t) > 20:
            t = t[:20] + "..."
        past_chat_list.controls.append(ft.Text(t))

    page.add(
        ft.Row(
            [
                ft.Container(
                    content=past_chat_list,
                    border=ft.border.all(1, ft.Colors.OUTLINE),
                    border_radius=5,
                    padding=10,
                    width=200,
                ),
                MainView(
                    human, agent, database, chat_history_state, file_picker, chat_id
                ),
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    database = DB("chat.db")
    ft.app(target=lambda page: main(page, database))
