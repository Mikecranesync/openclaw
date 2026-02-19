"""Shared enums and type aliases."""

from enum import Enum


class Channel(str, Enum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    HTTP_API = "http_api"
    WEBSOCKET = "websocket"


class Intent(str, Enum):
    DIAGNOSE = "diagnose"
    STATUS = "status"
    PHOTO = "photo"
    WORK_ORDER = "work_order"
    CHAT = "chat"
    ADMIN = "admin"
    HELP = "help"
    SEARCH = "search"
    SHELL = "shell"
    DIAGRAM = "diagram"
    GIST = "gist"
    PROJECT = "project"
    WIRING_RECONSTRUCT = "wiring_reconstruct"
    KB_ENRICH = "kb_enrich"
    UNKNOWN = "unknown"
