from typing import Any, Callable

from topics import Topics


class Bind:
    def __init__(self, func: Callable[[], None], topic: Topics | None = None):
        self.func = func
        self.topic = topic

    def __call__(self):
        self.func()


class State[T]:
    def __init__(self, var: T):
        self.var = var
        self._binds: list[Bind] = []

    def set(self, new_value: T, topic: Topics | None = None):
        """Set the state value and notify all bound callbacks."""
        self.var = new_value

        for bind in self._binds:
            if bind.topic is None or bind.topic == topic:
                bind()

    def bind_callback(self, callback: Callable[[], None], topic: Topics | None = None):
        """Bind a callback function to the state change."""
        self._binds.append(Bind(callback, topic))


class StateDict:
    def __init__(self, state_dict: dict[str, State] = None):
        self._states = {} if state_dict is None else state_dict

    def register(self, key: str, state: State):
        """Register a state with a key."""
        self._states[key] = state

    def __getitem__(self, key: str) -> State:
        """Get a state by its key."""
        return self._states.get(key).var

    def bind_callback(
        self, key: str, callback: Callable[[], None], topic: Topics | None = None
    ):
        """Bind a callback to a state change."""
        state = self._states.get(key)
        if state:
            state.bind_callback(callback, topic)
        else:
            raise KeyError(f"State '{key}' not found in StateDict.")

    def set(self, key: str, value: Any, topic: Topics | None = None):
        """Set the value of a state by its key."""
        state = self._states.get(key)
        if state:
            state.set(value, topic)
        else:
            raise KeyError(f"State '{key}' not found in StateDict.")
