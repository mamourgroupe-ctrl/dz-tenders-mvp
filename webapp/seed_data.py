"""Reference and demonstration data for the platform.

Facts policy:

* The 69 wilayas below are the official Algerian wilayas. Codes 01–58 date from
  the November 2019 reform; codes 59–69 were created by Law 26-06 (Journal
  Officiel no. 25, 5 April 2026) and named by Presidential Decree 26-206
  (Journal Officiel no. 40, 3 June 2026). During the transition the mother
  wilayas keep administering them until 31 December 2026. A client-supplied
  list can still replace the defaults through ``APP_WILAYAS_FILE``.
* Issuers are real public institutions, used only as sample references.
* Every demonstration announcement is flagged ``is_sample=True`` and renders a
  visible "نموذج" badge; source URLs use the reserved ``example.dz`` domain.
* Plan prices are explicit placeholders pending client confirmation.
"""

from __future__ import annotations

from typing import Any

#: (code, slug, name_ar, name_fr) — official 69 wilayas (2026).
WILAYAS: list[tuple[str, str, str, str]] = [
    ("01", "adrar", "أدرار", "Adrar"),
    ("02", "chlef", "الشلف", "Chlef"),
    ("03", "laghouat", "الأغواط", "Laghouat"),
    ("04", "oum-el-bouaghi", "أم البواقي", "Oum El Bouaghi"),
    ("05", "batna", "باتنة", "Batna"),
    ("06", "bejaia", "بجاية", "Béjaïa"),
    ("07", "biskra", "بسكرة", "Biskra"),
    ("08", "bechar", "بشار", "Béchar"),
    ("09", "blida", "البليدة", "Blida"),
    ("10", "bouira", "البويرة", "Bouira"),
    ("11", "tamanrasset", "تمنراست", "Tamanrasset"),
    ("12", "tebessa", "تبسة", "Tébessa"),
    ("13", "tlemcen", "تلمسان", "Tlemcen"),
    ("14", "tiaret", "تيارت", "Tiaret"),
    ("15", "tizi-ouzou", "تيزي وزو", "Tizi Ouzou"),
    ("16", "alger", "الجزائر", "Alger"),
    ("17", "djelfa", "الجلفة", "Djelfa"),
    ("18", "jijel", "جيجل", "Jijel"),
    ("19", "setif", "سطيف", "Sétif"),
    ("20", "saida", "سعيدة", "Saïda"),
    ("21", "skikda", "سكيكدة", "Skikda"),
    ("22", "sidi-bel-abbes", "سيدي بلعباس", "Sidi Bel Abbès"),
    ("23", "annaba", "عنابة", "Annaba"),
    ("24", "guelma", "قالمة", "Guelma"),
    ("25", "constantine", "قسنطينة", "Constantine"),
    ("26", "medea", "المدية", "Médéa"),
    ("27", "mostaganem", "مستغانم", "Mostaganem"),
    ("28", "msila", "المسيلة", "M'Sila"),
    ("29", "mascara", "معسكر", "Mascara"),
    ("30", "ouargla", "ورقلة", "Ouargla"),
    ("31", "oran", "وهران", "Oran"),
    ("32", "el-bayadh", "البيض", "El Bayadh"),
    ("33", "illizi", "إليزي", "Illizi"),
    ("34", "bordj-bou-arreridj", "برج بوعريريج", "Bordj Bou Arréridj"),
    ("35", "boumerdes", "بومرداس", "Boumerdès"),
    ("36", "el-tarf", "الطارف", "El Tarf"),
    ("37", "tindouf", "تندوف", "Tindouf"),
    ("38", "tissemsilt", "تيسمسيلت", "Tissemsilt"),
    ("39", "el-oued", "الوادي", "El Oued"),
    ("40", "khenchela", "خنشلة", "Khenchela"),
    ("41", "souk-ahras", "سوق أهراس", "Souk Ahras"),
    ("42", "tipaza", "تيبازة", "Tipaza"),
    ("43", "mila", "ميلة", "Mila"),
    ("44", "ain-defla", "عين الدفلى", "Aïn Defla"),
    ("45", "naama", "النعامة", "Naâma"),
    ("46", "ain-temouchent", "عين تموشنت", "Aïn Témouchent"),
    ("47", "ghardaia", "غرداية", "Ghardaïa"),
    ("48", "relizane", "غليزان", "Relizane"),
    ("49", "timimoun", "تيميمون", "Timimoun"),
    ("50", "bordj-badji-mokhtar", "برج باجي مختار", "Bordj Badji Mokhtar"),
    ("51", "ouled-djellal", "أولاد جلال", "Ouled Djellal"),
    ("52", "beni-abbes", "بني عباس", "Béni Abbès"),
    ("53", "in-salah", "عين صالح", "In Salah"),
    ("54", "in-guezzam", "عين قزام", "In Guezzam"),
    ("55", "touggourt", "تقرت", "Touggourt"),
    ("56", "djanet", "جانت", "Djanet"),
    ("57", "el-mghair", "المغير", "El M'Ghair"),
    ("58", "el-meniaa", "المنيعة", "El Meniaa"),
    # Wilayas created by Law 26-06 (2026); mother wilaya in parentheses.
    ("59", "aflou", "أفلو", "Aflou"),  # Laghouat (03)
    ("60", "barika", "بريكة", "Barika"),  # Batna (05)
    ("61", "el-kantara", "القنطرة", "El Kantara"),  # Biskra (07)
    ("62", "bir-el-ater", "بئر العاتر", "Bir El Ater"),  # Tébessa (12)
    ("63", "el-aricha", "العريشة", "El Aricha"),  # Tlemcen (13)
    ("64", "ksar-chellala", "قصر الشلالة", "Ksar Chellala"),  # Tiaret (14)
    ("65", "ain-ouessara", "عين وسارة", "Aïn Ouessara"),  # Djelfa (17)
    ("66", "messaad", "مسعد", "Messaad"),  # Djelfa (17)
    ("67", "ksar-el-boukhari", "قصر البخاري", "Ksar El Boukhari"),  # Médéa (26)
    ("68", "bou-saada", "بوسعادة", "Bou Saâda"),  # M'Sila (28)
    ("69", "el-abiodh-sidi-cheikh", "الأبيض سيدي الشيخ", "El Abiodh Sidi Cheikh"),
]

