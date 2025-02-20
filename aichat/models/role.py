from pydantic.dataclasses import dataclass
import flet as ft


@dataclass
class Role:
    name: str
    avatar_color: ft.Colors
