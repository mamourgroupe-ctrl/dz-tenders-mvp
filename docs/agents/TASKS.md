# TASKS: لوحة مهام الفريق
> يُحدّث هذا الملف من قبل المنسّق (Claude) والمنفّذين (Kilo / Antigravity).
> لا تغلق مهمة هنا إلا بعد التحقق من دمج PR بنجاح (علامة ✅ الخضراء في CI).

## 1. In Progress (قيد التنفيذ)
| المهمة | المنفذ | الفرع | تاريخ البدء |
|---|---|---|---|
| إعداد طبقة التنسيق (TASKS, HANDOFF, Playbooks, تحديث AGENTS) | Kilo Code | chore/agent-coordination-layer | 2026-11-05 |
| إصلاح تحذير Starlette DeprecationWarning | Kilo Code | chore/fix-starlette-deprecation | 2026-11-05 |

| فحص اكتمال زواحف BAOSEM و BOMOP واختباراتها | Kilo Code | chore/audit-baosem-bomop | 2026-11-07 |

## 2. Todo (مطلوب تنفيذها)
| المهمة | الأولوية | ملاحظات للمنفذ |
|---|---|---|
| مراجعة أمنية لملف `.vscode/mcp.json` | عالية | قبل تفعيل Playwright MCP. **مهمة منفصلة عن التنسيق.** يجب ألا يكشف الفحص أي أسرار (تنقية أي مفاتيح). |
| تجربة مراجعة Gemini (Code Assist) | متوسطة | مهمة صغيرة حقيقية لاختبار المراجع، بعد استقرار التنسيق. |
| Copilot review of PRs (second reviewer) | Medium | Enable Copilot code review in repo settings. |

## 3. Review (بانتظار مراجعة Gemini)
| المهمة | المنفذ | الفرع | ملاحظات |
|---|---|---|---|
| (فارغ) | - | - | - |

## 4. Done (مكتملة ومدموجة ومؤكدة)
| المهمة | PR | حالة CI | تاريخ الدمج |
|---|---|---|---|
| نقل storage/auth خارج مساحة العمل | #9 | (بانتظار تأكيد المستخدم لعلامة ✅) | 2026-11-05 |
| توحيد المنسق (Black/Ruff) | #8 | (بانتظار تأكيد المستخدم لعلامة ✅) | 2026-11-05 |