#: (slug, name_ar, name_fr, sort_order) — proposed taxonomy, client-editable.
SECTORS: list[tuple[str, str, str, int]] = [
    ("water", "المياه والصرف", "Eau et assainissement", 10),
    ("construction", "الأشغال العمومية والبناء", "Travaux publics et bâtiment", 20),
    ("housing", "السكن والعمران", "Habitat et urbanisme", 30),
    ("energy", "الطاقة والكهرباء", "Énergie et électricité", 40),
    ("hydrocarbons", "المحروقات", "Hydrocarbures", 50),
    ("it_telecom", "الإعلام الآلي والاتصالات", "Informatique et télécoms", 60),
    ("transport", "النقل واللوجستيك", "Transport et logistique", 70),
    ("health", "الصحة", "Santé", 80),
    ("education", "التربية والتعليم", "Éducation et enseignement", 90),
    ("agriculture", "الفلاحة", "Agriculture", 100),
    ("environment", "البيئة والنفايات", "Environnement et déchets", 110),
    ("industry", "الصناعة", "Industrie", 120),
    ("mining", "المناجم", "Mines", 130),
    ("security", "الأمن والحماية", "Sécurité et protection", 140),
    ("services", "الخدمات", "Services", 150),
    ("finance", "المالية والتأمين", "Finance et assurance", 160),
]

