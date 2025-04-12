from enum import Enum, auto


class Topics(Enum):
    START_SUBMISSION = auto()
    UPDATE_CHAT = auto()
    PAST_CHAT_RESTORED = auto()
    NEW_CHAT = auto()

    REQUEST_TO_AGENT = auto()
    APPEND_MESSAGE = auto()
    UPDATE_MESSAGE_STREAMLY = auto()
