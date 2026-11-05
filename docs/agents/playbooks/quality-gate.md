# Playbook: بوابة الجودة قبل أي Commit
> لا تطلب مراجعة أو دمجاً قبل تنفيذ هذه الأوامر ونجاحها جميعاً.

1. `ruff check .` — يجب أن ينجح.
2. `python -m pytest -q` — يجب أن ينجح (بعدد الاختبارات المتوقع، حالياً 426).
3. `black --check webapp migrations tests/conftest.py tests/test_phase1_*.py` — يجب أن ينجح.
4. `mypy webapp --ignore-missing-imports` — يجب أن ينجح.
5. `git diff --check` — يجب أن يخلو من المسافات الزائدة.
6. **التحقق من الأسرار:** تأكد أنك لم تضع أي مفاتيح أو مسارات مطلقة في الملفات المتتبعة.
