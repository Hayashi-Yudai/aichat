from enum import Enum, auto


class Topics(Enum):
    SUBMIT_MESSAGE = auto()
    UPDATE_CHAT = auto()
    CHANGE_AGENT = auto()
    PAST_CHAT_RESTORED = auto()
    NEW_CHAT = auto()
