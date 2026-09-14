"""One-shot script: insert 72 explainer keys into 42 non-English locale files."""

import re, sys, os

sys.stdout.reconfigure(encoding="utf-8")

LOCALES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "src", "app", "locales"
)

# fmt: off
# Translations for all 72 keys across 42 locales.
# Structure: locale -> key -> value
# Technical terms kept in English: BOQ, takeoff, Celery, JSON, CSV, ABS, RFQ, PDF
# Module name keys use existing translations from the locale files.

TRANSLATIONS = {
    "ar": {
        # timeline (15)
        "timeline.flow_intro": "موجز زمني بكل حدث مهم في المشروع، مجمّع من جميع الوحدات حتى تتمكن من رؤية ما حدث ومن قام به ومتى.",
        "timeline.flow_title": "كيف يعمل الجدول الزمني للمشروع",
        "timeline.flow_step_1": "تسجيل الأحداث",
        "timeline.flow_step_1_desc": "يُسجَّل كل إنشاء وتحديث وتغيير حالة وحذف عبر جميع الوحدات تلقائيًا مع طابع زمني ومنفذ والكيان المتأثر.",
        "timeline.flow_step_2": "تصفح السجل",
        "timeline.flow_step_2_desc": "تظهر الأحداث بترتيب زمني عكسي. انقر على أي صف لتوسيع تفاصيله بما فيها انتقالات الحالة والبيانات الوصفية ورابط للسجل.",
        "timeline.flow_step_3": "التصفية والبحث",
        "timeline.flow_step_3_desc": "تضييق النطاق حسب الوحدة أو نوع الإجراء أو نطاق التاريخ. يطابق شريط البحث أيضًا أنواع الكيانات والأسباب في الصفحة الحالية.",
        "timeline.flow_step_4": "تصدير للمراجعة",
        "timeline.flow_step_4_desc": "نزّل العرض الحالي بصيغة CSV للمراجعة دون اتصال أو لإعداد التقارير. يتضمن التصدير جميع الأعمدة المرئية ويراعي المرشحات النشطة.",
        "timeline.flow_related": "ذو صلة:",
        "timeline.mod_jobs": "المهام الخلفية",
        "timeline.mod_correspondence": "المراسلات",
        "timeline.mod_deadlines": "المواعيد النهائية",
        "timeline.go_to_record": "الانتقال إلى السجل",
        # jobs (14)
        "jobs.flow_intro": "تتولى المهام الخلفية العمل الثقيل خارج الخيط الرئيسي حتى تبقى الواجهة متجاوبة. هذه الصفحة هي المكان الوحيد لمتابعة وإلغاء وفحص كل مهمة في قائمة الانتظار.",
        "jobs.flow_title": "كيف تعمل المهام الخلفية",
        "jobs.flow_step_1": "وضع المهام في قائمة الانتظار",
        "jobs.flow_step_1_desc": "تُرسَل العمليات طويلة الأمد كإنشاء PDF واستيراد البيانات وإعادة حسابات التكلفة إلى قائمة انتظار الخلفية بدلًا من تعطيل الواجهة.",
        "jobs.flow_step_2": "مراقبة التقدم",
        "jobs.flow_step_2_desc": "تعرض كل مهمة نوعها وحالتها وشريط تقدم مباشر. انقر على صف لرؤية التوقيت ومعرف مهمة Celery وحمولة النتيجة أو تفاصيل الخطأ.",
        "jobs.flow_step_3": "إلغاء أو تصدير",
        "jobs.flow_step_3_desc": "يمكن إلغاء المهام المتوقفة أو غير الضرورية أثناء انتظارها أو تشغيلها. تتيح المهام المنتهية تنزيل النتيجة أو حمولة الخطأ بصيغة JSON.",
        "jobs.flow_step_4": "التصفية والترحيل",
        "jobs.flow_step_4_desc": "تضييق القائمة حسب الحالة أو نوع المهمة والبحث في الصفحة الحالية. يحافظ الترحيل من جانب الخادم على استجابة العرض حتى مع آلاف التشغيلات.",
        "jobs.flow_related": "ذو صلة:",
        "jobs.mod_schedule": "الجدول الزمني 4D",
        "jobs.mod_settings": "الإعدادات",
        "jobs.mod_timeline": "الجدول الزمني للمشروع",
        # rfq_bidding (15)
        "rfq_bidding.flow_intro": "أنشئ طلب عروض أسعار وأرسله للموردين واجمع عروضهم وقارنها ثم امنح أفضل عرض - كل ذلك في مكان واحد.",
        "rfq_bidding.flow_title": "كيف يعمل تقديم العطاءات",
        "rfq_bidding.flow_step_1": "صياغة طلب العروض",
        "rfq_bidding.flow_step_1_desc": "صف النطاق وحدد تاريخ الاستحقاق واذكر الموردين الذين تريد دعوتهم. يبقى الطلب في مسودة حتى تكون مستعدًا.",
        "rfq_bidding.flow_step_2": "إصدار للموردين",
        "rfq_bidding.flow_step_2_desc": "أصدر الطلب ويتلقى الموردون دعوة لتقديم العطاء. يقدمون الأسعار لكل بند نطاق قبل تاريخ الاستحقاق.",
        "rfq_bidding.flow_step_3": "مقارنة العروض",
        "rfq_bidding.flow_step_3_desc": "افتح مصفوفة المقارنة لرؤية كل مورد جنبًا إلى جنب بندًا ببند. يُبرز الإجمالي الأدنى تلقائيًا.",
        "rfq_bidding.flow_step_4": "المنح والتتبع",
        "rfq_bidding.flow_step_4_desc": "اختر العرض الفائز ويُسجَّل المنح مع المورد والمبلغ والتاريخ. تتوفر المنح السابقة للمراجعة في تبويب المنح.",
        "rfq_bidding.flow_related": "ذو صلة:",
        "rfq_bidding.mod_tendering": "المناقصات",
        "rfq_bidding.mod_bid_management": "إدارة العطاءات",
        "rfq_bidding.mod_contracts": "العقود",
        "rfq_bidding.mod_subcontractors": "المقاولون من الباطن",
        # enterprise_workflows (14)
        "enterprise_workflows.flow_intro": "أنشئ مسارات اعتماد متعددة الخطوات لأي نوع كيان ثم تتبع كل طلب من التقديم حتى القرار النهائي.",
        "enterprise_workflows.flow_title": "كيف تعمل مسارات الموافقة",
        "enterprise_workflows.flow_step_1": "تحديد مسار العمل",
        "enterprise_workflows.flow_step_1_desc": "سمِّ المسار واختر نوع الكيان الذي يحكمه (أوامر التغيير والتعديلات والفواتير وما إلى ذلك) وأضف خطوات الاعتماد مع المعتمدين المطلوبين.",
        "enterprise_workflows.flow_step_2": "التفعيل والتعيين",
        "enterprise_workflows.flow_step_2_desc": "فعّل المسار ليبدأ تلقي الطلبات. تُوقف المسارات غير النشطة مؤقتًا دون حذفها.",
        "enterprise_workflows.flow_step_3": "مراجعة الطلبات",
        "enterprise_workflows.flow_step_3_desc": "عندما يُطلق سجل طلب اعتماد يظهر في تبويب طلبات الاعتماد. وافق على كل خطوة أو ارفضها ليتقدم الطلب أو يتوقف.",
        "enterprise_workflows.flow_step_4": "تتبع النتائج",
        "enterprise_workflows.flow_step_4_desc": "صفّ الطلبات حسب الحالة لمعرفة ما هو معلق أو موافق عليه أو مرفوض. تسجل سجلات التدقيق من اتخذ القرار ومتى.",
        "enterprise_workflows.flow_related": "ذو صلة:",
        "enterprise_workflows.mod_contracts": "العقود",
        "enterprise_workflows.mod_timeline": "الجدول الزمني للمشروع",
        "enterprise_workflows.mod_variations": "الأعمال الإضافية",
        # rebar_schedule (14)
        "rebar_schedule.flow_intro": "استورد جداول ثني الحديد من ملفات ABS وراجع الأشكال والأوزان المحللة وأنتج قوائم القطع مجمّعة حسب القطر للمشتريات.",
        "rebar_schedule.flow_title": "كيف تعمل جداول الحديد",
        "rebar_schedule.flow_step_1": "رفع ملف ABS",
        "rebar_schedule.flow_step_1_desc": "اسحب وأسقط أو تصفح لملف جدول ثني القضبان بامتداد .abs. يقرأ المحلل علامات القضبان ورموز الأشكال والأبعاد والكميات.",
        "rebar_schedule.flow_step_2": "مراجعة المعاينة",
        "rebar_schedule.flow_step_2_desc": "قبل التأكيد تحقق من الأشكال المحللة وأي تحذيرات. صحح المشكلات في الملف المصدر وأعد الرفع إذا لزم.",
        "rebar_schedule.flow_step_3": "فحص الأشكال والأوزان",
        "rebar_schedule.flow_step_3_desc": "افتح استيرادًا لرؤية كل علامة قضيب مع شكلها وقطرها وطولها وكميتها ووزنها الوحدوي. تعرض بطاقات الإحصاء الإجماليات بنظرة واحدة.",
        "rebar_schedule.flow_step_4": "إنشاء قوائم القطع",
        "rebar_schedule.flow_step_4_desc": "تجمع قائمة القطع القضبان حسب القطر وتجمع العدد والوزن جاهزة للطلب أو التصدير بصيغة .abs.",
        "rebar_schedule.flow_related": "ذو صلة:",
        "rebar_schedule.mod_boq": "جدول الكميات",
        "rebar_schedule.mod_quantities": "حصر الكميات",
        "rebar_schedule.mod_formwork": "القوالب",
    },
    "bg": {
        "timeline.flow_intro": "Хронологичен поток от всяко значимо събитие в проекта, събирано от всички модули, за да виждате какво се е случило, кой го е направил и кога.",
        "timeline.flow_title": "Как работи хронологията на проекта",
        "timeline.flow_step_1": "Събитията се записват",
        "timeline.flow_step_1_desc": "Всяко създаване, актуализация, промяна на статус и изтриване в всички модули се регистрира автоматично с времева марка, изпълнител и засегнат обект.",
        "timeline.flow_step_2": "Преглед на потока",
        "timeline.flow_step_2_desc": "Събитията се показват в обратен хронологичен ред. Щракнете върху ред, за да разгърнете детайлите му, включително преходи на статус, метаданни и връзка към записа.",
        "timeline.flow_step_3": "Филтриране и търсене",
        "timeline.flow_step_3_desc": "Стесняване по модул, тип действие или период. Търсачката съответства и на типове обекти и причини на текущата страница.",
        "timeline.flow_step_4": "Експорт за одит",
        "timeline.flow_step_4_desc": "Изтеглете текущия изглед като CSV за офлайн преглед или докладване за съответствие. Експортът включва всички видими колони и спазва активните филтри.",
        "timeline.flow_related": "Свързани:",
        "timeline.mod_jobs": "Фонови задачи",
        "timeline.mod_correspondence": "Кореспонденция",
        "timeline.mod_deadlines": "Крайни срокове",
        "timeline.go_to_record": "Към записа",
        "jobs.flow_intro": "Фоновите задачи извършват тежка работа извън главния поток, за да остане интерфейсът отзивчив. Тази страница е единственото място за наблюдение, отмяна и проверка на всяка задача в опашката.",
        "jobs.flow_title": "Как работят фоновите задачи",
        "jobs.flow_step_1": "Задачите се поставят в опашка",
        "jobs.flow_step_1_desc": "Дълготрайни операции като генериране на PDF, импорт на данни и преизчисления на разходи се изпращат в опашката на фона вместо да блокират потребителския интерфейс.",
        "jobs.flow_step_2": "Мониторинг на напредъка",
        "jobs.flow_step_2_desc": "Всяка задача показва вида, статуса и жива лента за напредък. Щракнете върху ред, за да видите времето, идентификатора на задачата Celery, данните от резултата или детайлите за грешката.",
        "jobs.flow_step_3": "Отмяна или експорт",
        "jobs.flow_step_3_desc": "Заседналите или ненужни задачи могат да бъдат отменени, докато са в очакване или изпълнение. Завършените задачи позволяват изтегляне на резултата или данните за грешката като JSON.",
        "jobs.flow_step_4": "Филтриране и страниране",
        "jobs.flow_step_4_desc": "Стеснете списъка по статус или вид задача и търсете на текущата страница. Страниране от страна на сървъра запазва изгледа отзивчив дори с хиляди изпълнения.",
        "jobs.flow_related": "Свързани:",
        "jobs.mod_schedule": "4D график",
        "jobs.mod_settings": "Настройки",
        "jobs.mod_timeline": "Хронология на проекта",
        "rfq_bidding.flow_intro": "Създайте заявка за оферта, изпратете я на доставчиците, съберете и сравнете офертите им, след което присъдете най-добрата - всичко на едно място.",
        "rfq_bidding.flow_title": "Как работи наддаването по RFQ",
        "rfq_bidding.flow_step_1": "Изготвяне на RFQ",
        "rfq_bidding.flow_step_1_desc": "Опишете обхвата, задайте срок и посочете доставчиците, които искате да поканите. RFQ остава в чернова до готовност.",
        "rfq_bidding.flow_step_2": "Издаване на доставчиците",
        "rfq_bidding.flow_step_2_desc": "Издайте RFQ и доставчиците получават покана за наддаване. Те подават ценообразуване за всеки ред от обхвата преди срока.",
        "rfq_bidding.flow_step_3": "Сравнение на оферти",
        "rfq_bidding.flow_step_3_desc": "Отворете матрицата за сравнение, за да видите всеки доставчик един до друг, ред по ред. Най-ниската сума се откроява автоматично.",
        "rfq_bidding.flow_step_4": "Присъждане и проследяване",
        "rfq_bidding.flow_step_4_desc": "Изберете спечелилата оферта и присъждането се записва с доставчика, сумата и датата. Минали присъждания са достъпни за одит в раздел Присъждания.",
        "rfq_bidding.flow_related": "Свързани:",
        "rfq_bidding.mod_tendering": "Тръжна процедура",
        "rfq_bidding.mod_bid_management": "Управление на оферти",
        "rfq_bidding.mod_contracts": "Договори",
        "rfq_bidding.mod_subcontractors": "Подизпълнители",
        "enterprise_workflows.flow_intro": "Настройте многостъпални маршрути за одобрение за всякакъв тип обект, след което проследете всяка заявка от подаването до окончателното решение.",
        "enterprise_workflows.flow_title": "Как работят корпоративните работни потоци",
        "enterprise_workflows.flow_step_1": "Дефиниране на работен поток",
        "enterprise_workflows.flow_step_1_desc": "Наименувайте работния поток, изберете типа обект, който управлява (заповеди за промяна, анекси, фактури и др.) и добавете стъпки за одобрение с необходимите одобряващи.",
        "enterprise_workflows.flow_step_2": "Активиране и присвояване",
        "enterprise_workflows.flow_step_2_desc": "Включете работния поток, за да започне да получава заявки. Неактивните работни потоци са паузирани без да бъдат изтрити.",
        "enterprise_workflows.flow_step_3": "Преглед на заявките",
        "enterprise_workflows.flow_step_3_desc": "Когато запис задейства одобрение, то се появява в раздел Заявки за одобрение. Одобрете или отхвърлете всяка стъпка и заявката напредва или спира.",
        "enterprise_workflows.flow_step_4": "Проследяване на резултатите",
        "enterprise_workflows.flow_step_4_desc": "Филтрирайте заявките по статус, за да видите кои са в изчакване, одобрени или отхвърлени. Одитният запис отбелязва кой е решил и кога.",
        "enterprise_workflows.flow_related": "Свързани:",
        "enterprise_workflows.mod_contracts": "Договори",
        "enterprise_workflows.mod_timeline": "Хронология на проекта",
        "enterprise_workflows.mod_variations": "Анекси",
        "rebar_schedule.flow_intro": "Импортирайте графици за огъване на армировка от ABS файлове, прегледайте разпознатите форми и тегла и генерирайте списъци за рязане, групирани по диаметър за доставки.",
        "rebar_schedule.flow_title": "Как работят графиците за армировка",
        "rebar_schedule.flow_step_1": "Качване на ABS файл",
        "rebar_schedule.flow_step_1_desc": "Плъзнете и пуснете или намерете .abs файл с график за огъване. Парсерът чете маркировки на пръти, кодове на форми, размери и количества.",
        "rebar_schedule.flow_step_2": "Преглед на предварителния изглед",
        "rebar_schedule.flow_step_2_desc": "Преди потвърждаване проверете разпознатите форми и евентуалните предупреждения. Коригирайте проблемите в изходния файл и качете повторно при нужда.",
        "rebar_schedule.flow_step_3": "Проверка на форми и тегла",
        "rebar_schedule.flow_step_3_desc": "Отворете импорт, за да видите всяка маркировка на прът с формата, диаметъра, дължината, количеството и единичното тегло. Картите с показатели показват общите стойности.",
        "rebar_schedule.flow_step_4": "Генериране на списъци за рязане",
        "rebar_schedule.flow_step_4_desc": "Списъкът за рязане групира пръти по диаметър и сумира броя и теглото, готови за поръчка или експорт обратно в .abs.",
        "rebar_schedule.flow_related": "Свързани:",
        "rebar_schedule.mod_boq": "Количествена сметка",
        "rebar_schedule.mod_quantities": "Количествено изчисление",
        "rebar_schedule.mod_formwork": "Кофраж",
    },
}
# fmt: on

