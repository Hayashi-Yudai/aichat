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
