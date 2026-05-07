"""
Строительный бот для группового чата Telegram
Управление конструктивами, ежедневные отчёты, учёт людей и объёмов работ
"""

import logging
import json
import os
from datetime import date, datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)
from db import Database

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

(
    ADD_OBJ_NAME, ADD_OBJ_DESC,
    SELECT_OBJ, REPORT_WORKERS, REPORT_VOLUME, REPORT_UNIT,
    REPORT_NOTES, REPORT_CONFIRM,
    ISSUE_TEXT, ISSUE_PRIORITY,
    ADD_WORKER_NAME, ADD_WORKER_ROLE,
) = range(12)

TOKEN = os.getenv("BOT_TOKEN", "8668512686:AAGTozfhQX7TJCFU-revC1eO29h8roHSjVA")

db = Database("construction.db")


def obj_keyboard(objects, action_prefix: str):
    buttons = [
        [InlineKeyboardButton(f"🏗 {o['name']}", callback_data=f"{action_prefix}:{o['id']}")]
        for o in objects
    ]
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Объекты",   callback_data="menu:objects"),
         InlineKeyboardButton("📝 Отчёт",     callback_data="menu:report")],
        [InlineKeyboardButton("⚠️ Проблема",  callback_data="menu:issue"),
         InlineKeyboardButton("👷 Рабочие",   callback_data="menu:workers")],
        [InlineKeyboardButton("📊 Статистика",callback_data="menu:stats"),
         InlineKeyboardButton("📅 История",   callback_data="menu:history")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.full_name, user.username)
    await update.message.reply_text(
        f"👷 *Строительный бот*\nДобро пожаловать, {user.first_name}!\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]
    if action == "objects":
        await show_objects(query, context)
    elif action == "report":
        await start_report(query, context)
    elif action == "issue":
        await start_issue(query, context)
    elif action == "workers":
        await show_workers(query, context)
    elif action == "stats":
        await show_stats(query, context)
    elif action == "history":
        await show_history(query, context)


async def show_objects(query_or_update, context):
    objects = db.get_objects()
    is_query = hasattr(query_or_update, 'edit_message_text')
    if not objects:
        text = "📋 *Объекты*\n\nОбъектов пока нет."
    else:
        lines = []
        for o in objects:
            status_icon = {"active": "🟢", "paused": "🟡", "done": "✅"}.get(o["status"], "⚪")
            lines.append(f"{status_icon} *{o['name']}*\n   _{o['description'] or 'без описания'}_")
        text = "📋 *Объекты строительства:*\n\n" + "\n\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить объект", callback_data="obj:add")],
        [InlineKeyboardButton("🔧 Изменить статус", callback_data="obj:status")],
        [InlineKeyboardButton("🏠 Меню",            callback_data="back:main")],
    ])
    if is_query:
        await query_or_update.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await query_or_update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def obj_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if parts[1] == "add":
        await query.edit_message_text("🏗 Введите *название* нового объекта:", parse_mode="Markdown")
        return ADD_OBJ_NAME
    elif parts[1] == "status":
        objects = db.get_objects()
        if not objects:
            await query.edit_message_text("Объектов нет.")
            return ConversationHandler.END
        await query.edit_message_text(
            "Выберите объект для изменения статуса:",
            reply_markup=obj_keyboard(objects, "setstatus"),
        )


async def add_obj_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_obj_name"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 Введите *описание* объекта (или `-` чтобы пропустить):",
        parse_mode="Markdown"
    )
    return ADD_OBJ_DESC


