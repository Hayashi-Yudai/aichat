from dataclasses import dataclass
import flet as ft
from openai import OpenAI
import os
from typing import Iterable

from openai.types.chat import ChatCompletionMessageParam

USER_NAME = "Yudai"
DISABLE_AI = True


@dataclass
class User:
    user_name: str
    avatar_color: ft.Colors


class OpenAIAgent(User):
    def __init__(self, model_name: str):
        self.user_name = "System"
        self.avatar_color = ft.Colors.BLUE

        self.model_name = model_name
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        self.messages: Iterable[ChatCompletionMessageParam] = []

    def get_response(self, message: str):
        if not DISABLE_AI:
            self.messages.append({"role": "user", "content": message})
            chat_completion = self.client.chat.completions.create(
                messages=self.messages,
                model=self.model_name,
            )
            content = chat_completion.choices[0].message.content

            return Message(self, content)
        else:
            return Message(self, "Test")

    def append_file_into_messages(self, text: str):
        self.messages.append({"role": "user", "content": text})


@dataclass
class Message:
    user: User
    text: str


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


def main(page: ft.Page):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"

    human = User(USER_NAME, ft.Colors.GREEN)
    app_agent = User("App", ft.Colors.GREY)
    agent = OpenAIAgent("gpt-4o-mini")

    def send_message_click(e):
        if new_message.value != "":
            user_message = Message(
                human,
                new_message.value,
            )
            chat.controls.append(ChatMessage(user_message))
            new_message.value = ""
            new_message.focus()
            page.update()

            ai_message = agent.get_response(user_message.text)
            chat.controls.append(ChatMessage(ai_message))
            page.update()

    def load_file(e: ft.FilePickerResultEvent):
        for f in e.files:
            with open(f.path, "r") as d:
                text = d.read()

            chat.controls.append(ChatMessage(Message(app_agent, f"Uploaded: {f.name}")))
            page.update()
            agent.append_file_into_messages(text)

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
        shift_enter=False,
        min_lines=1,
        max_lines=5,
        filled=True,
        expand=True,
        on_submit=send_message_click,
    )
    file_picker = ft.FilePicker(on_result=load_file)
    page.overlay.append(file_picker)
    page.update()

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
                ft.IconButton(
                    icon=ft.Icons.ADD,
                    tooltip="Upload file",
                    on_click=lambda _: file_picker.pick_files(allow_multiple=True),
                ),
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
