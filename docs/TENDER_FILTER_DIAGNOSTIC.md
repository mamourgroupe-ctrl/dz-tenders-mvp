# تشخيص فلترة المناقصات

## النتيجة التنفيذية

تمت مراجعة `tender_filter.py` و`data/targets.json` وإضافة اختبارات تصنيف ثنائية اللغة.
بنية `targets.json` الحالية صحيحة: `products` عبارة عن mapping من فئة إلى قائمة عبارات، و`families` قائمة من كائنات.

السبب الأرجح لنتيجة `0 من 138` ليس أن ملف الأهداف غير محمّل، بل اجتماع عاملين:

1. `REQUIRE_PRODUCTS=true` يرفض عمداً كل سجل لا توجد فيه إشارة واضحة إلى PVC أو PEHD أو خزانات PE.
2. مصادر مثل Google News وSafqatic تضع غالباً `product: "غير محدد"`، وقد لا يذكر عنوان الخبر منتجاً. هذه سجلات إشارات عامة وليست إعلانات منتجات، لذلك يجب أن تُرفض في الوضع الصارم.

مع ذلك كان المصنّف هشاً أمام اختلافات schema: كان يقرأ `product` فقط ولا يقرأ `products` أو `title_fr` أو خرائط المنتجات المتداخلة. تمت معالجة ذلك دون تعديل `targets.json`.

## ما تم إصلاحه

- تطبيع Unicode للعربية والفرنسية:
  - إزالة التشكيل والتطويل.
  - توحيد الهمزات و`ى` و`ة` وفق convention المشروع.
  - توحيد حالة الحروف اللاتينية.
- مطابقة regex بحدود كلمات مع `re.IGNORECASE | re.UNICODE`.
- `_compile_patterns` يقرأ صراحةً:
  - `products: {CATEGORY: [phrases]}`.
  - `families: [{keywords, entities, ...}]`.
- `classify_tender` يقرأ العنوان العربي/الفرنسي والوصف والجهة والمنتج، بالإضافة إلى:
  - `products` كقائمة أو mapping.
  - `title_ar`, `title_fr`, `titre`, `objet`, `organization`, `product_codes` وغيرها.
- احتُفظ بالأوزان الأصلية:

```python
WEIGHT_ENTITY = 4
WEIGHT_KEYWORD = 2
WEIGHT_PRODUCT = 3
MIN_SCORE_THRESHOLD = 3
```

- أضيفت `last_filter_diagnostics` وسجل واضح لأسباب الرفض:
  - `product_required`
  - `no_product_or_family_match`
- لم يعد تشغيل يصفر النتائج دون تفسير في الـ log.

## طريقة التحقق السريع

```powershell
$env:REQUIRE_PRODUCTS = "true"
python -c @"
from tender_filter import TenderFilter
f = TenderFilter(freshness_enabled=False, require_products=True)
for tender in [
    {"title": "توريد أنابيب PEHD"},
    {"title": "Fourniture de conduites PVC"},
    {"title": "مناقصة عامة"},
]:
    result = f.classify_tender(tender)
    print(tender["title"], bool(result), f._last_classification_reason)
"@
```

النتيجة المتوقعة: أول سجلين `True` والثالث `False` بسبب `product_required`.

لتشخيص تشغيل كامل:

```python
filter_obj = TenderFilter()
filtered = filter_obj.filter_tenders(tenders)
print(filter_obj.last_filter_diagnostics)
```

مثال عند وجود أخبار عامة فقط:

```python
{
    'input': 138,
    'fresh': 138,
    'dropped': 0,
    'classified': 0,
    'rejected': {'product_required': 138},
    'require_products': True,
}
```

## أشهر خمسة أسباب لعودة `None`

1. **الحصر الصارم للمنتجات:** `REQUIRE_PRODUCTS=true` مع عدم وجود كلمة المنتج في أي حقل مقروء.
2. **اختلاف أسماء الحقول:** المنتج موجود تحت `products` أو `title_fr` أو `product_codes` وليس `product`.
3. **قراءة مفاتيح الفئات بدلاً من قيمها:** البحث عن `PEHD_PIPES` لا يعوض البحث عن `tuyau PEHD` و`أنابيب PEHD`.
4. **اختلاف Unicode والتهجئة:** التشكيل، التطويل، الهمزات، `PVC-U`، أو اختلاف حالة الحروف الفرنسية.
5. **إخفاء الاستثناءات أو خلط فلتر الحداثة بالتصنيف:** يجب فصل عدد `fresh` عن عدد `classified` وتسجيل سبب الرفض لكل مرحلة.

## قائمة فحص من عشر نقاط

1. اطبع `len(f.targets)` وتأكد أن `products` mapping و`families` list.
2. اطبع عدد عبارات كل فئة، لا أسماء المفاتيح فقط.
3. افحص العينة الخام قبل الفلترة: `title`, `product`, `products`, `description`.
4. شغّل `classify_tender` على سجل عربي معروف يحتوي `أنابيب PEHD`.
5. شغّله على سجل فرنسي يحتوي `conduites PVC`.
6. جرّب `products={"PEHD_PIPES": [...]}` وليس `product` فقط.
7. اطبع `_normalize` للنص والعبارة الهدف وقارن الناتج.
8. افصل إحصائيات `filter_fresh` عن إحصائيات `classify_tender`.
9. افحص قيمة `REQUIRE_PRODUCTS` من البيئة الفعلية، لا من `.env.example` فقط.
10. فعّل `last_filter_diagnostics` بعد كل تشغيل ولا تكتفِ بعدد النتائج النهائي.

## تحذيرات تشغيلية

- لا تجعل `REQUIRE_PRODUCTS=false` حلاً دائماً إذا كان الهدف إرسال فرص منتجات محددة؛ هذا سيعيد أخباراً عامة وضجيجاً.
- الأفضل تصنيف Google News كـ `signal` منفصل أو تشغيله بفلتر غير صارم ثم عدم إرساله في قناة المنتجات.
- لا تعدّل `targets.json` لمعالجة خطأ في قراءة schema.
- لا تستخدم `except: return None` داخل المصنّف؛ سجّل الاستثناء مع `title` و`source`.
- لا تعتمد على `date.today()` في الاختبارات؛ مرّر `today` إلى `filter_fresh` كما تفعل اختبارات الحداثة الحالية.

## الاختبارات

الاختبار الجديد موجود في `tests/test_tender_filter_classification.py` ويغطي العربية والفرنسية، products mapping، التطبيع، الوضع الصارم، وتشخيص نتيجة الصفر.
