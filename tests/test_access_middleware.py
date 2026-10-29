import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import GetChatMember
from aiogram.types import CallbackQuery, ChatMemberMember, User

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.bot.middlewares.access import AccessMiddleware
from app.config import settings


pytestmark = pytest.mark.asyncio
USER = User(id=12345, is_bot=False, first_name="Student")


@pytest.fixture(autouse=True)
def configure_access(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_TG_IDS", "99999")
    monkeypatch.setattr(settings, "PRIVATE_GROUP_ID", -1000000000001)


async def allowed_handler(event, data):
    return "allowed"


def message():
    return SimpleNamespace(from_user=USER, answer=AsyncMock())


@pytest.mark.parametrize("status", ["member", "administrator", "creator"])
async def test_current_members_reach_handler(status):
    event = message()
    bot = SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status=status)))

    result = await AccessMiddleware()(allowed_handler, event, {"bot": bot})

    assert result == "allowed"
    event.answer.assert_not_awaited()
    bot.get_chat_member.assert_awaited_once_with(settings.PRIVATE_GROUP_ID, USER.id)


@pytest.mark.parametrize("error_type", [TelegramBadRequest, TelegramNetworkError])
async def test_failed_check_is_not_reported_as_nonmembership(error_type, caplog):
    event = message()
    error = error_type(
        method=GetChatMember(chat_id=settings.PRIVATE_GROUP_ID, user_id=USER.id),
        message="Temporary check failure",
    )
    # Reproduces the screenshot: first check fails, a second would return member.
    bot = SimpleNamespace(get_chat_member=AsyncMock(side_effect=[error, ChatMemberMember(user=USER, status="member")]))

    result = await AccessMiddleware()(allowed_handler, event, {"bot": bot})

    assert result is None
    reply = event.answer.await_args.args[0]
    assert "Не удалось проверить" in reply
    assert "Доступ только" not in reply
    assert "notion.site" not in reply
    assert "debug:" not in reply
    assert str(USER.id) not in reply
    bot.get_chat_member.assert_awaited_once()
    assert error_type.__name__ in caplog.text


@pytest.mark.parametrize("status", ["left", "kicked"])
async def test_nonmembers_are_denied_using_one_check(status):
    event = message()
    bot = SimpleNamespace(get_chat_member=AsyncMock(return_value=SimpleNamespace(status=status)))

    result = await AccessMiddleware()(allowed_handler, event, {"bot": bot})

    assert result is None
    reply = event.answer.await_args.args[0]
    assert "Доступ только" in reply
    assert "notion.site" in reply
    assert "debug:" not in reply
    bot.get_chat_member.assert_awaited_once()


@pytest.mark.parametrize("status", ["left", "error:TelegramNetworkError"])
async def test_denied_callback_has_valid_short_alert(status, monkeypatch):
    answer = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    event = CallbackQuery(id="callback", from_user=USER, chat_instance="chat", data="action")
    if status.startswith("error:"):
        response = TelegramNetworkError(
            method=GetChatMember(chat_id=settings.PRIVATE_GROUP_ID, user_id=USER.id),
            message="Temporary check failure",
        )
        get_member = AsyncMock(side_effect=response)
    else:
        get_member = AsyncMock(return_value=SimpleNamespace(status=status))

    result = await AccessMiddleware()(allowed_handler, event, {"bot": SimpleNamespace(get_chat_member=get_member)})

    assert result is None
    assert len(answer.await_args.args[0]) <= 200
    assert answer.await_args.kwargs["show_alert"] is True
    get_member.assert_awaited_once()


async def test_admin_bypass_does_not_depend_on_telegram():
    event = message()
    event.from_user = SimpleNamespace(id=99999)
    bot = SimpleNamespace(get_chat_member=AsyncMock(side_effect=AssertionError("Unexpected API call")))

    assert await AccessMiddleware()(allowed_handler, event, {"bot": bot}) == "allowed"


async def test_event_without_user_reaches_handler():
    assert await AccessMiddleware()(allowed_handler, SimpleNamespace(), {}) == "allowed"
