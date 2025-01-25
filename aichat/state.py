from collections.abc import Callable
from typing import Any, Protocol


class State(Protocol):
    def get(self) -> Any: ...

    def set_value(self, value: Any): ...

    def bind(self, callback: Callable): ...


class PrimitiveState:
    def __init__(self, value: Any):
        self._value = value
        self._binds = []

    def set_value(self, value: Any):
        self._value = value
        for b in self._binds:
            b()

    def get(self) -> Any:
        return self._value

    def bind(self, callback: Callable):
        self._binds.append(callback)


class ListState:
    def __init__(self, value: list):
        self._value = value
        self._binds = []

    def get(self) -> list:
        return self._value

    def set_value(self, value: list):
        self._value = value
        for b in self._binds:
            b()

    def bind(self, callback: Callable):
        self._binds.append(callback)

    def append(self, value: Any):
        self._value.append(value)
        for b in self._binds:
            b()

    def pop(self):
        self._value.pop()
        for b in self._binds:
            b()

    def clear(self):
        self._value.clear()
        for b in self._binds:
            b()
