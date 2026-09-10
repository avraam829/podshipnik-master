"""
Telegram Bot — Магазин подшипников
Каталог · Поиск · Корзина · Оформление · История заказов
"""

import os
import sys
import logging
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

# ── Django ──
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from asgiref.sync import sync_to_async
from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce

from catalog.models import (
    Category, Product,
    TelegramOrder, TelegramOrderItem,
)

from telegram import (
    Update,
    InlineKeyboardButton as Btn,
    InlineKeyboardMarkup as Markup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode

# ── Config ──
TOKEN = os.getenv("TG_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("TG_ADMIN_CHAT_ID")
PER_PAGE = 6

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO
)
log = logging.getLogger(__name__)

REPLY_KB = ReplyKeyboardMarkup(
    [["🔍 Поиск", "📂 Каталог"], ["🛒 Корзина", "📦 Мои заказы"]],
    resize_keyboard=True,
)


# ════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════

def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_price(price):
    if price and price > 0:
        return f"{price:,.2f} ₽".replace(",", " ")
    return "По запросу"


def get_cart(ctx) -> dict:
    if "cart" not in ctx.user_data:
        ctx.user_data["cart"] = {}
    return ctx.user_data["cart"]


def cart_total_qty(ctx):
    return sum(get_cart(ctx).values())


async def reply(update, text, markup=None):
    """Edit if callback, send if message."""
    kw = dict(parse_mode=ParseMode.HTML, reply_markup=markup)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, **kw)
        except Exception:
            await update.callback_query.message.reply_text(text, **kw)
    elif update.message:
        await update.message.reply_text(text, **kw)


async def notify_admin(app, order_info: str):
    if ADMIN_CHAT_ID:
        try:
            await app.bot.send_message(
                chat_id=int(ADMIN_CHAT_ID),
                text=order_info,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            log.error(f"Admin notify failed: {e}")


# ════════════════════════════════════════════════
#  DB LAYER  (sync → async)
# ════════════════════════════════════════════════

@sync_to_async
def db_top_categories():
    return list(
        Category.objects.filter(parent__isnull=True)
        .order_by("name")
        .values("id", "name")
    )


@sync_to_async
def db_category(cat_id):
    try:
        c = Category.objects.select_related("parent").get(id=cat_id)
    except Category.DoesNotExist:
        return None, [], 0
    children = list(c.children.order_by("name").values("id", "name"))
    ids = [c.id] + [x["id"] for x in children]
    grand = list(
        Category.objects.filter(parent_id__in=[x["id"] for x in children])
        .values_list("id", flat=True)
    )
    ids += grand
    cnt = Product.objects.filter(category_id__in=ids).count()
    info = {
        "id": c.id, "name": c.name,
        "parent_id": c.parent_id,
        "parent_name": c.parent.name if c.parent else None,
    }
    return info, children, cnt


@sync_to_async
def db_products(cat_id, page=1):
    ids = [cat_id]
    ch = list(Category.objects.filter(parent_id=cat_id).values_list("id", flat=True))
    ids += ch
    if ch:
        ids += list(Category.objects.filter(parent_id__in=ch).values_list("id", flat=True))

    qs = (
        Product.objects.filter(category_id__in=ids)
        .annotate(total_stock=Coalesce(Sum("stocks__amount"), Value(0)))
        .order_by("designation")
    )
    total = qs.count()
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, pages))
    items = []
    for p in qs[(page - 1) * PER_PAGE: page * PER_PAGE]:
        items.append({
            "id": p.id,
            "designation": p.designation,
            "manufacturer": p.manufacturer or "",
            "price": p.price,
            "stock": p.total_stock,
        })
    return items, total, page, pages


