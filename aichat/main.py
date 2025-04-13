import uuid

import flet as ft
from loguru import logger
from pathlib import Path  # Added Path import

from agents.agent import AgentController
from agents.openai_agent import OpenAIAgent, OpenAIModel
from agents.mcp_handler import McpHandler  # Added McpHandler import
from views.message_input_area import UserMessageArea
from views.chat_display_area import ChatMessageDisplayContainer
from views.left_side_bar_area import LeftSideBarArea


def main(page: ft.Page):
    page.window.width = 1200
    page.window.height = 800
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "AI Chat"
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.GREY_50,
    )
    page.theme_mode = ft.ThemeMode.DARK

    logger.debug("Initialize MCP Handler and agent...")
    # Define the path to the MCP server script relative to main.py
    mcp_server_script = Path(__file__).parent / "agents/mcp_servers/weather.py"
    mcp_handler = McpHandler(server_script_path=mcp_server_script)
    agent = OpenAIAgent(OpenAIModel.GPT4OMINI, mcp_handler=mcp_handler)  # Pass handler

    _ = AgentController(page=page)

    # Session Variables
    page.session.set("chat_id", str(uuid.uuid4()))
    page.session.set("agent", agent)

    # Widgets
    user_message_area = UserMessageArea(page=page)
    chat_messages_display_container = ChatMessageDisplayContainer(page=page)
    left_side_bar_area = LeftSideBarArea(page=page, default_agent=agent)

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
