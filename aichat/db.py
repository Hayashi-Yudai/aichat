from datetime import datetime
import sqlite3

from loguru import logger


class DB:
    def __init__(self, db_name: str):
        self.db_name = db_name

        sqlite3.register_adapter(datetime, self.adapt_datetime)
        sqlite3.register_converter("DATETIME", self.convert_datetime)

        self.tables = ["message", "chat"]
        self._setup()

    def _setup(self):
        with sqlite3.connect(
            self.db_name, detect_types=sqlite3.PARSE_DECLTYPES
        ) as conn:
            for table in self.tables:
                with open(f"sqls/{table}.sql") as f:
                    conn.execute(f.read())

            logger.info("Database setup completed")

    # datetime → TEXT に変換するアダプター
    @staticmethod
    def adapt_datetime(dt: datetime):
        return dt.isoformat()  # 'YYYY-MM-DDTHH:MM:SS.ssssss'

    # TEXT → datetime に変換するコンバーター
    @staticmethod
    def convert_datetime(text: bytes):
        return datetime.fromisoformat(text.decode())

    def get_connect(self):
        return sqlite3.connect(self.db_name, detect_types=sqlite3.PARSE_DECLTYPES)

    def get_past_chat_list(self):
        with self.get_connect() as conn:
            cursor = conn.execute(
                """
                WITH
                chat_with_message AS (
                    SELECT
                        chat.id,
                        message.content,
                        RANK() OVER (PARTITION BY chat.id ORDER BY message.created_at) AS sequence,
                        chat.created_at
                    FROM chat
                    INNER JOIN message
                        ON chat.id = message.chat_id
                )

                SELECT
                    *
                FROM chat_with_message
                WHERE
                    sequence = 1
                ORDER BY
                    created_at DESC
                ;
            """
            )
            return cursor.fetchall()

    def get_chat_messages_by_chat_id(self, chat_id: str):
        with self.get_connect() as conn:
            cursor = conn.execute(
                """
                SELECT
                    role,
                    content_type,
                    content,
                    system_content
                FROM message
                WHERE
                    chat_id = ?
                ORDER BY
                    created_at
                ;
            """,
                (chat_id,),
            )
            return cursor.fetchall()
