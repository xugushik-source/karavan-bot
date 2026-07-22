import os
import json
import logging
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse

# ─── НАСТРОЙКИ (задаются в Railway → Variables) ───────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")      # приватный чат/канал владельца — сюда падает копия всего (всегда на русском)
GROUP_CHAT_ID = os.environ.get("GROUP_CHAT_ID", "")      # публичный чат/канал, куда публикуются анонимные объявления
PORT = int(os.environ.get("PORT", 8080))
ACCOUNT_DETAILS = os.environ.get("ACCOUNT_DETAILS", "")  # запасной вариант — просто текст (например, для наличных инструкций)
ACCOUNT_LINK_TBC = os.environ.get("ACCOUNT_LINK_TBC", "")   # ссылка на оплату через TBC
ACCOUNT_LINK_BOG = os.environ.get("ACCOUNT_LINK_BOG", "")   # ссылка на оплату через Bank of Georgia


def payment_lines():
    lines = []
    if ACCOUNT_LINK_TBC:
        lines.append(f'💳 <a href="{ACCOUNT_LINK_TBC}">Оплатить через TBC</a>')
    if ACCOUNT_LINK_BOG:
        lines.append(f'💳 <a href="{ACCOUNT_LINK_BOG}">Оплатить через Bank of Georgia</a>')
    if not lines and ACCOUNT_DETAILS:
        lines.append(ACCOUNT_DETAILS)
    if not lines:
        lines.append("реквизиты не заданы — добавь ACCOUNT_LINK_TBC в Railway")
    return "\n".join(lines)
COMMISSION = os.environ.get("COMMISSION", "10")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "karavan_ge_bot")

ACTIVE_CORRIDORS = ["tbilisi", "yerevan"]
LANGS = ["ru", "ka", "hy"]

# ═══════════════════════════════════════════════════════════════
# ПЕРЕВОДЫ.
# RU — уверенный текст.
# KA/HY — ЧЕРНОВИК, требует проверки носителем перед реальным запуском.
# ═══════════════════════════════════════════════════════════════
LANG_NAMES = {"ru": "🇷🇺 Русский", "ka": "🇬🇪 ქართული", "hy": "🇦🇲 Հայերեն"}

CORRIDOR_NAMES = {
    "tbilisi": {"ru": "Тбилиси", "ka": "თბილისი", "hy": "Թբիլիսի"},
    "yerevan": {"ru": "Ереван", "ka": "ერევანი", "hy": "Երևան"},
    "kutaisi": {"ru": "Кутаиси", "ka": "ქუთაისი", "hy": "Քութայիսի"},
    "batumi": {"ru": "Батуми", "ka": "ბათუმი", "hy": "Բաթում"},
}

VARIANT_NAMES = {
    "akhaltsikhe": {"ru": "через Ахалцихе", "ka": "ახალციხის გავლით", "hy": "Ախալցխայով"},
    "tsalka": {"ru": "через Цалку", "ka": "წალკის გავლით", "hy": "Ծալկայով"},
}

CORRIDORS = {
    "tbilisi": {"variants": ["akhaltsikhe", "tsalka"]},
    "yerevan": {"variants": None},
    "kutaisi": {"variants": None},
    "batumi": {"variants": None},
}

CARRY_KEYS = ["person", "parcel", "both"]
CARRY_NAMES = {
    "person": {"ru": "🙋 человека", "ka": "🙋 ადამიანი", "hy": "🙋 մարդ"},
    "parcel": {"ru": "📦 посылку", "ka": "📦 გზავნილი", "hy": "📦 ծանրոց"},
    "both": {"ru": "🙋+📦 и то, и то", "ka": "🙋+📦 ორივე", "hy": "🙋+📦 երկուսն էլ"},
}