async def add_obj_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    if desc == "-":
        desc = ""
    name = context.user_data.pop("new_obj_name")
    obj_id = db.add_object(name, desc, update.effective_user.id)
    await update.message.reply_text(
        f"✅ Объект *{name}* добавлен (ID: {obj_id})!",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def start_report(query_or_update, context):
    objects = db.get_objects(status="active")
    is_query = hasattr(query_or_update, 'edit_message_text')
    if not objects:
        text = "❌ Нет активных объектов. Добавьте объект сначала."
        if is_query:
            await query_or_update.edit_message_text(text)
        else:
            await query_or_update.message.reply_text(text)
        return ConversationHandler.END
    kb = obj_keyboard(objects, "rpt_obj")
    text = "📝 *Новый отчёт*\nВыберите объект:"
    if is_query:
        await query_or_update.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await query_or_update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return SELECT_OBJ


async def report_select_obj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    obj_id = int(query.data.split(":")[1])
    context.user_data["report"] = {"obj_id": obj_id, "date": str(date.today())}
    obj = db.get_object(obj_id)
    await query.edit_message_text(
        f"🏗 *{obj['name']}*\n\n👷 Сколько рабочих было сегодня на объекте?",
        parse_mode="Markdown",
    )
    return REPORT_WORKERS


async def report_workers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = int(update.message.text.strip())
        if n < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Введите целое число рабочих:")
        return REPORT_WORKERS
    context.user_data["report"]["workers_count"] = n
    await update.message.reply_text(
        "📦 Какой объём работ выполнен?\n_(например: 15.5)_",
        parse_mode="Markdown"
    )
    return REPORT_VOLUME


async def report_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        v = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("⚠️ Введите число:")
        return REPORT_VOLUME
    context.user_data["report"]["volume"] = v
    await update.message.reply_text(
        "📏 Единица измерения?\n_(м², м³, пог.м, шт, т и т.д.)_",
        parse_mode="Markdown",
    )
    return REPORT_UNIT


async def report_unit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["report"]["unit"] = update.message.text.strip()
    await update.message.reply_text(
        "💬 Примечания к отчёту?\n_(напишите `-` если нет)_",
        parse_mode="Markdown",
    )
    return REPORT_NOTES


async def report_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notes = update.message.text.strip()
    if notes == "-":
        notes = ""
    context.user_data["report"]["notes"] = notes
    r = context.user_data["report"]
    obj = db.get_object(r["obj_id"])
    text = (
        f"📋 *Подтвердите отчёт:*\n\n"
        f"🏗 Объект: *{obj['name']}*\n"
        f"📅 Дата: {r['date']}\n"
        f"👷 Рабочих: {r['workers_count']}\n"
        f"📦 Объём: {r['volume']} {r['unit']}\n"
        f"💬 Примечания: {notes or '—'}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Сохранить", callback_data="report:save"),
         InlineKeyboardButton("❌ Отмена",   callback_data="cancel")],
    ])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return REPORT_CONFIRM


async def report_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    r = context.user_data.pop("report", {})
    if not r:
        await query.edit_message_text("⚠️ Ошибка: данные отчёта не найдены.")
        return ConversationHandler.END
    report_id = db.add_report(
        obj_id=r["obj_id"], user_id=update.effective_user.id,
        report_date=r["date"], workers_count=r["workers_count"],
        volume=r["volume"], unit=r["unit"], notes=r["notes"],
    )
    obj = db.get_object(r["obj_id"])
    pub = (
        f"📊 *ЕЖЕДНЕВНЫЙ ОТЧЁТ* #{report_id}\n"
        f"{'─' * 30}\n"
        f"🏗 *{obj['name']}*\n"
        f"📅 {r['date']}  |  🕐 {datetime.now().strftime('%H:%M')}\n"
        f"{'─' * 30}\n"
        f"👷 *Рабочих:* {r['workers_count']} чел.\n"
        f"📦 *Выполнено:* {r['volume']} {r['unit']}\n"
    )
    if r["notes"]:
        pub += f"💬 *Примечания:* {r['notes']}\n"
    pub += f"{'─' * 30}\n✍️ {update.effective_user.full_name}"
    await query.edit_message_text(pub, parse_mode="Markdown")
    return ConversationHandler.END


async def start_issue(query_or_update, context):
    objects = db.get_objects(status="active")
    is_query = hasattr(query_or_update, 'edit_message_text')
    if not objects:
        text = "❌ Нет активных объектов."
        if is_query:
            await query_or_update.edit_message_text(text)
        else:
            await query_or_update.message.reply_text(text)
        return ConversationHandler.END
    kb = obj_keyboard(objects, "iss_obj")
    text = "⚠️ *Фиксация проблемы*\nВыберите объект:"
    if is_query:
        await query_or_update.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await query_or_update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return SELECT_OBJ


async def issue_select_obj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    obj_id = int(query.data.split(":")[1])
    context.user_data["issue"] = {"obj_id": obj_id}
    await query.edit_message_text("⚠️ Опишите проблему подробно:")
    return ISSUE_TEXT


async def issue_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["issue"]["text"] = update.message.text.strip()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔴 Критическая", callback_data="priority:critical")],
        [InlineKeyboardButton("🟠 Высокая",     callback_data="priority:high")],
        [InlineKeyboardButton("🟡 Средняя",     callback_data="priority:medium")],
        [InlineKeyboardButton("🟢 Низкая",      callback_data="priority:low")],
    ])
    await update.message.reply_text("📊 Приоритет проблемы:", reply_markup=kb)
    return ISSUE_PRIORITY


