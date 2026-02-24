from pathlib import Path


def test_test_compose_is_explicitly_marked_and_isolated():
    compose = Path("docker-compose.test.yml").read_text(encoding="utf-8")
    assert "db_test:" in compose
    assert "redis_test:" in compose
    assert "bot_test:" in compose
    assert "name: tgmocks_test_db_data" in compose


def test_test_env_uses_test_database_host():
    env = Path(".env.test").read_text(encoding="utf-8")
    assert "@db_test:5432/tgmocks_test" in env
    assert "REDIS_URL=redis://redis_test:6379/0" in env