# Anchor keys and the block of new keys to insert after each anchor
ANCHORS = {
    '"timeline.system"': "timeline",
    '"jobs.status_cancelled"': "jobs",
    '"rfq_bidding.vendors_count"': "rfq_bidding",
    '"enterprise_workflows.workflow_name"': "enterprise_workflows",
    '"rebar_schedule.weight_col"': "rebar_schedule",
}

KEY_ORDER = {
    "timeline": [
        "timeline.flow_intro",
        "timeline.flow_title",
        "timeline.flow_step_1",
        "timeline.flow_step_1_desc",
        "timeline.flow_step_2",
        "timeline.flow_step_2_desc",
        "timeline.flow_step_3",
        "timeline.flow_step_3_desc",
        "timeline.flow_step_4",
        "timeline.flow_step_4_desc",
        "timeline.flow_related",
        "timeline.mod_jobs",
        "timeline.mod_correspondence",
        "timeline.mod_deadlines",
        "timeline.go_to_record",
    ],
    "jobs": [
        "jobs.flow_intro",
        "jobs.flow_title",
        "jobs.flow_step_1",
        "jobs.flow_step_1_desc",
        "jobs.flow_step_2",
        "jobs.flow_step_2_desc",
        "jobs.flow_step_3",
        "jobs.flow_step_3_desc",
        "jobs.flow_step_4",
        "jobs.flow_step_4_desc",
        "jobs.flow_related",
        "jobs.mod_schedule",
        "jobs.mod_settings",
        "jobs.mod_timeline",
    ],
    "rfq_bidding": [
        "rfq_bidding.flow_intro",
        "rfq_bidding.flow_title",
        "rfq_bidding.flow_step_1",
        "rfq_bidding.flow_step_1_desc",
        "rfq_bidding.flow_step_2",
        "rfq_bidding.flow_step_2_desc",
        "rfq_bidding.flow_step_3",
        "rfq_bidding.flow_step_3_desc",
        "rfq_bidding.flow_step_4",
        "rfq_bidding.flow_step_4_desc",
        "rfq_bidding.flow_related",
        "rfq_bidding.mod_tendering",
        "rfq_bidding.mod_bid_management",
        "rfq_bidding.mod_contracts",
        "rfq_bidding.mod_subcontractors",
    ],
    "enterprise_workflows": [
        "enterprise_workflows.flow_intro",
        "enterprise_workflows.flow_title",
        "enterprise_workflows.flow_step_1",
        "enterprise_workflows.flow_step_1_desc",
        "enterprise_workflows.flow_step_2",
        "enterprise_workflows.flow_step_2_desc",
        "enterprise_workflows.flow_step_3",
        "enterprise_workflows.flow_step_3_desc",
        "enterprise_workflows.flow_step_4",
        "enterprise_workflows.flow_step_4_desc",
        "enterprise_workflows.flow_related",
        "enterprise_workflows.mod_contracts",
        "enterprise_workflows.mod_timeline",
        "enterprise_workflows.mod_variations",
    ],
    "rebar_schedule": [
        "rebar_schedule.flow_intro",
        "rebar_schedule.flow_title",
        "rebar_schedule.flow_step_1",
        "rebar_schedule.flow_step_1_desc",
        "rebar_schedule.flow_step_2",
        "rebar_schedule.flow_step_2_desc",
        "rebar_schedule.flow_step_3",
        "rebar_schedule.flow_step_3_desc",
        "rebar_schedule.flow_step_4",
        "rebar_schedule.flow_step_4_desc",
        "rebar_schedule.flow_related",
        "rebar_schedule.mod_boq",
        "rebar_schedule.mod_quantities",
        "rebar_schedule.mod_formwork",
    ],
}


