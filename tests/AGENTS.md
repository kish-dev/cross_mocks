# AGENTS.md — tests/

## Назначение
Unit/integration/smoke тесты критичных пользовательских флоу и надежности.

## Обязательные классы сценариев
1. P0: сохранность данных при рестартах/перезапуске контейнеров.
2. Контекст FSM: нет обработки новых сообщений в stale-state.
3. E2E флоу: proposal -> session -> feedback -> stats.

## Правила
1. Тесты запускаются в test-контуре (`docker-compose.test.yml`).
2. Запрещен cleanup вида `DELETE FROM <all tables>` без жесткой изоляции.
3. Для регрессии сначала писать failing test (или минимальный repro).