T = {
    "choose_lang": {"ru": "Выберите язык:", "ka": "აირჩიეთ ენა:", "hy": "Ընտրեք լեզուն:"},
    "welcome": {
        "ru": "🐫 <b>Karavan</b> — попутки и посылки Ахалкалаки ⇄ Тбилиси / Ереван\n\nВыберите действие:",
        "ka": "🐫 <b>Karavan</b> — თანამგზავრები და გზავნილები ახალქალაქი ⇄ თბილისი / ერევანი\n\nაირჩიეთ მოქმედება:",
        "hy": "🐫 <b>Karavan</b> — ուղեկիցներ և ծանրոցներ Ախալքալաք ⇄ Թբիլիսի / Երևան\n\nԸնտրեք գործողությունը:",
    },
    "btn_offer": {"ru": "🚗 Еду — предложить место/доставку", "ka": "🚗 მივდივარ — ადგილის/გზავნილის შეთავაზება", "hy": "🚗 Գնում եմ — առաջարկել տեղ/առաքում"},
    "btn_request": {"ru": "🙋 Мне нужно — доехать/отправить", "ka": "🙋 მჭირდება — წასვლა/გაგზავნა", "hy": "🙋 Ինձ պետք է — գնալ/ուղարկել"},
    "btn_my_listings": {"ru": "📋 Мои объявления", "ka": "📋 ჩემი განცხადებები", "hy": "📋 Իմ հայտարարությունները"},
    "ask_corridor_offer": {"ru": "🚗 Куда едете?", "ka": "🚗 საით მიდიხართ?", "hy": "🚗 Ուր եք գնում?"},
    "ask_corridor_request": {"ru": "🙋 Куда вам нужно?", "ka": "🙋 საით გჭირდებათ?", "hy": "🙋 Ուր է Ձեզ պետք?"},
    "ask_variant": {"ru": "🛣 Каким путём?", "ka": "🛣 რომელი გზით?", "hy": "🛣 Որ ճանապարհով?"},
    "variant_any": {"ru": "Без разницы", "ka": "არ აქვს მნიშვნელობა", "hy": "Կարևոր չէ"},
    "ask_carry_offer": {"ru": "📦 Что можете взять?", "ka": "📦 რისი წაღება შეგიძლიათ?", "hy": "📦 Ի՞նչ կարող եք վերցնել"},
    "ask_carry_request": {"ru": "📦 Что вам нужно?", "ka": "📦 რა გჭირდებათ?", "hy": "📦 Ի՞նչ է Ձեզ պետք"},
    "ask_capacity": {"ru": "🔢 Сколько мест/посылок можете взять? Напишите цифрой (например: 2)",
                      "ka": "🔢 რამდენი ადგილი/გზავნილი შეგიძლიათ? დაწერეთ ციფრით (მაგ: 2)",
                      "hy": "🔢 Քանի՞ տեղ/ծանրոց կարող եք վերցնել: Գրեք թվով (օրինակ՝ 2)"},
    "capacity_error": {"ru": "⚠️ Нужна просто цифра, например: 2", "ka": "⚠️ საჭიროა მხოლოდ ციფრი, მაგალითად: 2", "hy": "⚠️ Պետք է միայն թիվ, օրինակ՝ 2"},
    "ask_price": {"ru": "💵 Сколько стоит? Напишите цену в лари (например: 40)",
                  "ka": "💵 რა ღირს? დაწერეთ ფასი ლარში (მაგ: 40)",
                  "hy": "💵 Որքա՞ն արժե: Գրեք գինը լարիով (օրինակ՝ 40)"},
    "price_error": {"ru": "⚠️ Нужна цена цифрой, например: 40", "ka": "⚠️ საჭიროა ფასი ციფრით, მაგალითად: 40", "hy": "⚠️ Պետք է գին թվով, օրինակ՝ 40"},
    "ask_time": {"ru": "🕐 Когда? Напишите время или окно (например: 9:00-12:00 или просто 12:00)",
                 "ka": "🕐 როდის? დაწერეთ დრო ან შუალედი (მაგ: 9:00-12:00 ან უბრალოდ 12:00)",
                 "hy": "🕐 Ե՞րբ: Գրեք ժամը կամ միջակայքը (օրինակ՝ 9:00-12:00 կամ պարզապես 12:00)"},
    "ask_name": {"ru": "Как вас зовут?", "ka": "რა გქვიათ?", "hy": "Ի՞նչ է Ձեր անունը:"},
    "ask_share_phone": {"ru": "📞 Нажмите кнопку ниже, чтобы поделиться номером телефона — это номер вашего Telegram-аккаунта, Telegram уже проверил его SMS-кодом при регистрации.",
                         "ka": "📞 დააჭირეთ ღილაკს, რომ გაუზიაროთ ტელეფონის ნომერი — ეს თქვენი Telegram ანგარიშის ნომერია, Telegram-მა უკვე დაადასტურა ის SMS-კოდით რეგისტრაციისას.",
                         "hy": "📞 Սեղմեք կոճակը՝ հեռախոսահամարը կիսելու համար — սա Ձեր Telegram հաշվի համարն է, Telegram-ն արդեն հաստատել է այն SMS-կոդով գրանցվելիս:"},
    "btn_share_phone": {"ru": "📞 Поделиться номером", "ka": "📞 ნომრის გაზიარება", "hy": "📞 Կիսվել համարով"},
    "not_own_contact": {"ru": "⚠️ Это должен быть именно ваш собственный контакт — нажмите кнопку ниже.",
                         "ka": "⚠️ ეს უნდა იყოს სწორედ თქვენი საკუთარი კონტაქტი — დააჭირეთ ღილაკს ქვემოთ.",
                         "hy": "⚠️ Սա պետք է լինի հենց Ձեր սեփական կոնտակտը — սեղմեք ստորև կոճակը:"},
    "published": {"ru": "✅ Опубликовано! Как только кто-то откликнется — пришлю контакт.",
                  "ka": "✅ გამოქვეყნდა! როგორც კი ვინმე გამოეხმაურება — გამოგიგზავნით კონტაქტს.",
                  "hy": "✅ Հրապարակված է! Հենց որևէ մեկը արձագանքի — կուղարկեմ կոնտակտը:"},
    "future_commission_note": {"ru": "💵 Учтите заранее: когда кто-то откликнется, нужно будет заплатить комиссию сервису — {sum} лари, на счёт:\n{account}",
                                "ka": "💵 გაითვალისწინეთ: როცა ვინმე გამოეხმაურება, საჭირო იქნება საკომისიოს გადახდა — {sum} ლარი, ანგარიშზე:\n{account}",
                                "hy": "💵 Նախապես նկատի ունեցեք. երբ որևէ մեկը արձագանքի, պետք է վճարեք միջնորդավճար՝ {sum} լարի, հաշվին՝\n{account}"},
    "disclaimer": {"ru": "⚠️ <b>Важно перед началом:</b>\nKaravan только знакомит людей друг с другом. Мы не несём ответственности за качество услуги, безопасность поездки, утерю вещей или недобросовестность другой стороны. Убедитесь в надёжности собеседника самостоятельно перед тем как договариваться.",
                    "ka": "⚠️ <b>მნიშვნელოვანია დაწყებამდე:</b>\nKaravan მხოლოდ აკავშირებს ადამიანებს ერთმანეთთან. ჩვენ არ ვიღებთ პასუხისმგებლობას მომსახურების ხარისხზე, მგზავრობის უსაფრთხოებაზე, ნივთის დაკარგვაზე ან მეორე მხარის არაკეთილსინდისიერებაზე. დარწმუნდით მოსაუბრის სანდოობაში დამოუკიდებლად, სანამ შეთანხმდებით.",
                    "hy": "⚠️ <b>Կարևոր է սկսելուց առաջ.</b>\nKaravan-ը միայն կապակցում է մարդկանց միմյանց հետ։ Մենք պատասխանատվություն չենք կրում ծառայության որակի, ուղևորության անվտանգության, իրերի կորստի կամ մյուս կողմի անազնվության համար։ Համոզվեք զրուցակցի հուսալիությունում ինքնուրույն, նախքան պայմանավորվելը։"},
    "claim_button": {"ru": "✋ Откликнуться", "ka": "✋ გამოხმაურება", "hy": "✋ Արձագանքել"},
    "claim_taken": {"ru": "⚠️ Это уже занято другим человеком — опоздали буквально чуть-чуть.",
                     "ka": "⚠️ ეს უკვე დაკავებულია სხვის მიერ.", "hy": "⚠️ Սա արդեն զբաղված է ուրիշի կողմից:"},
    "claim_own": {"ru": "⚠️ Нельзя откликнуться на своё же объявление.",
                   "ka": "⚠️ საკუთარ განცხადებაზე ვერ გამოეხმაურებით.", "hy": "⚠️ Չեք կարող արձագանքել սեփական հայտարարությանը:"},
    "claim_owner_notice": {"ru": "✅ По объявлению #{id} есть отклик!\nКонтакт: {contact}\n\nДоговоритесь напрямую о месте встречи и оплате поездки.",
                            "ka": "✅ განცხადებაზე #{id} მოვიდა გამოხმაურება!\nკონტაქტი: {contact}\n\nშეთანხმდით პირდაპირ შეხვედრასა და გადახდაზე.",
                            "hy": "✅ #{id} հայտարարությանը կա արձագանք!\nԿոնտակտ՝ {contact}\n\nՊայմանավորվեք ուղղակիորեն հանդիպման և վճարման մասին:"},
    "claim_claimant_notice": {"ru": "✅ Вы откликнулись на #{id}!\nКонтакт: {contact}\n\nДоговоритесь напрямую о месте встречи и оплате поездки.",
                               "ka": "✅ თქვენ გამოეხმაურეთ #{id}-ს!\nკონტაქტი: {contact}\n\nშეთანხმდით პირდაპირ შეხვედრასა და გადახდაზე.",
                               "hy": "✅ Դուք արձագանքեցիք #{id}-ին!\nԿոնտակտ՝ {contact}\n\nՊայմանավորվեք ուղղակիորեն հանդիպման և վճարման մասին:"},
    "done_button": {"ru": "✅ Комиссию оплатил", "ka": "✅ საკომისიო გადავიხადე", "hy": "✅ Միջնորդավճարը վճարեցի"},
    "commission_now": {"ru": "💵 Комиссия сервису: {sum} лари\n\nПереводом на счёт:\n{account}\n\nНаличными — по договорённости.\n\nКогда оплатите — нажмите кнопку ниже.",
                        "ka": "💵 საკომისიო სერვისს: {sum} ლარი\n\nგადარიცხვით ანგარიშზე:\n{account}\n\nნაღდი ფული — შეთანხმებით.\n\nროცა გადაიხდით — დააჭირეთ ღილაკს.",
                        "hy": "💵 Ծառայության միջնորդավճար՝ {sum} լարի\n\nՓոխանցումով հաշվին՝\n{account}\n\nԿանխիկ՝ պայմանավորվածությամբ.\n\nԵրբ վճարեք՝ սեղմեք կոճակը."},
    "paid_confirmed": {"ru": "✅ Спасибо, отмечено как оплачено!", "ka": "✅ გმადლობთ, აღინიშნა როგორც გადახდილი!", "hy": "✅ Շնորհակալություն, նշվել է որպես վճարված!"},
    "listing_closed": {"ru": "🔒 Занято — совпадение уже найдено.", "ka": "🔒 დაკავებულია — მატჩი უკვე ნაპოვნია.", "hy": "🔒 Զբաղված է — համընկնում արդեն գտնվել է:"},
    "btn_show_open": {"ru": "📋 Все открытые заявки", "ka": "📋 ყველა ღია განცხადება", "hy": "📋 Բոլոր բաց հայտարարությունները"},
    "no_open_listings": {"ru": "Открытых заявок пока нет.", "ka": "ჯერ არ არის ღია განცხადებები.", "hy": "Բաց հայտարարություններ դեռ չկան:"},
    "my_listings_empty": {"ru": "У вас пока нет объявлений.", "ka": "თქვენ ჯერ არ გაქვთ განცხადებები.", "hy": "Դուք դեռ հայտարարություններ չունեք:"},
    "my_listings_header": {"ru": "📋 Ваши объявления:", "ka": "📋 თქვენი განცხადებები:", "hy": "📋 Ձեր հայտարարությունները:"},
    "unknown": {"ru": "Не понял. Нажмите /start, чтобы увидеть меню.", "ka": "ვერ გავიგე. დააჭირეთ /start მენიუს სანახავად.",
                "hy": "Չհասկացա: Սեղմեք /start՝ ցանկը տեսնելու համար:"},
}

