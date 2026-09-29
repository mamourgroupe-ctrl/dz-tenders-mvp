from config import AppConfig, parse_bool


def test_parse_bool_true_values():
    assert parse_bool("true") is True
    assert parse_bool("1") is True
    assert parse_bool("yes") is True
    assert parse_bool("on") is True


def test_parse_bool_false_default():
    assert parse_bool(None, default=False) is False
    assert parse_bool("false") is False
    assert parse_bool("0") is False


def test_app_config_from_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DB_PATH", "storage/test.db")
    monkeypatch.setenv("DRY_RUN", "true")

    config = AppConfig.from_env(load_env_file=False)

    assert config.app_env == "test"
    assert config.log_level == "DEBUG"
    assert config.db_path == "storage/test.db"
    assert config.dry_run is True
