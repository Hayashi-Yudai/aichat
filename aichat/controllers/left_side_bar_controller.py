# from loguru import logger

from models.chat import Chat


class PastChatListController:
    def collect_all_chat(self):
        chats = Chat.get_all()
        chats.sort(key=lambda x: x.created_at, reverse=True)

        return chats
