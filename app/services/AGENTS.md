# AGENTS.md — app/services/

## Назначение
Доменная/инфраструктурная логика: scheduling, matching, notifications, delivery queue, sheets sink.

## Правила
1. Функции должны быть детерминированными и хорошо покрываться unit-тестами.
2. Любые внешние интеграции иметь safe fallback (не блокировать основной flow).
3. Время/таймзона — через общие утилиты (`app/utils/time.py`).
