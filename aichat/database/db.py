from datetime import datetime
import sqlite3
from typing import Protocol

from loguru import logger

import config
from models.model import Schema


def _adapt_datetime(dt: datetime):
    return dt.isoformat()  # 'YYYY-MM-DDTHH:MM:SS.ssssss'


# TEXT → datetime に変換するコンバーター
def _convert_datetime(text: bytes):
    return datetime.fromisoformat(text.decode())


class DB(Protocol):
    def insert(self, table_name: str, schema: list[Schema], values: list):
        pass


class SQLiteDB:
    def __init__(self, is_debug: bool = False):
        if is_debug:
            self.db_name = config.DEBUG_DB_NAME
        else:
            self.db_name = config.DB_NAME

        sqlite3.register_adapter(datetime, _adapt_datetime)
        sqlite3.register_converter("DATETIME", _convert_datetime)

    def __get_connection(self):
        return sqlite3.connect(self.db_name, detect_types=sqlite3.PARSE_DECLTYPES)

    def insert(self, table_name: str, schema: list[Schema], values: list):
        if not self._table_exist(table_name):
            logger.debug(f"{table_name} table does not exist. Create table...")
            self._create_table(table_name, schema)

        logger.debug(f"Data insert into {table_name} table")

        columns = [s.column_name for s in schema]
        sql = (
            f"INSERT INTO {table_name} ({', '.join(columns)})"
            + f" VALUES ({', '.join(['?' for _ in schema])});"
        )
        logger.debug(f"Execute SQL: {sql}")
        with self.__get_connection() as conn:
            conn.execute(sql, values)

    def entry_exist(self, table_name: str, condition: str) -> bool:
        sql = f"SELECT * FROM {table_name} WHERE {condition};"
        with self.__get_connection() as conn:
            try:
                res = conn.execute(sql)
            except sqlite3.OperationalError:
                """e.g. Table does not exist"""
                return False

            if res.fetchone():
                return True
        return False

    def get_all(self, table_name: str, condition: str | None = None) -> list[tuple]:
        sql = f"SELECT * FROM {table_name};"
        if condition:
            sql = sql[:-1] + f" WHERE {condition};"
        with self.__get_connection() as conn:
            try:
                return conn.execute(sql).fetchall()
            except sqlite3.OperationalError:
                """e.g. Table does not exist"""
                return []

    def _table_exist(self, table_name: str) -> bool:
        sql = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        with self.__get_connection() as conn:
            if conn.execute(sql, (table_name,)).fetchone():
                return True
        return False

    def _create_table(self, table_name: str, schema: list[Schema]):
        logger.info(f"Create {table_name} table...")
        schema_declaration = ", ".join(
            [
                f"{s.column_name} {s.column_type} "
                + f"{'PRIMARY KEY' if s.is_primary_key else ''} "
                + f"{'NOT NULL' if not s.is_nullable and not s.is_primary_key else ''}"
                for s in schema
            ]
        )

        sql = f"CREATE TABLE {table_name} ({schema_declaration});"
        logger.debug(f"Execute SQL: {sql}")
        with self.__get_connection() as conn:
            logger.debug(f"Execute SQL: {sql}")
            conn.execute(sql, ())
