from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from telegram.request import HTTPXRequest
import logging
import aiohttp
import os
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токены из .env файла
TOKEN = os.getenv("BOT_TOKEN")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

# API для поиска вакансий
JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"

# Хранилище данных пользователей
user_data = defaultdict(lambda: {
    "messages": 0,
    "last_search": None,
    "favorites": [],
    "search_results": []
})


# ========== ФУНКЦИИ ПОИСКА ВАКАНСИЙ ==========

async def search_jobs(query: str, location: str) -> list:
    """Поиск вакансий через JSearch API"""
    try:
        headers = {
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "jsearch.p.rapidapi.com",
            "Content-Type": "application/json"
        }

        search_query = f"{query} {location}"

        async with aiohttp.ClientSession() as session:
            params = {
                "query": search_query,
                "page": "1",
                "num_pages": "1",
                "date_posted": "all"
            }

            async with session.get(JSEARCH_URL, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    jobs = []

                    if data.get("data"):
                        for job in data["data"][:5]:
                            salary_min = job.get("job_min_salary")
                            salary_max = job.get("job_max_salary")
                            currency = job.get("job_salary_currency", "₽")

                            if salary_min and salary_max:
                                salary_text = f"{salary_min:,.0f} - {salary_max:,.0f} {currency}".replace(",", " ")
                            elif salary_min:
                                salary_text = f"от {salary_min:,.0f} {currency}".replace(",", " ")
                            elif salary_max:
                                salary_text = f"до {salary_max:,.0f} {currency}".replace(",", " ")
                            else:
                                salary_text = "Не указана"

                            jobs.append({
                                "title": job.get("job_title", "Не указано"),
                                "company": job.get("employer_name", "Не указана"),
                                "salary": salary_text,
                                "url": job.get("job_apply_link", "#"),
                                "description": job.get("job_description", "Описание не указано")[:200]
                            })
                    return jobs
                else:
                    logger.error(f"API error: {resp.status}")
                    return []
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


def format_job_card(job: dict, index: int) -> str:
    """Форматирование карточки вакансии"""
    return (
        f"📌 *Вакансия #{index + 1}*\n\n"
        f"📋 *Название:* {job['title']}\n"
        f"🏢 *Компания:* {job['company']}\n"
        f"💰 *Зарплата:* {job['salary']}\n"
        f"📝 *Описание:* {job['description']}...\n\n"
        f"🔗 [Подробнее]({job['url']})"
    )


# ========== ОБРАБОТЧИКИ КОМАНД ==========

async def start(update: Update, context):
    """Обработчик команды /start"""
    user = update.effective_user

    keyboard = [
        [InlineKeyboardButton("🔍 Начать поиск", callback_data='start_search')],
        [InlineKeyboardButton("⭐️ Избранное", callback_data='show_favorites')],
        [InlineKeyboardButton("📊 Статистика", callback_data='show_stats')],
        [InlineKeyboardButton("❓ Помощь", callback_data='show_help')]
    ]

    await update.message.reply_text(
        f"👋 *Привет, {user.first_name}!*\n\n"
        f"🤖 *Я бот для поиска вакансий*\n\n"
        f"🔍 *Что я умею:*\n"
        f"• Искать вакансии по городу и профессии\n"
        f"• Показывать до 5 вакансий с полной информацией\n"
        f"• Сохранять в избранное\n"
        f"• Повторять последний поиск\n\n"
        f"📌 *Используй /search для начала*\n"
        f"💬 *Или просто напиши мне вопрос!*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def search_command(update: Update, context):
    """Начало поиска - запрос города"""
    await update.message.reply_text(
        "🔍 *Начинаем поиск вакансий!*\n\n"
        "📍 *Введите город:*\n"
        "*(например: Москва, Санкт-Петербург, Лондон)*",
        parse_mode='Markdown'
    )
    return 1


async def receive_city(update: Update, context):
    """Получение города от пользователя"""
    context.user_data['city'] = update.message.text.strip()
    await update.message.reply_text(
        f"📍 *Город:* {context.user_data['city']}\n\n"
        f"💼 *Введите профессию:*\n"
        f"*(например: Python, JavaScript, дизайнер)*",
        parse_mode='Markdown'
    )
    return 2


async def receive_profession(update: Update, context):
    """Получение профессии и поиск вакансий"""
    profession = update.message.text.strip()
    city = context.user_data.get('city')
    user_id = update.effective_user.id

    await update.message.reply_text(
        f"🔍 *Ищу вакансии...*\n\n"
        f"📍 {city}\n"
        f"💼 {profession}\n\n"
        f"⏳ *Пожалуйста, подождите...*",
        parse_mode='Markdown'
    )

    jobs = await search_jobs(profession, city)

    # Если вакансий нет
    if not jobs:
        await update.message.reply_text(
            "😔 *Вакансий не найдено!*\n\n"
            "Попробуйте:\n"
            "• Изменить город\n"
            "• Расширить ключевые слова\n"
            "• Проверить правильность написания\n\n"
            "🔄 Используйте /search для нового поиска",
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    # Сохраняем результаты поиска
    user_data[user_id]['last_search'] = {
        'city': city,
        'profession': profession,
        'jobs': jobs
    }
    user_data[user_id]['search_results'] = jobs

    await update.message.reply_text(
        f"✅ *Найдено {len(jobs)} вакансий!*\n\n"
        f"📋 *Вот результаты поиска:*\n",
        parse_mode='Markdown'
    )

    # Выводим каждую вакансию с кнопкой
    for i, job in enumerate(jobs):
        job_card = format_job_card(job, i)

        # Кнопка для сохранения
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐️ СОХРАНИТЬ В ИЗБРАННОЕ", callback_data=f'save_fav_{i}')]
        ])

        await update.message.reply_text(
            job_card,
            reply_markup=keyboard,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

    # Кнопки действий после поиска
    action_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 ПОВТОРИТЬ ПОИСК", callback_data='repeat_last')],
        [InlineKeyboardButton("⭐️ ИЗБРАННОЕ", callback_data='show_favorites')],
        [InlineKeyboardButton("🔍 НОВЫЙ ПОИСК", callback_data='start_search')]
    ])

    await update.message.reply_text(
        "🎯 *Что дальше?*\n\n"
        "• Нажмите на кнопку ⭐️ чтобы сохранить вакансию\n"
        "• Используйте /last для повторного поиска\n"
        "• Используйте /favorites для просмотра избранного\n\n"
        "💡 *Или отправьте:* `/save_1`, `/save_2` и т.д.",
        reply_markup=action_keyboard,
        parse_mode='Markdown'
    )

    return ConversationHandler.END


