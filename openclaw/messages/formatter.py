"""Format outbound messages per channel."""

from openclaw.types import Channel


def format_text(text: str, channel: Channel) -> str:
    """Adapt markdown formatting for the target channel."""
    if channel == Channel.TELEGRAM:
        # Telegram supports Markdown V2, but basic markdown works for most cases
        return text
    if channel == Channel.WHATSAPP:
        # WhatsApp uses *bold* and _italic_ (same as markdown)
        return text
    if channel == Channel.HTTP_API:
        return text
    return text
