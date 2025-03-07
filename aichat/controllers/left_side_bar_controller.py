# from loguru import logger

from database.db import DB
from models.chat import Chat


class PastChatListController:
    def __init__(self, db: DB):
        self.db = db

    def collect_all_chat(self):
        chats = Chat.get_all()
        chats.sort(key=lambda x: x.created_at, reverse=True)

        return chats
