from collections.abc import Callable
from typing import Any


class State:
    def __init__(self, value: Any):
        self.value = value
        self._binds: list[Callable] = []

    def get(self) -> Any:
        return self.value

    def set_value(self, value: Any):
        self.value = value
        for b in self._binds:
            b()

    def bind(self, callback: Callable):
        self._binds.append(callback)
