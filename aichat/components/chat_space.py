import base64
from datetime import datetime
import uuid

import flet as ft
import pdfplumber
from loguru import logger

from db import DB
from tables import MessageTableRow
from messages import Message
from roles import User, System


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
        page: ft.Page,
        database: DB,
        app_agent: System,
    ):
        super().__init__()
        self.database = database
        self.on_result = self.load_file

        self.app_agent = app_agent
        self.page = page

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
            _history_state = self.page.session.get("chat_history")
            _history_state.append(
                ChatMessage(
                    Message(
                        self.app_agent,
                        file_type,
                        content=content,
                        system_content=system_content,
                    )
                )
            )
            self.page.session.set("chat_history", _history_state)
            self.page.pubsub.send_all_on_topic("chat_history", None)
            self.update()

            MessageTableRow(
                id=str(uuid.uuid4()),
                created_at=datetime.now(),
                chat_id=self.page.session.get("chat_id"),
                role="App",
                content_type=file_type,
                content=content,
                system_content=system_content,
            ).insert_into(self.database)


class UserMessage(ft.TextField):
    def __init__(
        self,
        page: ft.Page,
        user: User,
        database: DB,
    ):
        super().__init__()
        self.hint_text = "Write a message..."
        self.autofocus = True
        self.shift_enter = False
        self.min_lines = 1
        self.max_lines = 5
        self.filled = True
        self.expand = True
        self.value = ""

        self.page = page

        self.on_submit = self.on_submit_func

        self.user = user
        self.database = database

    def on_submit_func(self, e: ft.ControlEvent):
        if self.value is not None and self.value != "":
            user_message = Message(self.user, "text", self.value, self.value)
            id = str(uuid.uuid4())
            created_at = datetime.now()

            MessageTableRow(
                id=id,
                created_at=created_at,
                chat_id=self.page.session.get("chat_id"),
                role=self.user.name,
                content_type=user_message.content_type,
                content=user_message.content,
                system_content=user_message.system_content,
            ).insert_into(self.database)

            _chat_history = self.page.session.get("chat_history")
            _chat_history.append(ChatMessage(user_message))
            self.page.session.set("chat_history", _chat_history)
            self.value = ""

            self.page.pubsub.send_all_on_topic("chat_history", None)

            self.focus()

            # FIXME: ここでエージェントごとの分岐を処理するのは微妙
            agent = self.page.session.get("agent")
            if agent.org == "openai":  # type: ignore
                agent_input = [c.message.to_openai_message() for c in _chat_history]
            elif agent.org == "deepseek":  # type: ignore
                agent_input = [c.message.to_deepseek_message() for c in _chat_history]
            elif agent.org == "google":  # type: ignore
                # FIXME: 後で直す
                agent_input = [c.message.to_openai_message() for c in _chat_history]
            else:
                logger.warning("Unknown agent")
                agent_input = []

            agent_message = agent.get_response(agent_input)
            if agent_message is not None:
                _chat_history = self.page.session.get("chat_history")
                _chat_history.append(
                    ChatMessage(
                        Message(
                            role=agent,  # type: ignore
                            content_type="text",
                            content=agent_message,
                            system_content=agent_message,
                        )
                    )
                )
                self.page.session.set("chat_history", _chat_history)
                self.page.pubsub.send_all_on_topic("chat_history", None)
                MessageTableRow(
                    id=str(uuid.uuid4()),
                    created_at=datetime.now(),
                    chat_id=self.page.session.get("chat_id"),
                    role="Agent",
                    content_type="text",
                    content=agent_message,
                    system_content=agent_message,
                ).insert_into(self.database)


class ChatHisiory(ft.ListView):
    def __init__(self, page: ft.Page, user: User, database: DB):
        super().__init__()
        self.expand = True
        self.spacing = 10

        self.user = user
        self.database = database
        self.page = page

        self.page.pubsub.subscribe_topic("chat_history", self.update_view)
        self.page.pubsub.subscribe_topic("chat_id", self.update_view_by_chat_id)

    def update_view(self, topic, message):
        logger.info("New message recieved. Updating ChatHisotry view.")
        self.controls = self.page.session.get("chat_history")
        self.update()

    def update_view_by_chat_id(self, topic, chat_id):
        role_map = {
            self.user.name: self.user,
            "App": self.user,
            "Agent": self.page.session.get("agent"),
        }
        _chat_messages = self.database.get_chat_messages_by_chat_id(chat_id)
        _chat_messages = [
            ChatMessage(Message.from_tuple(m, role_map)) for m in _chat_messages
        ]

        self.page.session.set("chat_history", _chat_messages)
        self.controls = self.page.session.get("chat_history")
        self.update()


class MainView(ft.Column):
    def __init__(
        self,
        page: ft.Page,
        human: User,
        database: DB,
        file_picker: FileLoader,
    ):
        super().__init__()

        self.expand = True

        self.user_message = UserMessage(page, human, database)
        self.chat_history = ChatHisiory(page, human, database)
        self.controls = [
            ft.Container(
                content=self.chat_history,
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

    def update_view(self):
        self.chat_history.update_view()
