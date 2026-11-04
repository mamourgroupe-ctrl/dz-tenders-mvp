"""موجّه مفاتيح مزوّدي الذكاء الاصطناعي.

يحمّل ``~/.ai-providers.env`` تلقائياً عند الاستيراد فتبقى مفاتيح
الذكاء الاصطناعي على مستوى النظام وتعمل في كل المشاريع دون إعادة إدخال.
"""

from __future__ import annotations

import os
from pathlib import Path

AI_PROVIDERS_ENV = Path.home() / ".ai-providers.env"


def _parse_env_file(path: Path) -> dict[str, str]:
    """قراءة أزواج KEY=VALUE من ملف env دون تبعيات خارجية."""
    pairs: dict[str, str] = {}
    if not path.exists():
        return pairs
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            pairs[key] = value
    return pairs


def load_ai_providers_env(path: Path = AI_PROVIDERS_ENV) -> dict[str, str]:
    """تحميل مفاتيح المزوّدين إلى ``os.environ`` دون تجاوز القيم الموجودة.

    يستخدم ``python-dotenv`` عند توفره وإلا يعتمد المحلل الداخلي.
    """
    if not path.exists():
        return {}
    before = set(os.environ)
    try:
        from dotenv import load_dotenv

        load_dotenv(path, override=False)
        loaded = {k: os.environ[k] for k in set(os.environ) - before}
    except ImportError:
        loaded = {}
        for key, value in _parse_env_file(path).items():
            if key not in os.environ:
                os.environ[key] = value
                loaded[key] = value
    return loaded


def get_provider_key(provider: str, default: str | None = None) -> str | None:
    """إرجاع مفتاح API لمزوّد معيّن (مثال: ``OPENAI`` ← ``OPENAI_API_KEY``)."""
    return os.environ.get(f"{provider.upper()}_API_KEY", default)


load_ai_providers_env()

if __name__ == "__main__":
    found = _parse_env_file(AI_PROVIDERS_ENV)
    print(f"file={AI_PROVIDERS_ENV} exists={AI_PROVIDERS_ENV.exists()} keys={sorted(found)}")