@sync_to_async
def db_search(query, page=1):
    qs = (
        Product.objects.filter(
            Q(designation__icontains=query)
            | Q(manufacturer__icontains=query)
            | Q(code__icontains=query)
        )
        .annotate(total_stock=Coalesce(Sum("stocks__amount"), Value(0)))
        .order_by("designation")
    )
    total = qs.count()
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, pages))
    items = []
    for p in qs[(page - 1) * PER_PAGE: page * PER_PAGE]:
        items.append({
            "id": p.id,
            "designation": p.designation,
            "manufacturer": p.manufacturer or "",
            "price": p.price,
            "stock": p.total_stock,
        })
    return items, total, page, pages


@sync_to_async
def db_product(pid):
    try:
        p = Product.objects.select_related("category", "category__parent").get(id=pid)
    except Product.DoesNotExist:
        return None
    stock = p.stocks.aggregate(t=Sum("amount"))["t"] or 0
    warehouses = list(
        p.stocks.select_related("warehouse")
        .filter(amount__gt=0)
        .values_list("warehouse__name", "amount")
    )
    prices = {x.price_type: x.price for x in p.prices.all()}
    return {
        "id": p.id, "code": p.code,
        "designation": p.designation,
        "manufacturer": p.manufacturer or "",
        "description": (p.description or "")[:800],
        "price": p.price,
        "retail": prices.get("retail"),
        "wholesale": prices.get("wholesale"),
        "weight": p.weight,
        "length": p.length, "width": p.width, "height": p.height,
        "stock": stock, "warehouses": warehouses,
        "cat_name": p.category.name if p.category else "",
        "cat_id": p.category_id,
    }


@sync_to_async
def db_products_by_ids(ids):
    out = {}
    for p in Product.objects.filter(id__in=ids):
        out[p.id] = {
            "id": p.id,
            "designation": p.designation,
            "manufacturer": p.manufacturer or "",
            "price": p.price,
        }
    return out


@sync_to_async
def db_create_order(uid, uname, name, phone, address, comment, cart):
    order = TelegramOrder.objects.create(
        telegram_user_id=uid,
        telegram_username=uname or "",
        customer_name=name, phone=phone,
        address=address, comment=comment,
    )
    total = Decimal("0")
    for pid, qty in cart.items():
        try:
            p = Product.objects.get(id=int(pid))
            pr = p.price or Decimal("0")
            TelegramOrderItem.objects.create(
                order=order, product=p,
                designation=p.designation,
                price=pr, quantity=qty,
            )
            total += pr * qty
        except Product.DoesNotExist:
            pass
    order.total = total
    order.save()
    return {"id": order.id, "total": order.total}


@sync_to_async
def db_orders(uid):
    out = []
    for o in TelegramOrder.objects.filter(telegram_user_id=uid).order_by("-created_at")[:20]:
        out.append({
            "id": o.id,
            "total": o.total,
            "status": o.get_status_display(),
            "date": o.created_at.strftime("%d.%m.%Y %H:%M"),
            "n": o.items.count(),
        })
    return out


@sync_to_async
def db_order(oid, uid):
    try:
        o = TelegramOrder.objects.get(id=oid, telegram_user_id=uid)
    except TelegramOrder.DoesNotExist:
        return None, []
    items = [
        {
            "name": i.designation,
            "price": i.price,
            "qty": i.quantity,
            "sub": i.price * i.quantity,
        }
        for i in o.items.all()
    ]
    return {
        "id": o.id,
        "name": o.customer_name, "phone": o.phone,
        "address": o.address, "comment": o.comment,
        "total": o.total,
        "status": o.get_status_display(),
        "date": o.created_at.strftime("%d.%m.%Y %H:%M"),
    }, items


# ════════════════════════════════════════════════
#  DISPLAY FUNCTIONS
# ════════════════════════════════════════════════

async def show_main(update, ctx):
    n = cart_total_qty(ctx)
    cart_lbl = f"🛒 Корзина ({n})" if n else "🛒 Корзина"
    kb = [
        [Btn("📂 Каталог", callback_data="cats"),
         Btn("🔍 Поиск", callback_data="search")],
        [Btn(cart_lbl, callback_data="cart"),
         Btn("📦 Мои заказы", callback_data="orders")],
        [Btn("ℹ️ О компании", callback_data="about")],
    ]
    await reply(update,
        "🏭 <b>Demo Oil — Подшипники и комплектующие</b>\n\n"
        "Выберите действие 👇",
        Markup(kb),
    )


