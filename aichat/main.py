from datetime import datetime
import uuid

import flet as ft
from loguru import logger

from messages import Message
from state import ListState, PrimitiveState
from roles import Agent, DummyAgent, OpenAIAgent, User, System
from components.chat_space import MainView, FileLoader, ChatMessage
from components.left_side_bar import LeftSideBar

from tables import ChatTableRow
from db import DB

USER_NAME = "Yudai"
DISABLE_AI = False
MODEL_NAME = "gpt-4o-mini"


def main(page: ft.Page, database: DB):
    logger.info("Starting Flet Chat")
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"

    chat_history_state = ListState([])  # list[ChatMessage]

    human = User(USER_NAME, ft.Colors.GREEN)
    app_agent = System("App", ft.Colors.GREY)
    agent: Agent
    if not DISABLE_AI:
        agent = OpenAIAgent(MODEL_NAME)
    else:
        agent = DummyAgent()

    def chat_id_bind():
        logger.info(f"Chat ID: {chat_id.get()}")
        role_map = {USER_NAME: human, "System": app_agent, "Agent": agent}
        _chat_messages = database.get_chat_messages_by_chat_id(chat_id)
        _chat_messages = [
            ChatMessage(Message.from_tuple(m, role_map)) for m in _chat_messages
        ]
        breakpoint()

        chat_history_state.set_value(_chat_messages)

        page.update()

    chat_id = PrimitiveState(str(uuid.uuid4()))
    chat_id.bind(chat_id_bind)
    chat_started_at = datetime.now()
    ChatTableRow(chat_id.get(), chat_started_at).insert_into(database)

    file_picker = FileLoader(database, chat_history_state, app_agent, agent, chat_id)
    page.overlay.append(file_picker)

    page.add(
        ft.Row(
            [
                LeftSideBar(db=database, chat_id=chat_id),
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
