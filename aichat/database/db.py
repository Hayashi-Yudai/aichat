from datetime import datetime
import sqlite3
from typing import Protocol

from loguru import logger

import config
from models.model import Model


def _adapt_datetime(dt: datetime):
    return dt.isoformat()  # 'YYYY-MM-DDTHH:MM:SS.ssssss'


# TEXT → datetime に変換するコンバーター
def _convert_datetime(text: bytes):
    return datetime.fromisoformat(text.decode())


class DB(Protocol):
    def insert_from_model(self, m: Model):
        pass


class SQLiteDB:
    def __init__(self, is_debug: bool = False):
        if is_debug:
            logger.debug("Debug mode. Using debug database")
            self.db_name = config.DEBUG_DB_NAME
        else:
            logger.debug("Production mode. Using prod database")
            self.db_name = config.DB_NAME

        sqlite3.register_adapter(datetime, _adapt_datetime)
        sqlite3.register_converter("DATETIME", _convert_datetime)

    def __get_connection(self):
        return sqlite3.connect(self.db_name, detect_types=sqlite3.PARSE_DECLTYPES)

    def insert_from_model(self, m: Model):
        if not self._table_exist(m.table_name):
            logger.debug(f"{m.table_name} table does not exist. Create table...")
            # self._create_table(m)
        logger.debug(f"Data insert into {m.table_name} table")

    def _table_exist(self, table_name: str) -> bool:
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        with self.__get_connection() as conn:
            if conn.execute(sql, (table_name,)).fetchone():
                return True
        return False

    def _create_table(self, m: Model):
        logger.info(f"Create {m.table_name} table...")
        schema_declaration = ", ".join(
            [
                f"{s.column_name} {s.column_type} "
                + f"{'PRIMARY KEY' if s.is_primary_key else ''} "
                + f"{'NOT NULL' if not s.is_nullable and not s.is_primary_key else ''}"
                for s in m.schema
            ]
        )

        sql = f"CREATE TABLE ? ({schema_declaration})"
        with self.__get_connection() as conn:
            logger.debug(f"Execute SQL: {sql}")
            conn.execute(sql, (m.table_name,))
