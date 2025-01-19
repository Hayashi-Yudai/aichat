import flet as ft
import asyncio  # 非同期処理用モジュール
import threading  # スレッド管理用

USER_NAME = "Yudai"


class Message:
    def __init__(self, user_name: str, text: str, message_type: str):
        self.user_name = user_name
        self.text = text
        self.message_type = message_type


class ChatMessage(ft.Row):
    def __init__(self, message: Message):
        super().__init__()
        self.vertical_alignment = ft.CrossAxisAlignment.START
        self.controls = [
            ft.CircleAvatar(
                content=ft.Text(self.get_initials(message.user_name)),
                color=ft.Colors.WHITE,
                bgcolor=self.get_avatar_color(message.user_name),
            ),
            ft.Column(
                [
                    ft.Text(message.user_name, weight="bold"),
                    ft.Text(message.text, selectable=True),
                ],
                tight=True,
                spacing=5,
            ),
        ]

    def get_initials(self, user_name: str):
        if user_name:
            return user_name[:1].capitalize()
        else:
            return "Unknown"

    def get_avatar_color(self, user_name: str):
        return ft.Colors.GREEN


def run_async_task(coroutine):
    """
    非同期タスクをバックグラウンドスレッドで実行する。
    """
    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: loop.run_until_complete(coroutine)).start()


async def add_accepted_message(page: ft.Page, chat: ft.ListView):
    """
    2秒後に 'Accepted' メッセージをタイムラインに追加する
    """
    await asyncio.sleep(2)  # 2秒待機
    accepted_message = Message("System", "Accepted", message_type="system_message")
    chat.controls.append(ChatMessage(accepted_message))
    page.update()


def main(page: ft.Page):
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.title = "Flet Chat"

    def send_message_click(e):
        if new_message.value != "":
            user_message = Message(
                page.session.get("user_name"),
                new_message.value,
                message_type="chat_message",
            )
            page.pubsub.send_all(user_message)
            new_message.value = ""
            new_message.focus()
            page.update()

            # メッセージ送信後に "Accepted" メッセージを追加
            run_async_task(add_accepted_message(page, chat))

    def on_message(message: Message):
        if message.message_type == "chat_message":
            m = ChatMessage(message)
        elif message.message_type == "system_message":
            m = ChatMessage(message)
        else:
            m = None

        chat.controls.append(m)
        page.update()

    page.pubsub.subscribe(on_message)

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
