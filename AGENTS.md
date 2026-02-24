# AGENTS.md — Project Bootstrap (tgMocks)

## Цель проекта
Telegram-бот для парных мок-собеседований (админ, интервьюер, кандидат) на `aiogram 3 + SQLAlchemy async + Postgres + Redis`.

## Что критично не ломать
1. Сохранность данных в Postgres (P0): `users`, `candidate_sets`, `sessions`, `interview_proposals`.
2. Контекст флоу (FSM): новые сообщения не должны обрабатываться в stale-state.
3. Бизнес-цепочка: подбор -> предложение слота -> confirm/reject -> сессия -> фидбек -> статистика.

## Быстрый старт для нового чата (5 минут)
1. Прочитать: `README.md`, `app/main.py`, `docker-compose.yml`, `docker-compose.test.yml`.
2. Проверить маршрутизацию: `app/bot/routers/`.
3. Прогнать тесты в изолированном контуре:
   - `docker-compose -f docker-compose.test.yml run --rm bot_test`
4. Поднять бота локально:
   - `docker-compose up --build -d`
   - `docker-compose logs --tail 60 bot`

## Контуры окружений
- Prod-like: `docker-compose.yml` (volume `tgmocks_db_data`).
- Test isolated: `docker-compose.test.yml` (volume `tgmocks_test_db_data`, сервисы `*_test`).

## Правила изменений
1. Любые фиксы делать минимальным blast radius.
2. Перед крупными правками покрывать тестами bug-repro.
3. Не использовать destructive-команды (`down -v`, массовые `DELETE`) в прод-контуре.
4. Не менять callback_data/FSM contract без миграционного плана.

## Ключевые команды
- Тесты: `docker-compose -f docker-compose.test.yml run --rm bot_test`
- Прод-подъём: `docker-compose up --build -d`
- Логи: `docker-compose logs --tail 60 bot`
- Безопасный рестарт: `docker-compose restart bot`

## Частые инциденты и где смотреть
- Пропажа данных: `docker-compose*.yml`, volume, test cleanup, DB init.
- Залипший контекст: `app/bot/routers/proposals.py`, `sessions.py`, `evaluations.py`, reply-handlers в `start.py`.
- Недоставка сообщений: `app/bot/routers/start.py`, `app/services/delivery_queue.py`, `safe_send`.
