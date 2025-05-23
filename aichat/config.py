import flet as ft


IS_DEBUG = True
USE_MISTRAL_OCR = True  # Requires Mistral API key

# Database
DB_NAME = "aichat.db"
DEBUG_DB_NAME = "aichat_dbg.db"

USER_NAME = "User"
USER_AVATAR_COLOR = ft.Colors.GREEN
AGENT_NAME = "Agent"
AGENT_AVATAR_COLOR = ft.Colors.BLUE
APP_ROLE_NAME = "App"
APP_ROLE_AVATAR_COLOR = ft.Colors.GREY

# For tool use
MAX_REQUEST_COUNT = 5