async def issue_priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    priority = query.data.split(":")[1]
    issue = context.user_data.pop("issue", {})
    obj = db.get_object(issue["obj_id"])
    icons  = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    labels = {"critical": "Критическая", "high": "Высокая", "medium": "Средняя", "low": "Низкая"}
    db.add_issue(obj_id=issue["obj_id"], user_id=update.effective_user.id,
                 text=issue["text"], priority=priority)
    msg = (
        f"{'─' * 30}\n"
        f"{icons[priority]} *ПРОБЛЕМА — {labels[priority].upper()}*\n"
        f"{'─' * 30}\n"
        f"🏗 *{obj['name']}*\n"
        f"📅 {date.today()}  |  {datetime.now().strftime('%H:%M')}\n\n"
        f"📋 {issue['text']}\n"
        f"{'─' * 30}\n"
        f"✍️ {update.effective_user.full_name}"
    )
    await query.edit_message_text(msg, parse_mode="Markdown")
    return ConversationHandler.END


async def show_workers(query_or_update, context):
    workers = db.get_workers()
    is_query = hasattr(query_or_update, 'edit_message_text')
    if not workers:
        text = "👷 *Рабочие*\n\nСписок пуст."
    else:
        lines = [f"• *{w['name']}* — {w['role']}" for w in workers]
        text = f"👷 *Рабочие* ({len(workers)} чел.):\n\n" + "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить рабочего", callback_data="worker:add")],
        [InlineKeyboardButton("🏠 Меню",              callback_data="back:main")],
    ])
    if is_query:
        await query_or_update.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await query_or_update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def worker_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "worker:add":
        await query.edit_message_text("👷 Введите *ФИО* рабочего:", parse_mode="Markdown")
        return ADD_WORKER_NAME


async def add_worker_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_worker_name"] = update.message.text.strip()
    await update.message.reply_text("🔧 Введите *должность/специализацию*:", parse_mode="Markdown")
    return ADD_WORKER_ROLE


async def add_worker_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = update.message.text.strip()
    name = context.user_data.pop("new_worker_name")
    db.add_worker(name, role)
    await update.message.reply_text(
        f"✅ Рабочий *{name}* ({role}) добавлен!",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def show_stats(query_or_update, context):
    is_query = hasattr(query_or_update, 'edit_message_text')
    stats = db.get_stats()
    objects = db.get_objects()
    text = f"📊 *СТАТИСТИКА*\n{'─' * 28}\n"
    text += f"🏗 Объектов всего: {stats['total_objects']}\n"
    text += f"📝 Отчётов за неделю: {stats['reports_week']}\n"
    text += f"⚠️ Открытых проблем: {stats['open_issues']}\n"
    text += f"👷 Рабочих в базе: {stats['total_workers']}\n\n"
    text += "*По объектам (за 7 дней):*\n"
    for o in objects:
        s = db.get_object_stats(o["id"])
        if s["reports"]:
            text += (
                f"• *{o['name']}*: {s['reports']} отчётов, "
                f"~{s['avg_workers']:.0f} чел/день, "
                f"{s['total_volume']:.1f} {s['unit']}\n"
            )
        else:
            text += f"• *{o['name']}*: нет отчётов\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Меню", callback_data="back:main")]])
    if is_query:
        await query_or_update.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await query_or_update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def show_history(query_or_update, context):
    is_query = hasattr(query_or_update, 'edit_message_text')
    reports = db.get_all_reports(limit=10)
    if not reports:
        text = "📅 *История*\n\nОтчётов нет."
    else:
        lines = []
        for r in reports:
            lines.append(
                f"📅 {r['report_date']} | 🏗 {r['obj_name']}\n"
                f"   👷 {r['workers_count']} чел — {r['volume']} {r['unit']}"
            )
        text = "📅 *Последние 10 отчётов:*\n\n" + "\n\n".join(lines)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Меню", callback_data="back:main")]])
    if is_query:
        await query_or_update.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await query_or_update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def daily_summary(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    today = str(date.today())
    objects = db.get_objects()
    lines = [f"📊 *СВОДНЫЙ ОТЧЁТ ЗА {today}*", "─" * 28]
    total_workers = 0
    has_data = False
    for o in objects:
        reports = db.get_reports_for_date(o["id"], today)
        if reports:
            has_data = True
            workers = sum(r["workers_count"] for r in reports)
            total_workers += workers
            vols = ", ".join(f"{r['volume']} {r['unit']}" for r in reports)
            lines.append(f"🏗 *{o['name']}*\n   👷 {workers} чел | 📦 {vols}")
        else:
            lines.append(f"🏗 *{o['name']}*\n   _— отчёт не сдан —_")
    lines.append("─" * 28)
    if has_data:
        lines.append(f"👥 *Итого рабочих:* {total_workers} чел.")
    issues = db.get_open_issues()
    if issues:
        lines.append(f"\n⚠️ *Открытых проблем: {len(issues)}*")
        for iss in issues[:3]:
            icons = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            lines.append(f"{icons.get(iss['priority'],'⚪')} {iss['obj_name']}: {iss['text'][:60]}…")
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="Markdown")


