from datetime import datetime
import uuid

import flet as ft

from state import ListState
from roles import Agent, DummyAgent, OpenAIAgent, User, System
from components.chat_space import MainView, FileLoader
from components.left_side_bar import LeftSideBar

from tables import ChatTableRow
from db import DB

USER_NAME = "Yudai"
DISABLE_AI = False
MODEL_NAME = "gpt-4o-mini"


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
    file_picker = FileLoader(database, chat_history_state, app_agent, agent, chat_id)
    page.overlay.append(file_picker)

    page.add(
        ft.Row(
            [
                LeftSideBar(db=database),
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
