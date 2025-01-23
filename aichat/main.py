import base64
from dataclasses import dataclass
import os

import flet as ft
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
import pdfplumber

from state import State, ListState

USER_NAME = "Yudai"
DISABLE_AI = False
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


class UserMessage(ft.TextField):
    def __init__(
        self,
        message_state: State,
        history_state: ListState,
        user: User,
        agent: OpenAIAgent,
    ):
        super().__init__()

        self.hint_text = "Write a message..."
        self.autofocus = True
        self.shift_enter = False
        self.min_lines = 1
        self.max_lines = 5
        self.filled = True
        self.expand = True

        self.message_state = message_state
        self.history_state = history_state
        self.bind()

        self.value = message_state.get()
        self.on_submit = self.on_submit_func

        self.user = user
        self.agent = agent

    def bind(self):
        def bind_func():
            self.value = self.message_state.get()
            self.update()  # MEMO: これをここにいれるべきかは検討の余地あり

        self.message_state.bind(bind_func)

    def on_submit_func(self, e: ft.ControlEvent):
        if self.value is not None and self.value != "":
            self.message_state.set_value(self.value)
            user_message = Message(self.user, self.value)

            self.history_state.append(ChatMessage(user_message))

            self.message_state.set_value("")

            self.focus()

            agent_message = self.agent.get_response(user_message.text)
            if agent_message is not None:
                self.history_state.append(ChatMessage(agent_message))


class ChatHisiory(ft.ListView):
    def __init__(self, history_state: State, user: User):
        super().__init__()
        self.expand = True
        self.auto_scroll = True
        self.spacing = 10

        self.history_state = history_state

        self.user = user
        self.bind()

    def bind(self):
        def bind_func():
            self.controls = self.history_state.get()
            self.update()

        self.history_state.bind(bind_func)


class FileLoader(ft.FilePicker):
    def __init__(self, history_state: ListState, app_agent: User, agent: OpenAIAgent):
        super().__init__()
        self.on_result = self.load_file

        self.app_agent = app_agent
        self.agent = agent

        self.history_state = history_state

    def load_file(self, e: ft.FilePickerResultEvent):
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

            self.history_state.append(
                ChatMessage(Message(self.app_agent, f"Uploaded: {f.name}"))
            )
            self.update()
            self.agent.append_file_into_messages(content, file_type=file_type)


def main(page: ft.Page):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"
    # page.window.width = 1000
    # page.window.height = 800

    human = User(USER_NAME, ft.Colors.GREEN)
    app_agent = User("App", ft.Colors.GREY)
    agent = OpenAIAgent(MODEL_NAME)

    human_entry = State("")
    chat_history_state = ListState([])

    file_picker = FileLoader(chat_history_state, app_agent, agent)
    page.overlay.append(file_picker)

    user_message = UserMessage(
        message_state=human_entry,
        history_state=chat_history_state,
        user=human,
        agent=agent,
    )

    page.add(
        ft.Container(
            content=ChatHisiory(chat_history_state, human),
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
                user_message,
                ft.IconButton(
                    icon=ft.Icons.SEND_ROUNDED,
                    tooltip="Send message",
                    on_click=user_message.on_submit_func,
                ),
            ]
        ),
    )


if __name__ == "__main__":
    ft.app(target=main)