async def show_categories(update, ctx):
    cats = await db_top_categories()
    if not cats:
        await reply(update, "Каталог пуст.", Markup([[Btn("🔙 Меню", callback_data="main")]]))
        return
    kb = []
    for c in cats:
        kb.append([Btn(f"📁 {c['name']}", callback_data=f"cat:{c['id']}")])
    kb.append([Btn("🔙 Меню", callback_data="main")])
    await reply(update, "📂 <b>Каталог</b>\n\nВыберите категорию:", Markup(kb))


async def show_category(update, ctx, cat_id):
    info, children, cnt = await db_category(cat_id)
    if not info:
        await reply(update, "Категория не найдена.",
                    Markup([[Btn("🔙 Назад", callback_data="cats")]]))
        return

    text = f"📁 <b>{esc(info['name'])}</b>\nТоваров: {cnt}\n"
    kb = []

    if children:
        text += "\nПодкатегории:"
        for ch in children:
            kb.append([Btn(f"📂 {ch['name']}", callback_data=f"cat:{ch['id']}")])

    # Кнопка «Показать все товары»
    if cnt > 0:
        kb.append([Btn(f"📦 Все товары ({cnt})", callback_data=f"pl:{cat_id}:1")])

    back = f"cat:{info['parent_id']}" if info["parent_id"] else "cats"
    kb.append([Btn("🔙 Назад", callback_data=back)])
    await reply(update, text, Markup(kb))


