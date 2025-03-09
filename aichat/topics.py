from enum import Enum, auto


class Topics(Enum):
    START_SUBMISSION = auto()
    SUBMIT_MESSAGE = auto()
    UPDATE_CHAT = auto()
    CHANGE_AGENT = auto()
    PAST_CHAT_RESTORED = auto()
    NEW_CHAT = auto()
