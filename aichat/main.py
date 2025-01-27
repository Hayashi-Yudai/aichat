from datetime import datetime
import uuid

import flet as ft
from loguru import logger

from messages import Message
from roles import (
    Agent,
    # DeepSeekAgent,
    DummyAgent,
    # OpenAIAgent,
    GeminiAgent,
    User,
    System,
)
from components.chat_space import MainView, FileLoader, ChatMessage
from components.left_side_bar import LeftSideBar

from tables import ChatTableRow
from db import DB

USER_NAME = "Yudai"
DISABLE_AI = False
# MODEL_NAME = "gpt-4o-mini"
# MODEL_NAME = "deepseek-chat"
MODEL_NAME = "gemini-1.5-flash"


def main(page: ft.Page, database: DB):
    logger.info("Starting Flet Chat")
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"

    page.session.set("chat_history", [])  # list[ChatMessage]
    page.session.set("chat_id", str(uuid.uuid4()))

    human = User(USER_NAME, ft.Colors.GREEN)
    app_agent = System("App", ft.Colors.GREY)
    agent: Agent
    if not DISABLE_AI:
        # agent = OpenAIAgent(MODEL_NAME)
        # agent = DeepSeekAgent(MODEL_NAME)
        agent = GeminiAgent(MODEL_NAME)
    else:
        agent = DummyAgent()

    def chat_id_bind(topic, message):
        """
        chat_id が変更されたらUIに表示されるチャット履歴を更新する
        """
        logger.info(f"Chat ID: {page.session.get('chat_id')}")
        role_map = {USER_NAME: human, "App": app_agent, "Agent": agent}
        _chat_messages = database.get_chat_messages_by_chat_id(
            page.session.get("chat_id")
        )
        _chat_messages = [
            ChatMessage(Message.from_tuple(m, role_map)) for m in _chat_messages
        ]

        page.session.set("chat_history", _chat_messages)
        page.pubsub.send_all_on_topic("chat_history", None)
        page.update()

    page.pubsub.subscribe_topic("chat_id", chat_id_bind)
    chat_started_at = datetime.now()
    ChatTableRow(page.session.get("chat_id"), chat_started_at).insert_into(database)

    file_picker = FileLoader(page, database, app_agent, agent)
    page.overlay.append(file_picker)

    left_side_bar = LeftSideBar(page, db=database)
    main_view = MainView(page, human, agent, database, file_picker)

    page.add(
        ft.Row(
            [left_side_bar, main_view],
            expand=True,
        )
    )


if __name__ == "__main__":
    database = DB("chat.db")
    ft.app(target=lambda page: main(page, database))
