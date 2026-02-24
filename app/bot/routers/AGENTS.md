# AGENTS.md — app/bot/routers/

## Карта роутеров
- `start.py`: `/start`, main menu, reply/meeting-link fallback.
- `proposals.py`: подбор интервьюера, предложение/подтверждение времени.
- `sessions.py`: запуск сессии, завершение, session-review.
- `evaluations.py`: быстрая оценка кандидатов.
- `submissions.py`: отправка наборов на модерацию.
- `admin_stats.py`, `stats.py`: статистика.
- `shared.py`: общий текст/утилиты отправки.

## Критичные инварианты
1. Любой stateful flow обязан иметь безопасный `state.clear()` на happy-path и на invalid-context.
2. Reply-based обработчики должны иметь явные маркеры (`session_id=` и т.п.).
3. Catch-all хендлеры только с guard-фильтрами, чтобы не перехватывать чужие сообщения.

## При фиксе контекста
- Проверять приоритет `StateFilter(None)` vs state-specific handlers.
- Добавлять тесты на stale-reply и смену user intent.