#: (slug, name_ar, name_fr, kind, wilaya_code) — real institutions, samples.
ISSUERS: list[tuple[str, str, str, str, str | None]] = [
    ("ade", "الجزائرية للمياه", "Algérie des Eaux", "مؤسسة عمومية", None),
    (
        "ona",
        "الديوان الوطني للتطهير",
        "Office National de l'Assainissement",
        "مؤسسة عمومية",
        None,
    ),
    ("sonatrach", "سوناطراك", "Sonatrach", "مؤسسة عمومية", None),
    ("sonelgaz", "سونلغاز", "Sonelgaz", "مؤسسة عمومية", None),
    ("algerie-telecom", "اتصالات الجزائر", "Algérie Télécom", "مؤسسة عمومية", None),
    ("algerie-poste", "بريد الجزائر", "Algérie Poste", "مؤسسة عمومية", None),
    ("anep", "الوكالة الوطنية للنشر والإشهار", "ANEP", "مؤسسة عمومية", None),
    (
        "ministere-sante",
        "وزارة الصحة",
        "Ministère de la Santé",
        "إدارة مركزية",
        None,
    ),
    (
        "ministere-education",
        "وزارة التربية الوطنية",
        "Ministère de l'Éducation Nationale",
        "إدارة مركزية",
        None,
    ),
    (
        "ministere-transports",
        "وزارة النقل",
        "Ministère des Transports",
        "إدارة مركزية",
        None,
    ),
    (
        "ministere-agriculture",
        "وزارة الفلاحة والتنمية الريفية",
        "Ministère de l'Agriculture",
        "إدارة مركزية",
        None,
    ),
    ("cnas", "الصندوق الوطني للتأمينات الاجتماعية", "CNAS", "مؤسسة عمومية", None),
    (
        "adm",
        "الجزائرية للطرق السيارة",
        "Autoroute des Hauts Plateaux (ADM)",
        "مؤسسة عمومية",
        None,
    ),
    (
        "opgi",
        "الديوان العمومي للتسيير العقاري",
        "OPGI",
        "مؤسسة عمومية",
        None,
    ),
    (
        "wilaya-constantine",
        "ولاية قسنطينة",
        "Wilaya de Constantine",
        "جماعة محلية",
        "25",
    ),
    ("wilaya-setif", "ولاية سطيف", "Wilaya de Sétif", "جماعة محلية", "19"),
    (
        "dtp-constantine",
        "مديرية الأشغال العمومية – قسنطينة",
        "Direction des Travaux Publics – Constantine",
        "إدارة محلية",
        "25",
    ),
    (
        "dtp-setif",
        "مديرية الأشغال العمومية – سطيف",
        "Direction des Travaux Publics – Sétif",
        "إدارة محلية",
        "19",
    ),
    (
        "universite-constantine-1",
        "جامعة الإخوة منتوري قسنطينة 1",
        "Université Frères Mentouri Constantine 1",
        "مؤسسة جامعية",
        "25",
    ),
    (
        "apc-alger-centre",
        "بلدية الجزائر الوسطى",
        "APC Alger-Centre",
        "جماعة محلية",
        "16",
    ),
]

#: (code, name_ar, name_fr, kind, sector_limit, auctions_only, monthly, annual, sort)
#: Prices are PLACEHOLDERS in DZD — see open question O2 in docs/AUDIT.md.
PLANS: list[tuple[str, str, str, str, int | None, bool, int, int, int]] = [
    ("free", "مجاني", "Gratuit", "subscription", 0, False, 0, 0, 10),
    ("bronze", "برونزي", "Bronze", "subscription", 1, False, 2000, 20000, 20),
    ("silver", "فضي", "Argent", "subscription", 4, False, 5500, 55000, 30),
    ("gold", "ذهبي", "Or", "subscription", 6, False, 8000, 80000, 40),
    ("premium", "بريميوم", "Premium", "subscription", 10, False, 12000, 120000, 50),
    ("platinum", "بلاتيني", "Platine", "subscription", None, False, 18000, 180000, 60),
    (
        "auctions_only",
        "المزادات فقط",
        "Enchères uniquement",
        "subscription",
        None,
        True,
        1500,
        15000,
        70,
    ),
    (
        "extra_sector",
        "قطاع إضافي",
        "Secteur additionnel",
        "addon",
        1,
        False,
        800,
        8000,
        80,
    ),
]

