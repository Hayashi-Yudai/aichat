from datetime import datetime
import uuid

import flet as ft
from loguru import logger

from agent_config import model_agent_mapping, DEFAULT_MODEL
from messages import Message
from roles import User, System
from components.chat_space import MainView
from components.left_side_bar import LeftSideBar

from tables import ChatTableRow
from db import DB

USER_NAME = "Yudai"


def main(page: ft.Page, database: DB):
    logger.info("Starting Flet Chat")
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"
    page.window.width = 1200

    page.session.set("chat_history", [])  # list[ChatMessage]
    page.session.set("chat_id", str(uuid.uuid4()))
    page.session.set("agent", model_agent_mapping(DEFAULT_MODEL))
    page.session.set("user", User(USER_NAME, ft.Colors.GREEN))
    page.session.set("app_agent", System("App", ft.Colors.GREY))

    def chat_id_bind(topic, message):
        """
        chat_id が変更されたらUIに表示されるチャット履歴を更新する
        """
        logger.info(f"Chat ID: {page.session.get('chat_id')}")
        role_map = {
            USER_NAME: page.session.get("user"),
            "App": page.session.get("app_agent"),
            "Agent": page.session.get("agent"),
        }
        _chat_messages = database.get_chat_messages_by_chat_id(
            page.session.get("chat_id")
        )
        _chat_messages = [Message.from_tuple(m, role_map) for m in _chat_messages]

        page.session.set("chat_history", _chat_messages)
        page.pubsub.send_all_on_topic("chat_history", None)
        page.update()

    page.pubsub.subscribe_topic("chat_id", chat_id_bind)
    chat_started_at = datetime.now()
    ChatTableRow(page.session.get("chat_id"), chat_started_at).insert_into(database)

    left_side_bar = LeftSideBar(page, db=database)
    main_view = MainView(page, database)

    page.add(
        ft.Row(
            [left_side_bar, main_view],
            expand=True,
        )
    )


if __name__ == "__main__":
    database = DB("chat.db")
    ft.app(target=lambda page: main(page, database))