async def show_product_list(update, ctx, cat_id, page):
    items, total, page, pages = await db_products(cat_id, page)
    ctx.user_data["nav"] = {"src": "cat", "cat": cat_id, "page": page}

    if not items:
        await reply(update, "Товаров не найдено.",
                    Markup([[Btn("🔙 Назад", callback_data=f"cat:{cat_id}")]]))
        return

    text = f"📦 <b>Товары</b>  (стр. {page}/{pages}, всего {total})\n\n"
    kb = []
    nums = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

    num_row = []
    for i, p in enumerate(items):
        stock = "✅" if p["stock"] > 0 else "📦"
        text += (
            f"{nums[i]} <b>{esc(p['designation'])}</b>"
            f"{' · ' + esc(p['manufacturer']) if p['manufacturer'] else ''}\n"
            f"   {stock} {fmt_price(p['price'])}"
            f"{' · ' + str(p['stock']) + ' шт.' if p['stock'] > 0 else ' · Под заказ'}\n\n"
        )
        num_row.append(Btn(nums[i], callback_data=f"p:{p['id']}"))

    kb.append(num_row)

    # Пагинация
    nav = []
    if page > 1:
        nav.append(Btn("◀️", callback_data=f"pl:{cat_id}:{page - 1}"))
    nav.append(Btn(f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        nav.append(Btn("▶️", callback_data=f"pl:{cat_id}:{page + 1}"))
    if len(nav) > 1:
        kb.append(nav)

    kb.append([Btn("🔙 К категории", callback_data=f"cat:{cat_id}")])
    await reply(update, text, Markup(kb))


async def show_search_results(update, ctx, query, page):
    items, total, page, pages = await db_search(query, page)
    ctx.user_data["nav"] = {"src": "search", "q": query, "page": page}
    ctx.user_data["search_q"] = query

    if not items:
        text = f'🔍 По запросу «<b>{esc(query)}</b>» ничего не найдено.'
        kb = [[Btn("🔍 Новый поиск", callback_data="search")],
              [Btn("🔙 Меню", callback_data="main")]]
        await reply(update, text, Markup(kb))
        return

    text = f'🔍 Результаты: «<b>{esc(query)}</b>»  (стр. {page}/{pages}, найдено {total})\n\n'
    kb = []
    nums = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

    num_row = []
    for i, p in enumerate(items):
        stock = "✅" if p["stock"] > 0 else "📦"
        text += (
            f"{nums[i]} <b>{esc(p['designation'])}</b>"
            f"{' · ' + esc(p['manufacturer']) if p['manufacturer'] else ''}\n"
            f"   {stock} {fmt_price(p['price'])}\n\n"
        )
        num_row.append(Btn(nums[i], callback_data=f"p:{p['id']}"))

    kb.append(num_row)

    nav = []
    if page > 1:
        nav.append(Btn("◀️", callback_data=f"sp:{page - 1}"))
    nav.append(Btn(f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        nav.append(Btn("▶️", callback_data=f"sp:{page + 1}"))
    if len(nav) > 1:
        kb.append(nav)

    kb.append([Btn("🔍 Новый поиск", callback_data="search"),
               Btn("🔙 Меню", callback_data="main")])
    await reply(update, text, Markup(kb))


async def show_product(update, ctx, pid):
    p = await db_product(pid)
    if not p:
        await reply(update, "Товар не найден.",
                    Markup([[Btn("🔙 Назад", callback_data="main")]]))
        return

    stock_icon = "✅" if p["stock"] > 0 else "📦"
    stock_text = f'{p["stock"]} шт. в наличии' if p["stock"] > 0 else "Под заказ"

    text = f'🔹 <b>{esc(p["designation"])}</b>\n'
    if p["manufacturer"]:
        text += f'Производитель: {esc(p["manufacturer"])}\n'
    if p["cat_name"]:
        text += f'Категория: {esc(p["cat_name"])}\n'
    text += f'Артикул: <code>{esc(p["code"])}</code>\n\n'

    text += f'{stock_icon} {stock_text}\n'
    if p["warehouses"]:
        for wh, amt in p["warehouses"]:
            text += f'   📍 {esc(wh)}: {amt} шт.\n'

    text += f'\n💰 <b>{fmt_price(p["price"])}</b>\n'
    if p["wholesale"] and p["wholesale"] != p["price"]:
        text += f'Опт: {fmt_price(p["wholesale"])}\n'

    # Габариты
    dims = []
    if p["weight"]:
        dims.append(f'Вес: {p["weight"]} кг')
    if p["length"] or p["width"] or p["height"]:
        d = f'{p["length"] or "—"}×{p["width"] or "—"}×{p["height"] or "—"} мм'
        dims.append(f'Размеры: {d}')
    if dims:
        text += "\n" + "\n".join(dims) + "\n"

    if p["description"]:
        desc = esc(p["description"][:400])
        if len(p["description"]) > 400:
            desc += "…"
        text += f"\n📝 {desc}\n"

    # Кнопки
    cart = get_cart(ctx)
    in_cart = cart.get(str(pid), 0)
    cart_btn_text = f"🛒 В корзину (уже {in_cart})" if in_cart else "🛒 В корзину"

    kb = [
        [Btn("➖", callback_data=f"aq:{pid}:-1"),
         Btn(cart_btn_text, callback_data=f"aq:{pid}:1"),
         Btn("➕", callback_data=f"aq:{pid}:5")],
    ]

    # Кнопка «назад»
    nav = ctx.user_data.get("nav", {})
    if nav.get("src") == "cat":
        kb.append([Btn("🔙 К списку", callback_data=f'pl:{nav["cat"]}:{nav["page"]}')])
    elif nav.get("src") == "search":
        kb.append([Btn("🔙 К результатам", callback_data=f'sp:{nav["page"]}')])
    else:
        kb.append([Btn("🔙 Меню", callback_data="main")])

    if in_cart:
        kb.append([Btn(f"🛒 Перейти в корзину ({cart_total_qty(ctx)})", callback_data="cart")])

    await reply(update, text, Markup(kb))


async def show_cart(update, ctx):
    cart = get_cart(ctx)

    if not cart:
        kb = [
            [Btn("📂 Каталог", callback_data="cats"),
             Btn("🔍 Поиск", callback_data="search")],
            [Btn("🔙 Меню", callback_data="main")],
        ]
        await reply(update, "🛒 <b>Корзина пуста</b>\n\nДобавьте товары из каталога.", Markup(kb))
        return

    products = await db_products_by_ids([int(x) for x in cart.keys()])

    text = "🛒 <b>Корзина</b>\n\n"
    kb = []
    total = Decimal("0")
    valid_items = []

    for pid_str, qty in list(cart.items()):
        p = products.get(int(pid_str))
        if not p:
            del cart[pid_str]
            continue
        valid_items.append((pid_str, qty, p))
        price = p["price"] or Decimal("0")
        sub = price * qty
        total += sub

        text += f'• <b>{esc(p["designation"])}</b>'
        if p["manufacturer"]:
            text += f' ({esc(p["manufacturer"])})'
        text += f'\n  {fmt_price(price)} × {qty} шт.'
        if price > 0:
            text += f' = {fmt_price(sub)}'
        text += "\n\n"

        kb.append([
            Btn("➖", callback_data=f"cm:{pid_str}"),
            Btn(f'{qty} шт.', callback_data=f"p:{pid_str}"),
            Btn("➕", callback_data=f"cp:{pid_str}"),
            Btn("🗑", callback_data=f"cd:{pid_str}"),
        ])

    text += f'💰 <b>Итого: {fmt_price(total)}</b>'

    kb.append([Btn("🗑 Очистить", callback_data="cc")])
    kb.append([Btn("✅ Оформить заказ", callback_data="co")])
    kb.append([Btn("🔙 Меню", callback_data="main")])

    await reply(update, text, Markup(kb))


async def show_orders_list(update, ctx):
    uid = update.callback_query.from_user.id if update.callback_query else update.message.from_user.id
    orders = await db_orders(uid)

    if not orders:
        await reply(update, "📦 <b>Заказов пока нет</b>\n\nОформите первый заказ!",
                    Markup([[Btn("🔙 Меню", callback_data="main")]]))
        return

    text = "📦 <b>Мои заказы</b>\n\n"
    kb = []
    for o in orders:
        text += (
            f'#{o["id"]}  ·  {o["date"]}\n'
            f'{o["n"]} поз.  ·  {fmt_price(o["total"])}  ·  {o["status"]}\n\n'
        )
        kb.append([Btn(f'📋 Заказ #{o["id"]}', callback_data=f'o:{o["id"]}')])

    kb.append([Btn("🔙 Меню", callback_data="main")])
    await reply(update, text, Markup(kb))


async def show_order_detail(update, ctx, oid):
    uid = update.callback_query.from_user.id
    order, items = await db_order(oid, uid)

    if not order:
        await reply(update, "Заказ не найден.",
                    Markup([[Btn("🔙 Назад", callback_data="orders")]]))
        return

    text = (
        f'📋 <b>Заказ #{order["id"]}</b>\n'
        f'Дата: {order["date"]}\n'
        f'Статус: <b>{order["status"]}</b>\n\n'
        f'👤 {esc(order["name"])}\n'
        f'📱 {esc(order["phone"])}\n'
    )
    if order["address"]:
        text += f'📍 {esc(order["address"])}\n'
    if order["comment"]:
        text += f'💬 {esc(order["comment"])}\n'

    text += "\n<b>Позиции:</b>\n"
    for it in items:
        text += f'• {esc(it["name"])} × {it["qty"]} = {fmt_price(it["sub"])}\n'

    text += f'\n💰 <b>Итого: {fmt_price(order["total"])}</b>'

    await reply(update, text, Markup([[Btn("🔙 К заказам", callback_data="orders")]]))


async def show_about(update, ctx):
    text = (
        "🏭 <b>Demo Oil</b>\n\n"
        "Подшипники и промышленные комплектующие для текущего "
        "и планового ремонта оборудования.\n\n"
        "📍 Склад: г. Владимир\n"
        "📱 Телефон: +7 (XXX) XXX-XX-XX\n"
        "📧 Email: info@demo-oil.ru\n"
        "🌐 Сайт: demo-oil.ru\n\n"
        "🕐 Пн–Пт: 9:00–18:00\n\n"
        "✅ 10 000+ позиций на складе\n"
        "✅ Гарантия качества\n"
        "✅ Доставка по всей России\n"
        "✅ Техническая поддержка"
    )
    await reply(update, text, Markup([[Btn("🔙 Меню", callback_data="main")]]))


# ════════════════════════════════════════════════
#  CHECKOUT FLOW
# ════════════════════════════════════════════════

async def checkout_start(update, ctx):
    cart = get_cart(ctx)
    if not cart:
        if update.callback_query:
            await update.callback_query.answer("Корзина пуста!", show_alert=True)
        return

    ctx.user_data["state"] = "order_name"
    ctx.user_data["order"] = {}

    text = (
        "📋 <b>Оформление заказа</b>\n\n"
        "Шаг 1/4\n"
        "Введите ваше <b>имя</b> (ФИО или название организации):"
    )
    kb = [[Btn("❌ Отменить", callback_data="cancel_co")]]

    if update.callback_query:
        await update.callback_query.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=Markup(kb)
        )
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML, reply_markup=Markup(kb)
        )


async def process_order_step(update, ctx):
    """Handles text input during checkout."""
    state = ctx.user_data.get("state", "")
    text = update.message.text.strip()
    order = ctx.user_data.get("order", {})

    if state == "order_name":
        order["name"] = text[:200]
        ctx.user_data["state"] = "order_phone"
        await update.message.reply_text(
            "📋 <b>Оформление заказа</b>\n\n"
            "Шаг 2/4\n"
            "Введите <b>номер телефона</b>:",
            parse_mode=ParseMode.HTML,
            reply_markup=Markup([[Btn("❌ Отменить", callback_data="cancel_co")]]),
        )

    elif state == "order_phone":
        order["phone"] = text[:50]
        ctx.user_data["state"] = "order_address"
        await update.message.reply_text(
            "📋 <b>Оформление заказа</b>\n\n"
            "Шаг 3/4\n"
            'Введите <b>адрес доставки</b>\n(или напишите "самовывоз"):',
            parse_mode=ParseMode.HTML,
            reply_markup=Markup([[Btn("❌ Отменить", callback_data="cancel_co")]]),
        )

    elif state == "order_address":
        order["address"] = text[:500]
        ctx.user_data["state"] = "order_comment"
        await update.message.reply_text(
            "📋 <b>Оформление заказа</b>\n\n"
            "Шаг 4/4\n"
            "Добавьте <b>комментарий</b> к заказу (необязательно):",
            parse_mode=ParseMode.HTML,
            reply_markup=Markup([
                [Btn("⏭ Пропустить", callback_data="skip_cmt")],
                [Btn("❌ Отменить", callback_data="cancel_co")],
            ]),
        )

    elif state == "order_comment":
        if text.lower() not in ("нет", "-", "пропустить", "не"):
            order["comment"] = text[:500]
        else:
            order["comment"] = ""
        ctx.user_data["state"] = "order_confirm"
        await show_order_confirm(update, ctx)

    ctx.user_data["order"] = order


async def show_order_confirm(update, ctx):
    order = ctx.user_data.get("order", {})
    cart = get_cart(ctx)
    products = await db_products_by_ids([int(x) for x in cart.keys()])

    text = "📋 <b>Подтверждение заказа</b>\n\n"
    text += f'👤 {esc(order.get("name", ""))}\n'
    text += f'📱 {esc(order.get("phone", ""))}\n'
    text += f'📍 {esc(order.get("address", ""))}\n'
    if order.get("comment"):
        text += f'💬 {esc(order["comment"])}\n'

    text += "\n<b>Товары:</b>\n"
    total = Decimal("0")
    for pid_str, qty in cart.items():
        p = products.get(int(pid_str))
        if not p:
            continue
        price = p["price"] or Decimal("0")
        sub = price * qty
        total += sub
        text += f'• {esc(p["designation"])} × {qty} = {fmt_price(sub)}\n'

    text += f'\n💰 <b>Итого: {fmt_price(total)}</b>\n\n'
    text += "Всё верно?"

    kb = [
        [Btn("✅ Подтвердить", callback_data="confirm")],
        [Btn("❌ Отменить", callback_data="cancel_co")],
    ]

    msg = update.message if update.message else update.callback_query.message
    await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=Markup(kb))


async def confirm_order(update, ctx):
    query = update.callback_query
    user = query.from_user
    order = ctx.user_data.get("order", {})
    cart = get_cart(ctx)

    if not cart:
        await query.answer("Корзина пуста!", show_alert=True)
        return

    result = await db_create_order(
        uid=user.id,
        uname=user.username,
        name=order.get("name", ""),
        phone=order.get("phone", ""),
        address=order.get("address", ""),
        comment=order.get("comment", ""),
        cart=cart,
    )

    # Очищаем корзину и состояние
    ctx.user_data["cart"] = {}
    ctx.user_data["state"] = None
    ctx.user_data["order"] = {}

    text = (
        f'🎉 <b>Заказ #{result["id"]} оформлен!</b>\n\n'
        f'💰 Сумма: {fmt_price(result["total"])}\n\n'
        f"Мы свяжемся с вами для подтверждения.\n"
        f"Спасибо за заказ! 🙏"
    )
    kb = [
        [Btn("📦 Мои заказы", callback_data="orders")],
        [Btn("🔙 Меню", callback_data="main")],
    ]
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=Markup(kb))

    # Уведомление админу
    admin_text = (
        f'🔔 <b>Новый заказ #{result["id"]}</b>\n\n'
        f'👤 {esc(order.get("name", ""))}\n'
        f'📱 {esc(order.get("phone", ""))}\n'
        f'📍 {esc(order.get("address", ""))}\n'
        f'💬 {esc(order.get("comment", ""))}\n'
        f'💰 Сумма: {fmt_price(result["total"])}\n'
        f'TG: @{user.username or "—"} (ID: {user.id})'
    )
    await notify_admin(ctx.application, admin_text)


