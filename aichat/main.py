import uuid

import flet as ft
from loguru import logger

from agents.openai_agent import OpenAIAgent, OpenAIModel
from views.message_input_area import UserMessageArea
from views.chat_display_area import ChatMessageDisplayContainer
from views.left_side_bar_area import LeftSideBarArea

from utils.state_store import State, StateDict


def main(page: ft.Page):
    page.window.width = 1200
    page.window.height = 800
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "AI Chat"
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.GREY_50,
    )
    page.theme_mode = ft.ThemeMode.DARK

    logger.debug("Initialize agent...")
    agent = OpenAIAgent(OpenAIModel.GPT4OMINI)

    state_dict = StateDict({"chat_id": State(str(uuid.uuid4())), "agent": State(agent)})

    # Widgets
    user_message_area = UserMessageArea(page=page, state_dict=state_dict)
    chat_messages_display_container = ChatMessageDisplayContainer(
        page=page, agent=agent, state_dict=state_dict
    )
    left_side_bar_area = LeftSideBarArea(
        page=page, default_agent=agent, state_dict=state_dict
    )

    # overlayにwidgetを登録
    page.overlay.extend([user_message_area.file_picker])

    page.add(
        ft.Row(
            [
                ft.Container(left_side_bar_area),
                ft.VerticalDivider(
                    width=1,
                    color=ft.Colors.with_opacity(0.5, ft.Colors.WHITE),
                ),
                ft.Column(
                    [chat_messages_display_container, user_message_area],
                    expand=True,
                ),
            ],
            expand=True,
            spacing=0,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
