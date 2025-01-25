import base64
from datetime import datetime
import uuid

import flet as ft
import pdfplumber

from db import DB
from tables import MessageTableRow
from messages import Message
from roles import User, System, Agent
from state import ListState


class ChatMessage(ft.Row):
    def __init__(self, message: Message):
        super().__init__()

        self.message = message

        self.vertical_alignment = ft.CrossAxisAlignment.START
        self.controls = [
            ft.CircleAvatar(
                content=ft.Text(self.get_initials(message.role.name)),
                color=ft.Colors.WHITE,
                bgcolor=message.role.avatar_color,
            ),
            ft.Column(
                [
                    ft.Text(message.role.name, weight=ft.FontWeight.BOLD),
                    ft.Markdown(
                        message.content,
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


class FileLoader(ft.FilePicker):
    def __init__(
        self,
        database: DB,
        history_state: ListState,
        app_agent: System,
        agent: Agent,
        chat_id: str,
    ):
        super().__init__()
        self.chat_id = chat_id
        self.database = database
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
                    system_content = f"{f.name}: "
                    for p in pdf.pages:
                        system_content += p.extract_text()
                file_type = "text"
            elif f.path.endswith(".png") or f.path.endswith(".jpg"):
                with open(f.path, "rb") as d:
                    system_content = base64.b64encode(d.read()).decode("utf-8")
                file_type = "image_url"
            else:
                with open(f.path, "r") as d:
                    system_content = d.read()
                file_type = "text"

            content = f"Uploaded: {f.name}"
            self.history_state.append(
                ChatMessage(
                    Message(
                        self.app_agent,
                        file_type,
                        content=content,
                        system_content=system_content,
                    )
                )
            )
            self.update()

            MessageTableRow(
                id=str(uuid.uuid4()),
                created_at=datetime.now(),
                chat_id=self.chat_id,
                role="App",
                content_type=file_type,
                content=content,
                system_content=system_content,
            ).insert_into(self.database)


class UserMessage(ft.TextField):
    def __init__(
        self,
        chat_id: str,
        history_state: ListState,
        user: User,
        agent: Agent,
        database: DB,
    ):
        super().__init__()
        self.chat_id = chat_id

        self.hint_text = "Write a message..."
        self.autofocus = True
        self.shift_enter = False
        self.min_lines = 1
        self.max_lines = 5
        self.filled = True
        self.expand = True
        self.value = ""

        self.history_state = history_state

        self.on_submit = self.on_submit_func

        self.user = user
        self.agent = agent
        self.database = database

    def on_submit_func(self, e: ft.ControlEvent):
        if self.value is not None and self.value != "":
            user_message = Message(self.user, "text", self.value, self.value)
            id = str(uuid.uuid4())
            created_at = datetime.now()

            MessageTableRow(
                id=id,
                created_at=created_at,
                chat_id=self.chat_id,
                role=self.user.name,
                content_type=user_message.content_type,
                content=user_message.content,
                system_content=user_message.system_content,
            ).insert_into(self.database)

            self.history_state.append(ChatMessage(user_message))
            self.value = ""

            self.focus()

            # FIXME: ここでエージェントごとの分岐を処理するのは微妙
            agent_input = [
                c.message.to_openai_message() for c in self.history_state.get()
            ]
            agent_message = self.agent.get_response(agent_input)
            if agent_message is not None:
                self.history_state.append(
                    ChatMessage(
                        Message(
                            role=self.agent,  # type: ignore
                            content_type="text",
                            content=agent_message,
                            system_content=agent_message,
                        )
                    )
                )
                MessageTableRow(
                    id=str(uuid.uuid4()),
                    created_at=datetime.now(),
                    chat_id=self.chat_id,
                    role="Agent",
                    content_type="text",
                    content=agent_message,
                    system_content=agent_message,
                ).insert_into(self.database)


class ChatHisiory(ft.ListView):
    def __init__(self, history_state: ListState, user: User):
        super().__init__()
        self.expand = True
        self.auto_scroll = True
        self.spacing = 10

        self.history_state = history_state

        self.user = user

    def bind(self):
        def bind_func():
            self.controls = self.history_state.get()
            self.update()

        self.history_state.bind(bind_func)


class MainView(ft.Column):
    def __init__(
        self,
        human: User,
        agent: Agent,
        database: DB,
        chat_history_state: ListState,
        file_picker: FileLoader,
        chat_id: str,
    ):
        super().__init__()

        self.expand = True

        self.user_message = UserMessage(
            chat_id, chat_history_state, human, agent, database
        )
        self.controls = [
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
                    self.user_message,
                    ft.IconButton(
                        icon=ft.Icons.SEND_ROUNDED,
                        tooltip="Send message",
                        on_click=self.user_message.on_submit_func,
                    ),
                ]
            ),
        ]
