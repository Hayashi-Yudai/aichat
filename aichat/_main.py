import flet as ft
from loguru import logger

# from agents.agent import DummyAgent
from agents.openai_agent import OpenAIAgent, OpenAIModel
import config
from database.db import SQLiteDB
from views.message_input_area import UserMessageArea
from views.chat_display_area import ChatMessageDisplayContainer
from views.left_side_bar_area import LeftSideBarArea


def main(page: ft.Page):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "AI Chat"

    logger.debug("Initialize agent...")
    agent = OpenAIAgent(OpenAIModel.GPT4OMINI)

    # Database
    db = SQLiteDB(is_debug=config.IS_DEBUG)

    # Widgets
    user_message_area = UserMessageArea(page=page, db=db)
    chat_messages_display_container = ChatMessageDisplayContainer(
        page=page, agent=agent, db=db
    )
    left_side_bar_area = LeftSideBarArea(page=page, default_agent=agent, db=db)

    # overlayにwidgetを登録
    page.overlay.extend([user_message_area.file_picker])

    page.add(
        ft.Row(
            [
                left_side_bar_area,
                ft.Column(
                    [chat_messages_display_container, user_message_area], expand=True
                ),
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