# ─── ЛОГИ ──────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# ─── ХРАНИЛИЩЕ (файл на диске — переживает перезапуск сервера) ─
DATA_FILE = "data.json"
lock = threading.Lock()

listings = {}
users = {}              # chat_id -> {"lang": "ru", "name": "Гиви", "phone": "+995555123456" (подтверждён Telegram)}
drafts = {}
pending_start_action = {}   # chat_id -> "offer"/"request"/"open", если человек пришёл по ссылке до выбора языка
listing_counter = [0]


def load_data():
    global listings, users, listing_counter
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            listings = raw.get("listings", {})
            users = raw.get("users", {})
            listing_counter[0] = raw.get("counter", 0)
            log.info(f"Загружено {len(listings)} объявлений, {len(users)} пользователей")
        except Exception as e:
            log.error(f"Не смог загрузить {DATA_FILE}: {e}")


def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"listings": listings, "users": users, "counter": listing_counter[0]},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Не смог сохранить {DATA_FILE}: {e}")


def get_lang(chat_id):
    return users.get(str(chat_id), {}).get("lang", "ru")


def t(chat_id, key, **kwargs):
    lang = get_lang(chat_id)
    text = T.get(key, {}).get(lang) or T.get(key, {}).get("ru") or key
    if kwargs:
        text = text.format(**kwargs)
    return text


