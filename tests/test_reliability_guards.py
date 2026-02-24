from pathlib import Path

from app.bot.routers.shared import continue_message_text


def test_continue_message_text_is_short_and_actionable():
    text = continue_message_text()
    assert "Гоу дальше" in text


def test_compose_has_persistent_named_db_volume_and_restart_policies():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "name: tgmocks_db_data" in compose
    assert "db:\n    image: postgres:16\n    restart: unless-stopped" in compose
    assert "redis:\n    image: redis:7\n    restart: unless-stopped" in compose
