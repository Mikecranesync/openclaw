"""Test intent classification."""

from openclaw.messages.intent import classify
from openclaw.messages.models import Attachment, InboundMessage
from openclaw.types import Channel, Intent


def _msg(text: str, attachments=None) -> InboundMessage:
    return InboundMessage(id="t1", channel=Channel.HTTP_API, user_id="u1", text=text,
                          attachments=attachments or [])


def test_diagnose_intent():
    assert classify(_msg("Why is the conveyor stopped?")) == Intent.DIAGNOSE
    assert classify(_msg("What fault is showing?")) == Intent.DIAGNOSE
    assert classify(_msg("why is it down")) == Intent.DIAGNOSE


def test_status_intent():
    assert classify(_msg("Show me current status")) == Intent.STATUS
    assert classify(_msg("What are the tag readings?")) == Intent.STATUS


def test_photo_intent():
    msg = _msg("", attachments=[Attachment(type="image", data=b"fake")])
    assert classify(msg) == Intent.PHOTO


def test_work_order_intent():
    assert classify(_msg("Create a work order for motor repair")) == Intent.WORK_ORDER


def test_admin_intent():
    assert classify(_msg("/health")) == Intent.ADMIN
    assert classify(_msg("show me budget")) == Intent.ADMIN


def test_help_intent():
    assert classify(_msg("/help")) == Intent.HELP
    assert classify(_msg("/start")) == Intent.HELP


def test_chat_fallback():
    assert classify(_msg("hello how are you")) == Intent.CHAT
