from dataclasses import dataclass
import flet as ft
from openai import OpenAI
import os

USER_NAME = "Yudai"
DISABLE_AI = False


@dataclass
class User:
    user_name: str
    avatar_color: ft.Colors


@dataclass
class Message:
    user: User
    text: str
    message_type: str


class ChatMessage(ft.Row):
    def __init__(self, message: Message):
        super().__init__()
        self.vertical_alignment = ft.CrossAxisAlignment.START
        self.controls = [
            ft.CircleAvatar(
                content=ft.Text(self.get_initials(message.user.user_name)),
                color=ft.Colors.WHITE,
                bgcolor=message.user.avatar_color,
            ),
            ft.Column(
                [
                    ft.Text(message.user.user_name, weight="bold"),
                    ft.Markdown(
                        message.text, extension_set="gitHubWeb", selectable=True
                    ),
                ],
                tight=True,
                spacing=5,
                expand=True,
            ),
        ]

    def get_initials(self, user_name: str):
        if user_name:
            return user_name[:1].capitalize()
        else:
            return "Unknown"


def add_system_message(message: Message, agent: User):
    if not DISABLE_AI:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": message.text,
                }
            ],
            model="gpt-4o-mini",
        )
        content = chat_completion.choices[0].message.content
    else:
        content = "Hi"

    accepted_message = Message(agent, content, message_type="system_message")
    return accepted_message


def main(page: ft.Page):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"

    human = User(USER_NAME, ft.Colors.GREEN)
    agent = User("System", ft.Colors.RED)

    def send_message_click(e):
        if new_message.value != "":
            user_message = Message(
                human,
                new_message.value,
                message_type="chat_message",
            )
            chat.controls.append(ChatMessage(user_message))
            new_message.value = ""
            new_message.focus()
            page.update()

            ai_message = add_accepted_message(user_message, agent)
            chat.controls.append(ChatMessage(ai_message))
            page.update()

    page.session.set("user_name", USER_NAME)

    # Chat messages
    chat = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=True,
    )

    # A new message entry form
    new_message = ft.TextField(
        hint_text="Write a message...",
        autofocus=True,
        shift_enter=True,
        min_lines=1,
        max_lines=5,
        filled=True,
        expand=True,
        on_submit=send_message_click,
    )

    # Add everything to the page
    page.add(
        ft.Container(
            content=chat,
            border=ft.border.all(1, ft.Colors.OUTLINE),
            border_radius=5,
            padding=10,
            expand=True,
        ),
        ft.Row(
            [
                new_message,
                ft.IconButton(
                    icon=ft.Icons.SEND_ROUNDED,
                    tooltip="Send message",
                    on_click=send_message_click,
                ),
            ]
        ),
    )


if __name__ == "__main__":
    ft.app(target=main)