#: Demonstration announcements. ``publish_days_ago``/``deadline_in_days`` are
#: relative to the seed date so the demo never looks frozen in the past.
SAMPLES: list[dict[str, Any]] = [
    {
        "type": "tender",
        "title_ar": "اقتناء أنابيب PVC لشبكة توزيع مياه الشرب",
        "title_fr": "Acquisition de conduites PVC pour le réseau d'eau potable",
        "description_ar": (
            "مناقصة توضيحية لاقتناء أنابيب PVC بأقطار مختلفة ولواحقها، "
            "مع النقل والتسليم على مستوى مستودعات الولاية. "
            "هذا الإعلان نموذج تقني لعرض الميزات ولا يمثل إعلاناً رسمياً."
        ),
        "sectors": ["water"],
        "wilaya": "25",
        "issuer": "ade",
        "publish_days_ago": 2,
        "deadline_in_days": 21,
        "value": 18_500_000,
    },
    {
        "type": "tender",
        "title_ar": "إنجاز خزان مياه بسعة 5000 متر مكعب ببلدية الخروب",
        "title_fr": "Réalisation d'un réservoir d'eau de 5000 m³ à El Khroub",
        "description_ar": (
            "أشغال إنجاز خزان مياه مدفون بسعة 5000 متر مكعب مع الأشغال الملحقة "
            "والربط بالشبكة. العرض نموذج لتوضيح صفحة المناقصة."
        ),
        "sectors": ["water", "construction"],
        "wilaya": "25",
        "issuer": "ona",
        "publish_days_ago": 3,
        "deadline_in_days": 30,
        "value": 92_000_000,
    },
    {
        "type": "tender",
        "title_ar": "تهيئة الطرق الحضرية عبر بلديات ولاية سطيف",
        "title_fr": "Aménagement de voiries urbaines dans la wilaya de Sétif",
        "description_ar": (
            "أشغال تهيئة الطرق والأرصفة والإنارة العمومية على عدة محاور. "
            "نموذج توضيحي لعرض المناقصات متعددة القطاعات."
        ),
        "sectors": ["construction", "transport"],
        "wilaya": "19",
        "issuer": "dtp-setif",
        "publish_days_ago": 1,
        "deadline_in_days": 45,
        "value": 140_000_000,
    },
    {
        "type": "consultation",
        "title_ar": "استشارة لاقتناء معدات مخبرية",
        "title_fr": "Consultation pour l'acquisition d'équipements de laboratoire",
        "description_ar": (
            "استشارة توضيحية لتوريد معدات مخبرية وتحاليل طبية، "
            "تشمل التركيب والتكوين والضمان."
        ),
        "sectors": ["health"],
        "wilaya": "16",
        "issuer": "ministere-sante",
        "publish_days_ago": 2,
        "deadline_in_days": 15,
        "value": 7_400_000,
    },
    {
        "type": "consultation",
        "title_ar": "استشارة خاصة بخدمات الصيانة المعلوماتية",
        "title_fr": "Consultation pour la maintenance informatique",
        "description_ar": (
            "خدمات صيانة دورية للخوادم ومحطات العمل وشبكة الاتصالات الداخلية "
            "لمدة اثني عشر شهراً. إعلان نموذجي."
        ),
        "sectors": ["it_telecom"],
        "wilaya": "31",
        "issuer": "algerie-telecom",
        "publish_days_ago": 4,
        "deadline_in_days": 10,
        "value": 3_200_000,
    },
    {
        "type": "auction",
        "title_ar": "مزاد علني لبيع أغراض ومعدات متوقفة",
        "title_fr": "Vente aux enchères de matériels hors service",
        "description_ar": (
            "مزاد علني توضيحي لبيع معدات وأثاث متوقف عن الاستعمال، "
            "المعاينة متاحة قبل تاريخ الجلسة."
        ),
        "sectors": ["services"],
        "wilaya": "25",
        "issuer": "algerie-poste",
        "publish_days_ago": 400,
        "deadline_in_days": 7,
        "value": 450_000,
    },
    {
        "type": "auction",
        "title_ar": "بيع بالمزاد لكمية من أنابيب PEHD غير المستعملة",
        "title_fr": "Vente aux enchères de conduites PEHD non utilisées",
        "description_ar": (
            "بيع كمية من أنابيب PEHD بمختلف الأقطار في حالة جيدة، "
            "تسليم في عين المكان. بيانات المزاد نموذجية."
        ),
        "sectors": ["water"],
        "wilaya": "30",
        "issuer": "ade",
        "publish_days_ago": 2,
        "deadline_in_days": 5,
        "value": 2_100_000,
    },
    {
        "type": "provisional_award",
        "title_ar": "إسناد مؤقت لإنجاز محطة معالجة المياه",
        "title_fr": "Attribution provisoire d'une station de traitement des eaux",
        "description_ar": (
            "إعلان توضيحي عن الإسناد المؤقت لمشروع محطة معالجة المياه "
            "لفائدة المؤسسة الفائزة، مع أجل الطعن القانوني."
        ),
        "sectors": ["water", "environment"],
        "wilaya": "47",
        "issuer": "ona",
        "publish_days_ago": 3,
        "deadline_in_days": None,
        "value": 210_000_000,
    },
    {
        "type": "provisional_award",
        "title_ar": "الإسناد المؤقت لتوريد أجهزة إعلام آلي",
        "title_fr": "Attribution provisoire pour la fourniture de matériel informatique",
        "description_ar": (
            "نتيجة مؤقتة توضيحية لتوريد حواسيب وطابعات لمؤسسات تربوية، "
            "مرفقة بجدول الأسعار."
        ),
        "sectors": ["it_telecom", "education"],
        "wilaya": "16",
        "issuer": "ministere-education",
        "publish_days_ago": 5,
        "deadline_in_days": None,
        "value": 65_000_000,
    },
    {
        "type": "cancellation",
        "title_ar": "إلغاء مناقصة توريد خزانات المياه",
        "title_fr": "Annulation de l'appel d'offres pour réservoirs d'eau",
        "description_ar": (
            "إعلان توضيحي عن إلغاء المناقصة بسبب مراجعة دفتر الشروط، "
            "على أن تُنشر مناقصة جديدة لاحقاً."
        ),
        "sectors": ["water"],
        "wilaya": "05",
        "issuer": "ade",
        "publish_days_ago": 2,
        "deadline_in_days": None,
        "value": None,
    },
    {
        "type": "cancellation",
        "title_ar": "إلغاء استشارة تتعلق بدراسة تقنية",
        "title_fr": "Annulation d'une consultation pour étude technique",
        "description_ar": (
            "إلغاء استشارة نموذجية لعدم اكتمال الشروط التقنية، " "مع شكر المشاركين."
        ),
        "sectors": ["energy"],
        "wilaya": "09",
        "issuer": "sonelgaz",
        "publish_days_ago": 6,
        "deadline_in_days": None,
        "value": None,
    },
    {
        "type": "deadline_extension",
        "title_ar": "تمديد أجل تقديم العروض لمناقصة أشغال التهيئة",
        "title_fr": "Prorogation du délai de soumission – travaux d'aménagement",
        "description_ar": (
            "نموذج إعلان تمديد أجل تقديم العروض لمدة أسبوعين إضافيين، "
            "مع بقاء بقية الشروط دون تغيير."
        ),
        "sectors": ["construction"],
        "wilaya": "22",
        "issuer": "dtp-setif",
        "publish_days_ago": 1,
        "deadline_in_days": 14,
        "value": None,
    },
    {
        "type": "deadline_extension",
        "title_ar": "تمديد أجل مناقصة اقتناء معدات كهربائية",
        "title_fr": "Prorogation de délai – acquisition d'équipements électriques",
        "description_ar": (
            "تمديد أجلي نموذجي لتقديم العروض بسبب طلب توضيحات إضافية من المتنافسين."
        ),
        "sectors": ["energy"],
        "wilaya": "25",
        "issuer": "sonelgaz",
        "publish_days_ago": 3,
        "deadline_in_days": 21,
        "value": None,
    },
    {
        "type": "notice_of_default",
        "title_ar": "إعذار متعاقد بسبب تأخر التسليم",
        "title_fr": "Mise en demeure pour retard de livraison",
        "description_ar": (
            "إعلان إعذار نموذجي لمؤسسة متعاقدة لم تحترم آجال التسليم، "
            "مع منحها مهلة تصحيحية."
        ),
        "sectors": ["construction"],
        "wilaya": "06",
        "issuer": "opgi",
        "publish_days_ago": 4,
        "deadline_in_days": None,
        "value": None,
    },
    {
        "type": "notice_of_default",
        "title_ar": "إعذار مؤسسة مقاولات لعدم احترام آجال الإنجاز",
        "title_fr": "Mise en demeure pour non-respect des délais d'exécution",
        "description_ar": (
            "إعذار توضيحي ثانٍ لمقاولة بسبب توقف الأشغال دون مبرر، "
            "مع إمكانية تطبيق الغرامات التعاقدية."
        ),
        "sectors": ["housing"],
        "wilaya": "18",
        "issuer": "opgi",
        "publish_days_ago": 7,
        "deadline_in_days": None,
        "value": None,
    },
    {
        "type": "contract_termination",
        "title_ar": "فسخ عقد إنجاز شبكة الصرف",
        "title_fr": "Résiliation du contrat de réalisation du réseau d'assainissement",
        "description_ar": (
            "قرار توضيحي بفسخ العقد بعد الإعذار، مع تسوية الوضعية المالية "
            "وإعادة إطلاق المشروع."
        ),
        "sectors": ["water", "construction"],
        "wilaya": "31",
        "issuer": "ona",
        "publish_days_ago": 8,
        "deadline_in_days": None,
        "value": None,
    },
    {
        "type": "contract_termination",
        "title_ar": "فسخ عقد صيانة التجهيزات الطبية",
        "title_fr": "Résiliation du contrat de maintenance des équipements médicaux",
        "description_ar": (
            "فسخ نموذجي لعقد الصيانة لعدم تنفيذ الالتزامات التعاقدية، "
            "مع إشعار المؤسسة المعنية."
        ),
        "sectors": ["health"],
        "wilaya": "25",
        "issuer": "ministere-sante",
        "publish_days_ago": 760,
        "deadline_in_days": None,
        "value": None,
    },
    {
        "type": "tender",
        "title_ar": "اقتناء خزانات بولي إيثيلين بسعة 1000 لتر",
        "title_fr": "Acquisition de réservoirs en polyéthylène de 1000 litres",
        "description_ar": (
            "مناقصة نموذجية لتوريد خزانات PE بسعة 1000 لتر لمشاريع مياه الشرب، "
            "مع التركيب في المواقع."
        ),
        "sectors": ["water"],
        "wilaya": "39",
        "issuer": "ade",
        "publish_days_ago": 1,
        "deadline_in_days": 18,
        "value": 12_750_000,
    },
    {
        "type": "tender",
        "title_ar": "إنجاز قناة نقل المياه نحو المنطقة الصناعية",
        "title_fr": "Réalisation d'une conduite d'adduction vers la zone industrielle",
        "description_ar": (
            "أشغال إنجاز قناة نقل المياه بطول 12 كلم مع المنشآت الهيدروليكية، "
            "إعلان توضيحي."
        ),
        "sectors": ["water", "industry"],
        "wilaya": "35",
        "issuer": "ade",
        "publish_days_ago": 12,
        "deadline_in_days": 60,
        "value": 320_000_000,
    },
    {
        "type": "consultation",
        "title_ar": "استشارة لاختيار مكتب دراسات لإعداد دفتر شروط",
        "title_fr": "Consultation pour le choix d'un bureau d'études",
        "description_ar": (
            "استشارة نموذجية لإعداد دفتر شروط تقني ودراسة جدوى "
            "لمشروع تحديث أنظمة النقل الحضري."
        ),
        "sectors": ["services", "transport"],
        "wilaya": "16",
        "issuer": "ministere-transports",
        "publish_days_ago": 400,
        "deadline_in_days": 12,
        "value": 1_800_000,
    },
    {
        "type": "auction",
        "title_ar": "مزاد لكراء فضاءات تجارية",
        "title_fr": "Enchère pour la location d'espaces commerciaux",
        "description_ar": (
            "مزاد نموذجي لكراء فضاءات تجارية تابعة للبلدية، "
            "مع تحديد مدة الكراء وضمان المشاركة."
        ),
        "sectors": ["services"],
        "wilaya": "25",
        "issuer": "apc-alger-centre",
        "publish_days_ago": 5,
        "deadline_in_days": 9,
        "value": 600_000,
    },
    {
        "type": "provisional_award",
        "title_ar": "الإسناد المؤقت لمشروع رقمنة الأرشيف",
        "title_fr": "Attribution provisoire du projet de numérisation des archives",
        "description_ar": (
            "نتيجة مؤقتة نموذجية لمشروع رقمنة الأرشيف البريدي "
            "مع خطة حفظ النسخ الاحتياطية."
        ),
        "sectors": ["it_telecom"],
        "wilaya": "25",
        "issuer": "algerie-poste",
        "publish_days_ago": 9,
        "deadline_in_days": None,
        "value": 24_000_000,
    },
    {
        "type": "cancellation",
        "title_ar": "إلغاء مزاد بيع تجهيزات قديمة",
        "title_fr": "Annulation de la vente aux enchères de matériels anciens",
        "description_ar": (
            "إلغاء مزاد نموذجي لعدم اكتمال شروط المعاينة، " "وسيُعاد الإعلان لاحقاً."
        ),
        "sectors": ["services"],
        "wilaya": "19",
        "issuer": "algerie-telecom",
        "publish_days_ago": 6,
        "deadline_in_days": None,
        "value": None,
    },
    {
        "type": "deadline_extension",
        "title_ar": "تمديد أجل استشارة خاصة بالنقل المدرسي",
        "title_fr": "Prorogation de délai – consultation pour le transport scolaire",
        "description_ar": (
            "تمديد نموذجي لأجل تقديم العروض الخاصة بالنقل المدرسي "
            "على مستوى عدة بلديات."
        ),
        "sectors": ["transport", "education"],
        "wilaya": "45",
        "issuer": "ministere-education",
        "publish_days_ago": 2,
        "deadline_in_days": 11,
        "value": None,
    },
]

