import flet as ft

from agents.agent import DummyAgent
from views.message_input_area import UserMessageArea
from views.chat_display_area import ChatMessageDisplayContainer


def main(page: ft.Page):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "AI Chat"

    agent = DummyAgent()

    # Widgets
    user_message_area = UserMessageArea(page=page)
    chat_messages_display_container = ChatMessageDisplayContainer(
        page=page, agent=agent
    )

    # overlayにwidgetを登録
    page.overlay.extend([user_message_area.file_picker])

    page.add(
        ft.Column([chat_messages_display_container, user_message_area], expand=True)
    )


if __name__ == "__main__":
    ft.app(target=main)