def escape_ts_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def insert_keys_into_file(locale: str, path: str, translations: dict) -> None:
    content = open(path, encoding="utf-8").read()
    lines = content.splitlines(keepends=True)

    for anchor_pattern, namespace in ANCHORS.items():
        keys = KEY_ORDER[namespace]
        # Find the anchor line
        anchor_idx = None
        for i, line in enumerate(lines):
            if anchor_pattern in line:
                anchor_idx = i
                break
        if anchor_idx is None:
            print(f"  WARNING: anchor {anchor_pattern} not found in {locale}.ts")
            continue

        # Build insertion lines
        insertion = []
        for key in keys:
            value = translations.get(key, "")
            if not value:
                print(f"  WARNING: no translation for {key} in {locale}")
                value = ""
            escaped = escape_ts_string(value)
            insertion.append(f'    "{key}": "{escaped}",\n')

        # Insert after anchor line
        lines = lines[: anchor_idx + 1] + insertion + lines[anchor_idx + 1 :]

    new_content = "".join(lines)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  OK: {locale}.ts")


if __name__ == "__main__":
    for locale, translations in TRANSLATIONS.items():
        path = os.path.join(LOCALES_DIR, f"{locale}.ts")
        if not os.path.exists(path):
            print(f"SKIP: {path} not found")
            continue
        print(f"Processing {locale}...")
        insert_keys_into_file(locale, path, translations)
    print("Done.")
