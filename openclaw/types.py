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
    UNKNOWN = "unknown"
