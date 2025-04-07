import uuid

import flet as ft
from loguru import logger

from agents.openai_agent import OpenAIAgent, OpenAIModel
from views.message_input_area import UserMessageArea
from views.chat_display_area import ChatMessageDisplayContainer
from views.left_side_bar_area import LeftSideBarArea


def main(page: ft.Page):
    page.window.width = 1200
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "AI Chat"
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.GREY_50,
    )
    page.theme_mode = ft.ThemeMode.DARK

    logger.debug("Initialize agent...")
    agent = OpenAIAgent(OpenAIModel.GPT4OMINI)

    # Session Variables
    page.session.set("chat_id", str(uuid.uuid4()))

    # Widgets
    user_message_area = UserMessageArea(page=page)
    chat_messages_display_container = ChatMessageDisplayContainer(
        page=page, agent=agent
    )
    left_side_bar_area = LeftSideBarArea(page=page, default_agent=agent)

    # overlayにwidgetを登録
    page.overlay.extend([user_message_area.file_picker])

    page.add(
        ft.Row(
            [
                ft.Container(left_side_bar_area, bgcolor=ft.Colors.GREY_900),
                ft.Column(
                    [chat_messages_display_container, user_message_area], expand=True
                ),
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
