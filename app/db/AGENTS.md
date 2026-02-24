# AGENTS.md — app/db/

## Назначение
SQLAlchemy модели, engine/session, инициализация схемы.

## Критично
1. Никаких drop/reset логик в runtime.
2. `init_db()` используется для bootstrap test/dev схемы.
3. Для прод-изменений схемы ориентир — Alembic migration-first.

## Таблицы повышенной важности
`users`, `candidate_sets`, `sessions`, `interview_proposals`.
