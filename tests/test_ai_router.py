"""اختبارات موجّه مفاتيح مزوّدي الذكاء الاصطناعي (tools/ai_router)."""

from pathlib import Path

from tools import ai_router


def test_parse_env_file(tmp_path: Path) -> None:
    env = tmp_path / ".ai-providers.env"
    env.write_text(
        '# تعليق\nOPENAI_API_KEY="sk-test"\nEMPTY=\nBADLINE\n', encoding="utf-8"
    )
    pairs = ai_router._parse_env_file(env)
    assert pairs == {"OPENAI_API_KEY": "sk-test", "EMPTY": ""}


def test_load_does_not_override(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".ai-providers.env"
    env.write_text("MYKEY=from_file\n", encoding="utf-8")
    monkeypatch.setenv("MYKEY", "from_env")
    import os

    ai_router.load_ai_providers_env(env)
    assert os.environ["MYKEY"] == "from_env"


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    assert ai_router.load_ai_providers_env(tmp_path / "nope.env") == {}
