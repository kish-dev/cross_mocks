import time

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update


class Flow(StatesGroup):
    waiting = State()


def _raw_message_update(user_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": int(time.time()),
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "text": text,
        },
    }


@pytest.mark.asyncio
async def test_state_handler_has_priority_over_state_none_catchall():
    bot = Bot("123456:TESTTOKEN")
    dp = Dispatcher(storage=MemoryStorage())
    router = Router()
    calls: list[str] = []

    @router.message(Flow.waiting)
    async def on_waiting(_message):
        calls.append("state")

    @router.message(StateFilter(None))
    async def on_none(_message):
        calls.append("none")

    dp.include_router(router)
    ctx = dp.fsm.get_context(bot=bot, chat_id=1, user_id=1)
    await ctx.set_state(Flow.waiting)

    update = Update.model_validate(_raw_message_update(user_id=1, chat_id=1, text="hello"))
    await dp.feed_update(bot, update)

    assert calls == ["state"]
    await bot.session.close()


@pytest.mark.asyncio
async def test_state_none_catchall_handles_message_without_fsm_state():
    bot = Bot("123456:TESTTOKEN")
    dp = Dispatcher(storage=MemoryStorage())
    router = Router()
    calls: list[str] = []

    @router.message(Flow.waiting)
    async def on_waiting(_message):
        calls.append("state")

    @router.message(StateFilter(None))
    async def on_none(_message):
        calls.append("none")

    dp.include_router(router)

    update = Update.model_validate(_raw_message_update(user_id=2, chat_id=2, text="hello"))
    await dp.feed_update(bot, update)

    assert calls == ["none"]
    await bot.session.close()