#: Demonstration subcontracting offers (published unless noted).
OFFERS: list[dict[str, Any]] = [
    {
        "title": "بحث عن مقاولة من الباطن لإنجاز أشغال الترصيص",
        "description": (
            "مؤسسة مقاولات تبحث عن مقاولة من الباطن لإنجاز أشغال الترصيص "
            "داخل مشروع سكني بولاية قسنطينة. الخبرة المطلوبة: 3 سنوات."
        ),
        "sector": "construction",
        "wilaya": "25",
        "issuer_name": "مؤسسة نموذجية للبناء",
        "contact_name": "مسؤول المشتريات",
        "phone": "+213555000000",
        "email": "sous-traitance@example.dz",
        "deadline_in_days": 20,
        "status": "published",
        "days_ago": 2,
    },
    {
        "title": "مطلوب مورد أنابيب PEHD بكميات كبيرة",
        "description": (
            "طلب نموذجي لتوريد أنابيب PEHD بأقطار 110 و160 ملم لمشروع "
            "شبكة مياه، التسليم على مراحل."
        ),
        "sector": "water",
        "wilaya": "19",
        "issuer_name": "شركة نموذجية للمياه",
        "contact_name": "مصلحة المشتريات",
        "phone": "+213555000001",
        "email": "achats@example.dz",
        "deadline_in_days": 10,
        "status": "published",
        "days_ago": 1,
    },
    {
        "title": "مقاولة من الباطن للكهرباء الصناعية",
        "description": (
            "مشروع صناعي يبحث عن فريق مؤهل لتركيب وصيانة لوحات كهربائية "
            "ذات جهد متوسط. الإعلان نموذجي."
        ),
        "sector": "energy",
        "wilaya": "31",
        "issuer_name": "مجمع صناعي نموذجي",
        "contact_name": "قسم الصيانة",
        "phone": "+213555000002",
        "email": "energie@example.dz",
        "deadline_in_days": 25,
        "status": "published",
        "days_ago": 4,
    },
    {
        "title": "خدمات نقل ولوجستيك لمشروع مؤقت",
        "description": (
            "بحث عن متعامل نقل لتأمين نقل مواد البناء على المحور "
            "الجزائر – وهران، لمدة ثلاثة أشهر."
        ),
        "sector": "transport",
        "wilaya": "16",
        "issuer_name": "شركة لوجستيك نموذجية",
        "contact_name": "مدير العمليات",
        "phone": "+213555000003",
        "email": "logistique@example.dz",
        "deadline_in_days": 15,
        "status": "published",
        "days_ago": 3,
    },
    {
        "title": "عرض بانتظار المراجعة",
        "description": "هذا العرض نموذجي ولا يظهر في القائمة العامة قبل موافقة الإدارة.",
        "sector": "services",
        "wilaya": "25",
        "issuer_name": "مؤسسة نموذجية",
        "contact_name": "جهة الاتصال",
        "phone": "+213555000004",
        "email": "moderation@example.dz",
        "deadline_in_days": 30,
        "status": "pending",
        "days_ago": 1,
    },
]

__all__ = ["ISSUERS", "OFFERS", "PLANS", "SAMPLES", "SECTORS", "WILAYAS"]