# ════════════════════════════════════════════════
#  HANDLERS
# ════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["state"] = None
    if "cart" not in ctx.user_data:
        ctx.user_data["cart"] = {}
    await update.message.reply_text(
        "🏭 <b>Demo Oil — Подшипники и комплектующие</b>\n\n"
        "Добро пожаловать! Я помогу найти и заказать нужные подшипники.\n\n"
        "Используйте кнопки ниже 👇",
        parse_mode=ParseMode.HTML,
        reply_markup=REPLY_KB,
    )
    await show_main(update, ctx)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Как пользоваться ботом:</b>\n\n"
        "🔍 Просто напишите маркировку подшипника — бот найдёт его\n"
        "📂 Нажмите «Каталог» для навигации по категориям\n"
        "🛒 Добавляйте товары в корзину и оформляйте заказ\n\n"
        "Команды:\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/cancel — отмена текущего действия",
        parse_mode=ParseMode.HTML,
    )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["state"] = None
    ctx.user_data.pop("order", None)
    await update.message.reply_text("Действие отменено.", reply_markup=REPLY_KB)
    await show_main(update, ctx)


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # Безопасное получение state (может быть None)
    state = ctx.user_data.get("state") or ""

    # Если пользователь в процессе оформления и нажал кнопку навигации
    if data not in ("cancel_co", "skip_cmt", "confirm") and \
       state.startswith("order_"):
        await query.answer(
            "Сначала завершите оформление или нажмите /cancel",
            show_alert=True,
        )
        return

    await query.answer()

    try:
        if data == "main":
            await show_main(update, ctx)

        elif data == "cats":
            await show_categories(update, ctx)

        elif data.startswith("cat:"):
            await show_category(update, ctx, int(data.split(":")[1]))

        elif data.startswith("pl:"):
            parts = data.split(":")
            await show_product_list(update, ctx, int(parts[1]), int(parts[2]))

        elif data.startswith("p:"):
            await show_product(update, ctx, int(data.split(":")[1]))

        elif data.startswith("aq:"):
            parts = data.split(":")
            pid, delta = str(parts[1]), int(parts[2])
            cart = get_cart(ctx)
            current = cart.get(pid, 0)
            new_qty = max(0, current + delta)
            if new_qty > 0:
                cart[pid] = new_qty
                await query.answer(
                    f"✅ {cart[pid]} шт. в корзине", show_alert=False
                )
            elif pid in cart:
                del cart[pid]
                await query.answer("Удалено из корзины", show_alert=False)
            await show_product(update, ctx, int(parts[1]))

        elif data == "cart":
            await show_cart(update, ctx)

        elif data.startswith("cp:"):
            pid = data.split(":")[1]
            cart = get_cart(ctx)
            cart[pid] = cart.get(pid, 0) + 1
            await show_cart(update, ctx)

        elif data.startswith("cm:"):
            pid = data.split(":")[1]
            cart = get_cart(ctx)
            if pid in cart:
                cart[pid] -= 1
                if cart[pid] <= 0:
                    del cart[pid]
            await show_cart(update, ctx)

        elif data.startswith("cd:"):
            pid = data.split(":")[1]
            cart = get_cart(ctx)
            cart.pop(pid, None)
            await query.answer("Удалено")
            await show_cart(update, ctx)

        elif data == "cc":
            ctx.user_data["cart"] = {}
            await query.answer("Корзина очищена")
            await show_cart(update, ctx)

        elif data == "co":
            await checkout_start(update, ctx)

        elif data == "orders":
            await show_orders_list(update, ctx)

        elif data.startswith("o:"):
            await show_order_detail(update, ctx, int(data.split(":")[1]))

        elif data == "about":
            await show_about(update, ctx)

        elif data == "search":
            ctx.user_data["state"] = "search"
            await query.message.reply_text(
                "🔍 Введите маркировку, производителя или артикул:"
            )

        elif data.startswith("sp:"):
            q = ctx.user_data.get("search_q", "")
            if q:
                await show_search_results(
                    update, ctx, q, int(data.split(":")[1])
                )

        elif data == "skip_cmt":
            ctx.user_data.setdefault("order", {})["comment"] = ""
            ctx.user_data["state"] = "order_confirm"
            await show_order_confirm(update, ctx)

        elif data == "confirm":
            await confirm_order(update, ctx)

        elif data == "cancel_co":
            ctx.user_data["state"] = None
            ctx.user_data.pop("order", None)
            await query.answer("Оформление отменено")
            await show_main(update, ctx)

        elif data == "noop":
            pass

    except Exception as e:
        log.error(f"Callback error [{data}]: {e}", exc_info=True)
        try:
            await query.answer(
                "Произошла ошибка. Нажмите /start", show_alert=True
            )
        except Exception:
            pass

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return

    # Безопасное получение state
    state = ctx.user_data.get("state") or ""

    # Reply-keyboard кнопки
    if text == "📂 Каталог":
        ctx.user_data["state"] = None
        await show_categories(update, ctx)
        return

    if text == "🔍 Поиск":
        ctx.user_data["state"] = "search"
        await update.message.reply_text(
            "🔍 Введите маркировку, производителя или артикул:"
        )
        return

    if text == "🛒 Корзина":
        ctx.user_data["state"] = None
        await show_cart(update, ctx)
        return

    if text == "📦 Мои заказы":
        ctx.user_data["state"] = None
        await show_orders_list(update, ctx)
        return

    # Checkout flow
    if state.startswith("order_"):
        await process_order_step(update, ctx)
        return

    # Search (любой текст = поиск)
    ctx.user_data["state"] = None
    query = text[:100]
    await show_search_results(update, ctx, query, 1)

# ════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════

def main():
    if not TOKEN:
        log.error(
            "TG_BOT_TOKEN не найден! Создайте .env и укажите токен."
        )
        return

    app = Application.builder().token(TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # Inline-кнопки
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Текстовые сообщения
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message
    ))

    log.info("🤖 Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()