async def set_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    context.job_queue.run_daily(
        daily_summary,
        time=datetime.strptime("18:00", "%H:%M").time(),
        data={"chat_id": chat_id},
        name=f"daily_{chat_id}",
    )
    await update.message.reply_text(
        "✅ Ежедневный сводный отчёт будет отправляться в *18:00*.",
        parse_mode="Markdown"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Отменено.", reply_markup=main_menu_keyboard())
    else:
        await update.message.reply_text("❌ Отменено.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dest = query.data.split(":")[1]
    if dest == "main":
        await query.edit_message_text("Выберите действие:", reply_markup=main_menu_keyboard())


async def setstatus_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    obj_id = int(query.data.split(":")[1])
    obj = db.get_object(obj_id)
    statuses = {"active": "🟢 Активный", "paused": "🟡 Приостановлен", "done": "✅ Завершён"}
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"dostatus:{obj_id}:{key}")]
        for key, label in statuses.items()
    ])
    await query.edit_message_text(
        f"Выберите статус для *{obj['name']}*:",
        parse_mode="Markdown", reply_markup=kb,
    )


async def dostatus_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, obj_id, status = query.data.split(":")
    db.set_object_status(int(obj_id), status)
    obj = db.get_object(int(obj_id))
    await query.edit_message_text(
        f"✅ Статус *{obj['name']}* обновлён → {status}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Меню", callback_data="back:main")]]),
    )


def main():
    db.init()
    app = Application.builder().token(TOKEN).build()

    add_obj_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(obj_callback, pattern="^obj:add$")],
        states={
            ADD_OBJ_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_obj_name)],
            ADD_OBJ_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_obj_desc)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$"),
                   CommandHandler("cancel", cancel)],
    )

    report_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(lambda u, c: start_report(u.callback_query, c), pattern="^menu:report$"),
            CommandHandler("report", lambda u, c: start_report(u, c)),
        ],
        states={
            SELECT_OBJ:     [CallbackQueryHandler(report_select_obj, pattern="^rpt_obj:")],
            REPORT_WORKERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, report_workers)],
            REPORT_VOLUME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, report_volume)],
            REPORT_UNIT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, report_unit)],
            REPORT_NOTES:   [MessageHandler(filters.TEXT & ~filters.COMMAND, report_notes)],
            REPORT_CONFIRM: [CallbackQueryHandler(report_save, pattern="^report:save$"),
                             CallbackQueryHandler(cancel, pattern="^cancel$")],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$"),
                   CommandHandler("cancel", cancel)],
    )

    issue_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(lambda u, c: start_issue(u.callback_query, c), pattern="^menu:issue$"),
            CommandHandler("issue", lambda u, c: start_issue(u, c)),
        ],
        states={
            SELECT_OBJ:     [CallbackQueryHandler(issue_select_obj, pattern="^iss_obj:")],
            ISSUE_TEXT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, issue_text)],
            ISSUE_PRIORITY: [CallbackQueryHandler(issue_priority, pattern="^priority:")],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$"),
                   CommandHandler("cancel", cancel)],
    )

    worker_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(worker_callback, pattern="^worker:add$")],
        states={
            ADD_WORKER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_worker_name)],
            ADD_WORKER_ROLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_worker_role)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$"),
                   CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setdaily", set_daily))
    app.add_handler(add_obj_conv)
    app.add_handler(report_conv)
    app.add_handler(issue_conv)
    app.add_handler(worker_conv)
    app.add_handler(CallbackQueryHandler(menu_callback,      pattern="^menu:"))
    app.add_handler(CallbackQueryHandler(back_callback,      pattern="^back:"))
    app.add_handler(CallbackQueryHandler(obj_callback,       pattern="^obj:"))
    app.add_handler(CallbackQueryHandler(setstatus_callback, pattern="^setstatus:"))
    app.add_handler(CallbackQueryHandler(dostatus_callback,  pattern="^dostatus:"))
    app.add_handler(CallbackQueryHandler(cancel,             pattern="^cancel$"))

    print("🤖 Строительный бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()