from typing import Callable


class State[T]:
    def __init__(self, var: T):
        self.var = var
        self._binds = []

    @property
    def value(self) -> T:
        return self.var

    @value.setter
    def value(self, new_value: T):
        self.var = new_value

        for bind in self._binds:
            bind()

    def set(self, new_value: T):
        """Set the state value and notify all bound callbacks."""
        self.value = new_value

    def bind_callback(self, callback: Callable[[], None]):
        """Bind a callback function to the state change."""
        self._binds.append(callback)


class StateDict:
    def __init__(self, state_dict: dict[str, State] = None):
        self._states = {} if state_dict is None else state_dict

    def register(self, key: str, state: State):
        """Register a state with a key."""
        self._states[key] = state

    def __getitem__(self, key: str) -> State:
        """Get a state by its key."""
        return self._states.get(key)

    def bind_callback(self, key: str, callback: Callable[[], None]):
        """Bind a callback to a state change."""
        state = self._states.get(key)
        if state:
            state.bind_callback(callback)
        else:
            raise KeyError(f"State '{key}' not found in StateDict.")
