"""Application lifecycle states for the desktop controller."""

from enum import Enum


class AppState(str, Enum):
    STARTING = "STARTING"          # booting (workers start), pre-UI-request
    MODE_SELECTION = "MODE_SELECTION"  # "Boss, what do you prefer — Chat or Talk?"
    CHAT = "CHAT"                  # chat interface active
    TALK = "TALK"                  # voice interface active
    SHUTTING_DOWN = "SHUTTING_DOWN"  # graceful teardown in progress
    CLOSED = "CLOSED"              # fully terminated