async def cancel_search(update: Update, context):
    """Отмена поиска"""
    await update.message.reply_text(
        "❌ *Поиск отменен*\n\n"
        "Используйте /search чтобы начать заново",
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def last_search(update: Update, context):
    """Повтор последнего поиска (/last)"""
    user_id = update.effective_user.id
    last = user_data[user_id].get('last_search')

    if not last:
        await update.message.reply_text(
            "❌ *Нет истории поиска!*\n\n"
            "Сначала выполните поиск с помощью /search",
            parse_mode='Markdown'
        )
        return

    jobs = last['jobs']

    await update.message.reply_text(
        f"🔄 *Повторяем последний поиск*\n\n"
        f"📍 {last['city']}\n"
        f"💼 {last['profession']}\n\n"
        f"📋 *Найдено {len(jobs)} вакансий:*\n",
        parse_mode='Markdown'
    )

    for i, job in enumerate(jobs):
        job_card = format_job_card(job, i)
        await update.message.reply_text(
            job_card,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )


async def save_favorite_callback(update: Update, context):
    """Сохранение в избранное через callback кнопку"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data.startswith('save_fav_'):
        index = int(data.split('_')[2])
        jobs = user_data[user_id].get('search_results', [])

        if index < len(jobs):
            job = jobs[index]

            # Проверяем, не сохранена ли уже
            is_favorite = any(fav['title'] == job['title'] for fav in user_data[user_id]['favorites'])

            if not is_favorite:
                user_data[user_id]['favorites'].append(job)
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text(
                    f"✅ *Сохранено в избранное!*\n\n"
                    f"📌 {job['title']}\n"
                    f"🏢 {job['company']}\n\n"
                    f"⭐️ /favorites - посмотреть избранное",
                    parse_mode='Markdown'
                )
            else:
                await query.message.reply_text(
                    "⚠️ *Эта вакансия уже в избранном!*",
                    parse_mode='Markdown'
                )


async def save_favorite_text(update: Update, context):
    """Сохранение в избранное через текстовую команду (/save_1, /save_2 и т.д.)"""
    user_id = update.effective_user.id
    text = update.message.text

    try:
        # Извлекаем номер из команды /save_1, /save_2 и т.д.
        number = int(text.split('_')[1]) - 1
        jobs = user_data[user_id].get('search_results', [])

        if 0 <= number < len(jobs):
            job = jobs[number]

            # Проверяем, не сохранена ли уже
            if not any(fav['title'] == job['title'] for fav in user_data[user_id]['favorites']):
                user_data[user_id]['favorites'].append(job)
                await update.message.reply_text(
                    f"✅ *Сохранено в избранное!*\n\n"
                    f"📌 {job['title']}\n"
                    f"🏢 {job['company']}\n\n"
                    f"⭐️ /favorites - посмотреть избранное",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "⚠️ *Эта вакансия уже в избранном!*",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                "❌ *Неверный номер вакансии!*\nИспользуйте /save_1 до /save_5",
                parse_mode='Markdown'
            )
    except (IndexError, ValueError):
        await update.message.reply_text(
            "❌ *Используйте:* `/save_1`, `/save_2`, `/save_3`, `/save_4`, `/save_5`",
            parse_mode='Markdown'
        )


async def show_favorites(update: Update, context):
    """Показать избранные вакансии (/favorites)"""
    user_id = update.effective_user.id
    favorites = user_data[user_id]['favorites']

    if not favorites:
        await update.message.reply_text(
            "⭐️ *Избранное пусто*\n\n"
            "Добавляйте вакансии в избранное во время поиска",
            parse_mode='Markdown'
        )
        return

    await update.message.reply_text(
        f"⭐️ *Ваши избранные вакансии ({len(favorites)})*\n\n",
        parse_mode='Markdown'
    )

    for i, job in enumerate(favorites):
        job_card = (
            f"📌 *Избранное #{i + 1}*\n"
            f"📋 *Название:* {job['title']}\n"
            f"🏢 *Компания:* {job['company']}\n"
            f"💰 *Зарплата:* {job['salary']}\n"
            f"🔗 [Подробнее]({job['url']})"
        )
        await update.message.reply_text(
            job_card,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )


async def show_stats(update: Update, context):
    """Показать статистику пользователя (/stats)"""
    user_id = update.effective_user.id
    data = user_data[user_id]

    await update.message.reply_text(
        f"📊 *Ваша статистика*\n\n"
        f"💬 Сообщений: *{data['messages']}*\n"
        f"⭐️ Избранных: *{len(data['favorites'])}*\n"
        f"🔍 Последний поиск: *{'Есть' if data['last_search'] else 'Нет'}*\n\n"
        f"📅 Активен с: *{datetime.now().strftime('%d.%m.%Y')}*",
        parse_mode='Markdown'
    )


async def show_help(update: Update, context):
    """Показать справку (/help)"""
    await update.message.reply_text(
        "📚 *Помощь по командам*\n\n"
        "🤖 *Основные команды:*\n"
        "• /start - Начать работу\n"
        "• /search - Найти вакансии (город → профессия)\n"
        "• /last - Повторить последний поиск\n"
        "• /favorites - Показать избранное\n"
        "• /stats - Моя статистика\n"
        "• /help - Эта справка\n\n"
        "⭐️ *Как сохранить вакансию:*\n"
        "• Нажмите на кнопку ⭐️ под вакансией\n"
        "• Или отправьте `/save_1`, `/save_2` и т.д.\n\n"
        "🔍 *Примеры поиска:*\n"
        "• Москва + Python\n"
        "• Лондон + дизайнер\n"
        "• Нью-Йорк + JavaScript\n\n"
        "💡 *Просто напишите вопрос - я помогу с карьерой!*",
        parse_mode='Markdown'
    )


async def handle_message(update: Update, context):
    """Обработка обычных сообщений"""
    user_id = update.effective_user.id
    user_data[user_id]["messages"] += 1

    await update.message.reply_text(
        "🤖 *Я бот для поиска вакансий!*\n\n"
        "🔍 *Чтобы найти работу:*\n"
        "• Используйте /search\n"
        "• Или нажмите кнопку «Начать поиск»\n\n"
        "💡 *Также могу помочь с:*\n"
        "• Составлением резюме\n"
        "• Подготовкой к собеседованию\n"
        "• Советами по карьере\n\n"
        "❓ *Введите /help для справки*",
        parse_mode='Markdown'
    )


async def inline_buttons_handler(update: Update, context):
    """Обработка inline кнопок"""
    query = update.callback_query
    await query.answer()

    if query.data == 'start_search':
        await search_command(update, context)
    elif query.data == 'show_favorites':
        await show_favorites(update, context)
    elif query.data == 'show_stats':
        await show_stats(update, context)
    elif query.data == 'show_help':
        await show_help(update, context)
    elif query.data == 'repeat_last':
        await last_search(update, context)
    elif query.data.startswith('save_fav_'):
        await save_favorite_callback(update, context)


# ========== ЗАПУСК БОТА ==========

def main():
    print("=" * 60)
    print("🤖 БОТ ДЛЯ ПОИСКА ВАКАНСИЙ")
    print("=" * 60)
    print("✅ Поиск через JSearch API")
    print("✅ Сохранение в избранное (кнопки + текст)")
    print("✅ Повтор последнего поиска")
    print("=" * 60)

    # Создаем приложение
    request = HTTPXRequest(connect_timeout=30, read_timeout=30)
    app = Application.builder().token(TOKEN).request(request).build()

    # Конверсация для поиска вакансий
    search_conv = ConversationHandler(
        entry_points=[
            CommandHandler("search", search_command),
            CallbackQueryHandler(inline_buttons_handler, pattern='^start_search$')
        ],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_city)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_profession)],
        },
        fallbacks=[CommandHandler("cancel", cancel_search)],
    )

    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("last", last_search))
    app.add_handler(CommandHandler("favorites", show_favorites))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("help", show_help))

    # Регистрируем текстовые команды для сохранения
    app.add_handler(MessageHandler(filters.Regex(r'^/save_[1-5]$'), save_favorite_text))

    # Регистрируем конверсацию поиска
    app.add_handler(search_conv)

    # Регистрируем обработчик inline кнопок
    app.add_handler(CallbackQueryHandler(inline_buttons_handler))

    # Регистрируем обработчик обычных сообщений (должен быть последним)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ БОТ ЗАПУЩЕН!")
    print("📱 Telegram: @Saa01Bot")
    print("=" * 60)

    # Запускаем бота
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()





