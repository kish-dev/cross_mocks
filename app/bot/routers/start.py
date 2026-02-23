from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

router = Router()

WELCOME = (
    "Привет! Я бот для парных мок-собеседований.\n\n"
    "Что я делаю:\n"
    "— помогаю найти пару для мок-собеса\n"
    "— фиксирую результаты и прогресс\n"
    "— собираю статистику по прохождениям и проведениям\n\n"
    "Команды:\n"
    "/find_interviewer — хочу пройти собес\n"
    "/find_student — хочу провести собес\n"
    "/my_stats — моя история и результаты\n\n"
    "Менторство по Android:\n"
    "https://storm-paneer-5a4.notion.site/Android-2ac8b91c3fe48155b0a0f098f865e092"
)


@router.message(CommandStart())
async def start_cmd(message: Message):
    await message.answer(WELCOME)


@router.message(Command("find_interviewer"))
async def find_interviewer(message: Message):
    await message.answer("Ок, поиск интервьюера. Следующий шаг: выбери трек (пока в разработке FSM).")


@router.message(Command("find_student"))
async def find_student(message: Message):
    await message.answer("Ок, поиск ученика. Следующий шаг: выбери трек (пока в разработке FSM).")


@router.message(Command("my_stats"))
async def my_stats(message: Message):
    await message.answer("Статистика будет здесь: прохождения / проведения / сравнение со средним.")
