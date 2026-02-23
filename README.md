# tgMocks

MVP Telegram-бота для парных мок-собеседований.

## Что уже есть
- Базовый aiogram проект
- Ограничение доступа: только участники приватной группы
- Команды-заглушки для поиска пары и статистики
- Модель БД под матчинг/сессии/фидбек
- Docker Compose для постоянного запуска

## Быстрый старт
1. Создай бота через @BotFather (см. ниже) и получи `BOT_TOKEN`
2. Скопируй `.env.example` в `.env`
3. Заполни:
   - `BOT_TOKEN`
   - `PRIVATE_GROUP_ID`
   - `ADMIN_TG_IDS`
4. Запусти:
   ```bash
   docker compose up --build -d
   ```

## Как создать бота в Telegram
Это делается только вручную владельцем аккаунта:
1. Открой @BotFather
2. `/newbot`
3. Выбери имя и `username` (должен заканчиваться на `bot`)
4. Скопируй токен в `.env`

## Как узнать PRIVATE_GROUP_ID
- Добавь бота в приватную группу
- Напиши что-то в группу
- Временно запусти скрипт/лог апдейтов и возьми `chat.id` (обычно начинается с `-100...`)

## Чтобы бот отвечал всегда
Да, его нужно держать на постоянно работающем сервере:
- VPS (самый надежный и гибкий)
- Render/Railway/Fly.io (проще, но следи за лимитами)

Рекомендация: VPS + Docker Compose + `restart: unless-stopped`.

## Миграции и данные
- Используется Alembic baseline: `0001_baseline`
- При старте контейнера бот делает `alembic stamp 0001_baseline` и запускается без удаления данных.

## Backup / Restore
- Сделать бэкап:
  ```bash
  ./scripts/backup_db.sh
  ```
- Восстановить бэкап:
  ```bash
  ./scripts/restore_db.sh backups/backup_YYYYmmdd_HHMMSS.sql
  ```

## Тесты
Запуск в отдельном одноразовом контейнере:
```bash
docker-compose run --rm bot pytest -q
```

## Google Sheets
Если нет реальных credentials/sheet id, работает mock sink:
- события пишутся в `backups/sheets_outbox.jsonl`
- формат и точки вызова готовы для подключения реального Sheets API.
