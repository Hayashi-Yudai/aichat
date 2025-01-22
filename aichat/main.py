import base64
from dataclasses import dataclass
import os

import flet as ft
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
import pdfplumber

from state import State

USER_NAME = "Yudai"
DISABLE_AI = True
MODEL_NAME = "gpt-4o-mini"


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

        self.messages: list[ChatCompletionMessageParam] = []

    def get_response(self, message: str):
        if not DISABLE_AI:
            self.messages.append({"role": "user", "content": message})
            chat_completion = self.client.chat.completions.create(
                messages=self.messages,
                model=self.model_name,
            )
            content = chat_completion.choices[0].message.content
            if content is None:
                return None

            return Message(self, content)
        else:
            return Message(self, "Test")

    def append_file_into_messages(self, content: str, file_type: str = "text"):
        if file_type == "text":
            self.messages.append(
                {
                    "role": "user",
                    "content": content,
                }
            )
        elif file_type == "image_url":
            self.messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{content}"},
                        }
                    ],
                }
            )


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
                    ft.Text(message.user.user_name, weight=ft.FontWeight.BOLD),
                    ft.Markdown(
                        message.text,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        selectable=True,
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
    # page.window.width = 1000
    # page.window.height = 800

    human = User(USER_NAME, ft.Colors.GREEN)
    app_agent = User("App", ft.Colors.GREY)
    agent = OpenAIAgent(MODEL_NAME)

    def send_message_click(_):
        if human_entry.get() is not None and human_entry.get() != "":
            user_message = Message(
                human,
                human_entry.get(),
            )
            chat.controls.append(ChatMessage(user_message))
            human_entry.set_value("")
            new_message.focus()
            page.update()

            ai_message = agent.get_response(user_message.text)
            if ai_message is not None:
                chat.controls.append(ChatMessage(ai_message))
            page.update()

    def load_file(e: ft.FilePickerResultEvent):
        if e.files is None:
            return

        for f in e.files:
            file_type = None
            if f.path.endswith(".pdf"):
                with pdfplumber.open(f.path) as pdf:
                    content = ""
                    for p in pdf.pages:
                        content += p.extract_text()
                file_type = "text"
            elif f.path.endswith(".png") or f.path.endswith(".jpg"):
                with open(f.path, "rb") as d:
                    content = base64.b64encode(d.read()).decode("utf-8")
                file_type = "image_url"
            else:
                with open(f.path, "r") as d:
                    content = d.read()
                file_type = "text"

            chat.controls.append(ChatMessage(Message(app_agent, f"Uploaded: {f.name}")))
            page.update()
            agent.append_file_into_messages(content, file_type=file_type)

    page.session.set("user_name", USER_NAME)

    # Chat messages
    chat = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=True,
    )

    # A new message entry form
    human_entry = State("")

    def new_message_on_change(e: ft.ControlEvent):
        human_entry.set_value(new_message.value)

    new_message = ft.TextField(
        value=human_entry.get(),
        hint_text="Write a message...",
        autofocus=True,
        shift_enter=False,
        min_lines=1,
        max_lines=5,
        filled=True,
        expand=True,
        on_submit=send_message_click,
        on_change=new_message_on_change,
    )

    def new_message_bind():
        new_message.value = human_entry.get()

    human_entry.bind(new_message_bind)

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