def corridor_name(chat_id, corridor_key):
    lang = get_lang(chat_id)
    return CORRIDOR_NAMES[corridor_key].get(lang) or CORRIDOR_NAMES[corridor_key]["ru"]


def variant_name(chat_id, variant_key):
    lang = get_lang(chat_id)
    return VARIANT_NAMES[variant_key].get(lang) or VARIANT_NAMES[variant_key]["ru"]


def carry_name(chat_id, carry_key):
    lang = get_lang(chat_id)
    return CARRY_NAMES[carry_key].get(lang) or CARRY_NAMES[carry_key]["ru"]


# ─── ОТПРАВКА В TELEGRAM ───────────────────────────────────────
def tg_call(method, payload):
    if not BOT_TOKEN:
        log.warning("BOT_TOKEN не задан")
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        log.error(f"Ошибка {method}: {e}")
        return None


def tg_send(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_call("sendMessage", payload)


def tg_edit(chat_id, message_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_call("editMessageText", payload)


def notify_admin(text):
    if ADMIN_CHAT_ID:
        tg_send(ADMIN_CHAT_ID, text)  # админ-канал всегда на русском — это твой личный лог


def answer_callback(callback_id, text=None, show_alert=False):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    tg_call("answerCallbackQuery", payload)


# ─── КЛАВИАТУРЫ ─────────────────────────────────────────────────
def kb_lang():
    return {"inline_keyboard": [[{"text": LANG_NAMES[l], "callback_data": f"lang_{l}"}] for l in LANGS]}


def kb_main(chat_id):
    return {"inline_keyboard": [
        [{"text": t(chat_id, "btn_offer"), "callback_data": "start_offer"}],
        [{"text": t(chat_id, "btn_request"), "callback_data": "start_request"}],
        [{"text": t(chat_id, "btn_my_listings"), "callback_data": "my_listings"}],
    ]}


def kb_corridors(chat_id, prefix):
    buttons = []
    for key in ACTIVE_CORRIDORS:
        buttons.append([{"text": corridor_name(chat_id, key), "callback_data": f"{prefix}_corr_{key}"}])
    return {"inline_keyboard": buttons}


def kb_variant(chat_id, prefix, corridor_key):
    variant_keys = CORRIDORS[corridor_key]["variants"]
    buttons = [[{"text": variant_name(chat_id, vk), "callback_data": f"{prefix}_var_{vk}"}] for vk in variant_keys]
    buttons.append([{"text": t(chat_id, "variant_any"), "callback_data": f"{prefix}_var_any"}])
    return {"inline_keyboard": buttons}


def kb_carry(chat_id, prefix):
    return {"inline_keyboard": [
        [{"text": carry_name(chat_id, key), "callback_data": f"{prefix}_carry_{key}"}] for key in CARRY_KEYS
    ]}


def kb_claim(chat_id, listing_id):
    return {"inline_keyboard": [[{"text": t(chat_id, "claim_button"), "callback_data": f"claim_{listing_id}"}]]}


def kb_done(chat_id, listing_id):
    return {"inline_keyboard": [[{"text": t(chat_id, "done_button"), "callback_data": f"done_{listing_id}"}]]}


def kb_share_phone(chat_id):
    return {
        "keyboard": [[{"text": t(chat_id, "btn_share_phone"), "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }


def kb_group_start():
    base = f"https://t.me/{BOT_USERNAME}?start="
    return {"inline_keyboard": [
        [{"text": "🚗 Еду / მივდივარ / Գնում եմ", "url": base + "offer"}],
        [{"text": "🙋 Нужно / მჭირდება / Ինձ պետք է", "url": base + "request"}],
        [{"text": "📋 Открытые заявки / ღია განცხადებები / Բաց հայտարարություններ", "url": base + "open"}],
    ]}


def show_open_listings(chat_id):
    open_listings = [l for l in listings.values() if l["status"] == "open"]
    if not open_listings:
        return tg_send(chat_id, t(chat_id, "no_open_listings"))
    sent = None
    for l in open_listings[-20:]:
        icon = "🚗" if l["kind"] == "offer" else "🙋"
        variant_label = None
        if CORRIDORS[l["corridor"]]["variants"] and l.get("variant") and l["variant"] != "any":
            variant_label = variant_name(chat_id, l["variant"])
        text = (
            f"{icon} <b>#{l['id']} — {corridor_name(chat_id, l['corridor'])}</b>"
            + (f" ({variant_label})" if variant_label else "") + "\n"
            f"{carry_name(chat_id, l['carry'])}\n"
            + (f"{l['capacity']}\n" if l.get("capacity") else "")
            + (f"{l['price']} ₾\n" if l.get("price") else "")
            + f"🕐 {l.get('time','—')}"
        )
        sent = tg_send(chat_id, text, reply_markup=kb_claim(chat_id, l["id"]))
    return sent


# ─── ЧЕРНОВИК ОБЪЯВЛЕНИЯ ────────────────────────────────────────
def start_offer(chat_id):
    intro = tg_send(chat_id, t(chat_id, "disclaimer"))
    tg_send(chat_id, t(chat_id, "future_commission_note", sum=COMMISSION, account=payment_lines()))
    drafts[chat_id] = {"kind": "offer", "step": "corridor"}
    result = tg_send(chat_id, t(chat_id, "ask_corridor_offer"), reply_markup=kb_corridors(chat_id, "offer"))
    return bool(intro and intro.get("ok")) and bool(result and result.get("ok"))


def start_request(chat_id):
    intro = tg_send(chat_id, t(chat_id, "disclaimer"))
    drafts[chat_id] = {"kind": "request", "step": "corridor"}
    result = tg_send(chat_id, t(chat_id, "ask_corridor_request"), reply_markup=kb_corridors(chat_id, "request"))
    return bool(intro and intro.get("ok")) and bool(result and result.get("ok"))


def ask_next_step(chat_id):
    d = drafts.get(chat_id)
    if not d:
        return
    corridor = d.get("corridor")
    variants = CORRIDORS[corridor]["variants"] if corridor else None

    if d["step"] == "variant":
        if variants:
            tg_send(chat_id, t(chat_id, "ask_variant"), reply_markup=kb_variant(chat_id, d["kind"], corridor))
        else:
            d["step"] = "carry"
            ask_next_step(chat_id)

    elif d["step"] == "carry":
        key = "ask_carry_offer" if d["kind"] == "offer" else "ask_carry_request"
        tg_send(chat_id, t(chat_id, key), reply_markup=kb_carry(chat_id, d["kind"]))

    elif d["step"] == "capacity":
        if d["kind"] == "offer":
            tg_send(chat_id, t(chat_id, "ask_capacity"))
        else:
            d["step"] = "price"
            ask_next_step(chat_id)

    elif d["step"] == "price":
        if d["kind"] == "offer":
            tg_send(chat_id, t(chat_id, "ask_price"))
        else:
            d["step"] = "time"
            ask_next_step(chat_id)

    elif d["step"] == "time":
        tg_send(chat_id, t(chat_id, "ask_time"))

    elif d["step"] == "name":
        tg_send(chat_id, t(chat_id, "ask_name"))

    elif d["step"] == "share_phone":
        tg_send(chat_id, t(chat_id, "ask_share_phone"), reply_markup=kb_share_phone(chat_id))

    elif d["step"] == "confirm":
        publish_listing(chat_id)


def handle_draft_text(chat_id, text):
    d = drafts.get(chat_id)
    if not d:
        return False

    step = d["step"]

    if step == "capacity":
        if not text.strip().isdigit():
            tg_send(chat_id, t(chat_id, "capacity_error"))
            return True
        d["capacity"] = int(text.strip())
        d["step"] = "price"
        ask_next_step(chat_id)
        return True

    if step == "price":
        cleaned = text.strip().replace("лари", "").replace("₾", "").strip()
        if not cleaned.replace(".", "", 1).isdigit():
            tg_send(chat_id, t(chat_id, "price_error"))
            return True
        d["price"] = cleaned
        d["step"] = "time"
        ask_next_step(chat_id)
        return True

    if step == "time":
        d["time"] = text.strip()
        if str(chat_id) in users and users[str(chat_id)].get("phone"):
            d["step"] = "confirm"
            ask_next_step(chat_id)
        else:
            d["step"] = "name"
            ask_next_step(chat_id)
        return True

    if step == "name":
        d["pending_name"] = text.strip()
        d["step"] = "share_phone"
        ask_next_step(chat_id)
        return True

    if step == "share_phone":
        # человек написал текст вместо того, чтобы нажать кнопку "Поделиться номером"
        tg_send(chat_id, t(chat_id, "ask_share_phone"), reply_markup=kb_share_phone(chat_id))
        return True

    return False


def handle_shared_contact(chat_id, contact):
    d = drafts.get(chat_id)
    if not d or d.get("step") != "share_phone":
        return  # контакт пришёл не там, где ждали — игнорируем

    contact_owner_id = str(contact.get("user_id", ""))
    if contact_owner_id != str(chat_id):
        tg_send(chat_id, t(chat_id, "not_own_contact"), reply_markup=kb_share_phone(chat_id))
        return

    phone = contact.get("phone_number", "")
    name = d.pop("pending_name", "")
    users.setdefault(str(chat_id), {})["phone"] = phone
    if name:
        users[str(chat_id)]["name"] = name
    save_data()

    tg_call("sendMessage", {"chat_id": chat_id, "text": "✅", "reply_markup": {"remove_keyboard": True}})

    if d.get("kind") == "pending_claim":
        listing_id = d["listing_id"]
        drafts.pop(chat_id, None)
        handle_claim(listing_id, chat_id)
        return

    d["step"] = "confirm"
    ask_next_step(chat_id)


def publish_listing(chat_id):
    d = drafts.pop(chat_id, None)
    if not d:
        return

    listing_counter[0] += 1
    lid = str(listing_counter[0])
    corridor = d["corridor"]
    variant_label = None
    if CORRIDORS[corridor]["variants"] and d.get("variant") and d["variant"] != "any":
        variant_label = variant_name(chat_id, d["variant"])

    listing = {
        "id": lid,
        "kind": d["kind"],
        "owner_chat_id": str(chat_id),
        "corridor": corridor,
        "variant": d.get("variant"),
        "carry": d["carry"],
        "capacity": d.get("capacity"),
        "price": d.get("price"),
        "time": d.get("time"),
        "status": "open",
        "matched_with": None,
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    listings[lid] = listing
    save_data()

    icon = "🚗" if d["kind"] == "offer" else "🙋"
    text = (
        f"{icon} <b>#{lid} — {corridor_name(chat_id, corridor)}</b>"
        + (f" ({variant_label})" if variant_label else "") + "\n"
        f"{carry_name(chat_id, d['carry'])}\n"
        + (f"{d['capacity']}\n" if d.get("capacity") else "")
        + (f"{d['price']} ₾\n" if d.get("price") else "")
        + f"🕐 {d.get('time','—')}\n"
        f"━━━━━━━━━━━━━━━━"
    )

    if GROUP_CHAT_ID:
        posted = tg_send(GROUP_CHAT_ID, text, reply_markup=kb_claim(chat_id, lid))
        if posted and posted.get("ok"):
            listing["group_message_id"] = posted["result"]["message_id"]
            save_data()

    tg_send(chat_id, t(chat_id, "published"))
    notify_admin(f"🆕 Новое объявление #{lid} ({d['kind']}) от {contact_line(chat_id)}\n{text}")


# ─── МАТЧИНГ ────────────────────────────────────────────────────
def claim_listing(listing_id, claimant_chat_id):
    with lock:
        listing = listings.get(listing_id)
        if not listing:
            return None, "not_found"
        if listing["status"] != "open":
            return None, "taken"
        if listing["owner_chat_id"] == str(claimant_chat_id):
            return None, "own"
        listing["status"] = "matched"
        listing["matched_with"] = str(claimant_chat_id)
        save_data()
        return listing, None


def contact_line(chat_id):
    u = users.get(str(chat_id))
    if u and u.get("phone"):
        name = u.get("name", "").strip()
        return f"{name}, {u['phone']}" if name else u["phone"]
    return f"Telegram id {chat_id}"


def handle_claim(listing_id, claimant_chat_id):
    # телефон обязателен для отклика — без него человек не может участвовать в матче
    if not users.get(str(claimant_chat_id), {}).get("phone"):
        drafts[claimant_chat_id] = {"kind": "pending_claim", "listing_id": listing_id, "step": "name"}
        ask_next_step(claimant_chat_id)
        return

    listing, error = claim_listing(listing_id, claimant_chat_id)
    if error == "taken":
        tg_send(claimant_chat_id, t(claimant_chat_id, "claim_taken"))
        return
    if error == "own":
        tg_send(claimant_chat_id, t(claimant_chat_id, "claim_own"))
        return
    if error:
        return

    owner_id = listing["owner_chat_id"]
    driver_id = owner_id if listing["kind"] == "offer" else claimant_chat_id

    tg_send(owner_id, t(owner_id, "claim_owner_notice", id=listing_id, contact=contact_line(claimant_chat_id)))
    tg_send(claimant_chat_id, t(claimant_chat_id, "claim_claimant_notice", id=listing_id, contact=contact_line(owner_id)))

    # комиссию просим сразу при матче — у стороны, которая везёт (не у пассажира/отправителя)
    tg_send(driver_id, t(driver_id, "commission_now", sum=COMMISSION, account=payment_lines()),
            reply_markup=kb_done(driver_id, listing_id))

    if GROUP_CHAT_ID and listing.get("group_message_id"):
        tg_edit(GROUP_CHAT_ID, listing["group_message_id"], "🔒 —")

    notify_admin(f"🤝 Матч по #{listing_id}: {contact_line(owner_id)} ⇄ {contact_line(claimant_chat_id)}")


def handle_done(listing_id, chat_id):
    listing = listings.get(listing_id)
    if not listing:
        return
    if str(chat_id) not in (listing["owner_chat_id"], listing["matched_with"]):
        return
    if listing["status"] == "completed":
        return

    listing["status"] = "completed"
    save_data()

    tg_send(chat_id, t(chat_id, "commission_msg", sum=COMMISSION, account=payment_lines()))

    notify_admin(
        f"💰 Сделка #{listing_id} завершена. "
        f"{contact_line(listing['owner_chat_id'])} ⇄ {contact_line(listing['matched_with'])}. "
        f"Комиссия к оплате: {COMMISSION} лари."
    )


# ─── ОБРАБОТКА CALLBACK ────────────────────────────────────────
def handle_callback(callback):
    data = callback.get("data", "")
    chat_id = str(callback["from"]["id"])  # ID человека, который нажал кнопку — работает и в группе, и в личке
    callback_id = callback.get("id")

    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]
        users.setdefault(chat_id, {})["lang"] = lang
        save_data()
        action = pending_start_action.pop(chat_id, None)
        if action == "offer":
            start_offer(chat_id)
        elif action == "request":
            start_request(chat_id)
        elif action == "open":
            show_open_listings(chat_id)
        else:
            tg_send(chat_id, t(chat_id, "welcome"), reply_markup=kb_main(chat_id))
        answer_callback(callback_id)
        return

    if data == "start_offer":
        ok = start_offer(chat_id)
        if ok:
            answer_callback(callback_id)
        else:
            answer_callback(callback_id, "Откройте @karavan_ge_bot в личке и нажмите Start, затем нажмите кнопку ещё раз", show_alert=True)
    elif data == "start_request":
        ok = start_request(chat_id)
        if ok:
            answer_callback(callback_id)
        else:
            answer_callback(callback_id, "Откройте @karavan_ge_bot в личке и нажмите Start, затем нажмите кнопку ещё раз", show_alert=True)
    elif data == "show_open":
        sent = show_open_listings(chat_id)
        if sent and sent.get("ok"):
            answer_callback(callback_id)
        else:
            answer_callback(callback_id, "Откройте @karavan_ge_bot в личке и нажмите Start, затем нажмите кнопку ещё раз", show_alert=True)
    elif data == "my_listings":
        mine = [l for l in listings.values() if l["owner_chat_id"] == chat_id or l.get("matched_with") == chat_id]
        if not mine:
            tg_send(chat_id, t(chat_id, "my_listings_empty"))
        else:
            msg = t(chat_id, "my_listings_header") + "\n━━━━━━━━━━━━━━━━\n"
            for l in mine:
                msg += f"#{l['id']} | {corridor_name(chat_id, l['corridor'])} | {l['status']}\n"
            tg_send(chat_id, msg)
        answer_callback(callback_id)
    elif data.startswith("offer_corr_") or data.startswith("request_corr_"):
        _, _, corridor_key = data.partition("_corr_")
        d = drafts.get(chat_id)
        if d:
            d["corridor"] = corridor_key
            d["step"] = "variant"
            ask_next_step(chat_id)
        answer_callback(callback_id)
    elif data.startswith("offer_var_") or data.startswith("request_var_"):
        _, _, variant_key = data.partition("_var_")
        d = drafts.get(chat_id)
        if d:
            d["variant"] = variant_key
            d["step"] = "carry"
            ask_next_step(chat_id)
        answer_callback(callback_id)
    elif data.startswith("offer_carry_") or data.startswith("request_carry_"):
        _, _, carry_key = data.partition("_carry_")
        d = drafts.get(chat_id)
        if d:
            d["carry"] = carry_key
            d["step"] = "capacity"
            ask_next_step(chat_id)
        answer_callback(callback_id)
    elif data.startswith("claim_"):
        handle_claim(data.split("_", 1)[1], chat_id)
        answer_callback(callback_id)
    elif data.startswith("done_"):
        handle_done(data.split("_", 1)[1], chat_id)
        answer_callback(callback_id)
    else:
        answer_callback(callback_id)


# ─── ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ──────────────────────────────
def handle_message(message):
    chat_id = str(message["chat"]["id"])
    text = message.get("text", "")

    contact = message.get("contact")
    if contact is not None:
        handle_shared_contact(chat_id, contact)
        return

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        payload = parts[1].strip() if len(parts) > 1 else None
        has_lang = str(chat_id) in users and "lang" in users.get(str(chat_id), {})

        if not has_lang:
            if payload:
                pending_start_action[chat_id] = payload
            tg_send(chat_id, T["choose_lang"]["ru"] + " / " + T["choose_lang"]["ka"] + " / " + T["choose_lang"]["hy"], reply_markup=kb_lang())
            return

        if payload == "offer":
            start_offer(chat_id)
        elif payload == "request":
            start_request(chat_id)
        elif payload == "open":
            show_open_listings(chat_id)
        else:
            tg_send(chat_id, t(chat_id, "welcome"), reply_markup=kb_main(chat_id))
        return

    if text == "/lang":
        tg_send(chat_id, T["choose_lang"]["ru"] + " / " + T["choose_lang"]["ka"] + " / " + T["choose_lang"]["hy"], reply_markup=kb_lang())
        return

    if text == "/myid":
        tg_send(chat_id, f"chat_id: <code>{chat_id}</code>")
        return

    if text == "/post" and ADMIN_CHAT_ID and chat_id == str(ADMIN_CHAT_ID):
        if not GROUP_CHAT_ID:
            tg_send(chat_id, "⚠️ GROUP_CHAT_ID не задан в переменных Railway.")
            return
        group_text = (
            "🐫 <b>Karavan</b>\n\n"
            "🇷🇺 Хотите поехать/отправить посылку или предложить свои услуги как водитель? Нажмите кнопку ниже — бот проведёт вас через все шаги в личных сообщениях.\n\n"
            "🇬🇪 გსურთ წასვლა/გზავნილის გაგზავნა თუ მძღოლის მომსახურების შეთავაზება? დააჭირეთ ღილაკს — ბოტი გაგატარებთ ყველა ეტაპზე პირად შეტყობინებებში.\n\n"
            "🇦🇲 Ցանկանու՞մ եք գնալ/ուղարկել ծանրոց, թե՞ առաջարկել վարորդի ծառայություն։ Սեղմեք կոճակը ներքևում — բոտը կուղեկցի Ձեզ բոլոր քայլերով անձնական հաղորդագրություններում։"
        )
        posted = tg_send(GROUP_CHAT_ID, group_text, reply_markup=kb_group_start())
        if posted and posted.get("ok"):
            tg_send(chat_id, "✅ Плашка опубликована в группе. Рекомендую закрепить её вручную (зажать сообщение → Закрепить).")
        else:
            tg_send(chat_id, "⚠️ Не получилось опубликовать — проверь, что бот всё ещё состоит в группе и GROUP_CHAT_ID верный.")
        return

    if handle_draft_text(chat_id, text):
        return

    tg_send(chat_id, t(chat_id, "unknown"))


# ─── HTTP-СЕРВЕР ────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Karavan bot is running!")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        try:
            data = json.loads(body)
        except Exception:
            self.wfile.write(json.dumps({"ok": False}).encode())
            return

        if self.path == "/webhook":
            if "callback_query" in data:
                handle_callback(data["callback_query"])
            elif "message" in data:
                handle_message(data["message"])
            self.wfile.write(json.dumps({"ok": True}).encode())
        else:
            self.wfile.write(json.dumps({"ok": False, "error": "unknown path"}).encode())


def set_webhook(server_url):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={urllib.parse.quote(server_url + '/webhook')}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            log.info(f"Webhook установлен: {json.loads(r.read())}")
    except Exception as e:
        log.error(f"Ошибка webhook: {e}")


if __name__ == "__main__":
    load_data()
    server_url = os.environ.get("SERVER_URL", "")
    if server_url and BOT_TOKEN:
        set_webhook(server_url)
    log.info(f"Бот запущен на порту {PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
