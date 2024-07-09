import logging
import sqlite3
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Вставьте ваш Telegram токен сюда
TOKEN = 'PASTE_TOKEN_HERE'
# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Исправлено на правильное значение
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для разговора
DESCRIPTION, PHOTO, BUY = range(3)

# Подключение и инициализация базы данных
def init_db():
    conn = sqlite3.connect('photo_marketplace.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL,
            photos_bought INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id TEXT,
            description TEXT,
            price REAL,
            category TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bought_photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id TEXT,
            description TEXT,
            category TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    return conn, cursor

conn, cursor = init_db()

# Define the commission_account variable
commission_account = 0.0

# Стартовое сообщение с командами
START_MESSAGE = """
Привет! Добро пожаловать на биржу фотографий в Telegram! 📸

Вот список доступных команд:
- /start - Перезапуск бота
- /profile - Посмотреть профиль
- /view_free_photos - Просмотреть бесплатные фотографии
- /view_paid_photos - Просмотреть платные фотографии

Наслаждайтесь! 😃
"""

# Приветственное сообщение при новом пользователе
WELCOME_MESSAGE = """
Добро пожаловать на биржу фотографий в Telegram! 📸

Вы можете загружать и покупать фотографии.
"""

# Функция для создания основной клавиатуры
def get_main_keyboard():
    buttons = [
        [KeyboardButton("Профиль"), KeyboardButton("Добавить фотографию")],
        [KeyboardButton("Бесплатные фото"), KeyboardButton("Платные фото")],
        [KeyboardButton("Мои фото"), KeyboardButton("Купить фото")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    user_id = user.id
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    record = cursor.fetchone()
    if not record:
        cursor.execute('INSERT INTO users (id, username, balance, photos_bought) VALUES (?, ?, ?, ?)', (user_id, user.username, 100, 0))
        conn.commit()
        await update.message.reply_text(WELCOME_MESSAGE)
    else:
        cursor.execute('UPDATE users SET username = ? WHERE id = ?', (user.username, user_id))
        conn.commit()

    await update.message.reply_text(START_MESSAGE, reply_markup=get_main_keyboard())

# Запуск обработки добавления фотографии
async def add_photo_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Пожалуйста, введите описание и цену для фотографии в формате: <описание> <цена (или 0 для бесплатных)>",
        reply_markup=ReplyKeyboardRemove()
    )
    return DESCRIPTION

# Обработчик ввода описания и цены
async def add_photo_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        text = update.message.text.split()
        description = ' '.join(text[:-1])
        price = float(text[-1])
        context.user_data['description'] = description
        context.user_data['price'] = price

        await update.message.reply_text(f"Описание: {description}\nЦена: {'Бесплатно' if price == 0 else f'{price} Telegram Stars'}\n\n"
                                        "Если всё верно, отправьте фотографию. Для отмены используйте команду /start.")
        return PHOTO

    except (ValueError, IndexError):
        await update.message.reply_text("Пожалуйста, введите описание и цену в правильном формате: <описание> <цена (или 0 для бесплатных)>")
        return DESCRIPTION

# Обработчик загрузки фотографии
async def add_photo_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    try:
        description = context.user_data['description']
        price = context.user_data['price']
        category = 'free' if price == 0 else 'paid'

        if update.message.photo:
            file = update.message.photo[-1].file_id
            cursor.execute('INSERT INTO photos (user_id, file_id, description, price, category) VALUES (?, ?, ?, ?, ?)',
                           (user_id, file, description, price, category))
            conn.commit()
            await update.message.reply_text(f'Фотография "{description}" добавлена на биржу {"бесплатно" if price == 0 else f"по цене {price} Telegram Stars"}!',
                                            reply_markup=get_main_keyboard())
            return ConversationHandler.END
        else:
            await update.message.reply_text("Пожалуйста, загрузите фотографию.")
            return PHOTO
    except KeyError:
        await update.message.reply_text("Сначала добавьте описание и цену.")
        return DESCRIPTION

# Начало процесса покупки фотографии
async def buy_photo_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Показываем доступные фотографии
    cursor.execute('SELECT id, description, price FROM photos ORDER BY id ASC')
    records = cursor.fetchall()
    if not records:
        await update.message.reply_text('Нет доступных фотографий.', reply_markup=get_main_keyboard())
        return ConversationHandler.END

    message = 'Доступные фотографии:\n'
    for idx, (photo_id, description, price) in enumerate(records):
        message += f"{photo_id}. {description} - {'Бесплатно' if price == 0 else f'Цена: {price} 🌟'}\n"

    await update.message.reply_text(message)
    await update.message.reply_text(
        "Пожалуйста, введите номер фотографии, которую хотите купить.",
        reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True)
    )
    return BUY

# Обработчик покупки фотографии
async def buy_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text.lower() in ["отмена", "cancel"]:
        await update.message.reply_text('Покупка отменена. Возвращаемся к основному меню.', reply_markup=get_main_keyboard())
        return ConversationHandler.END

    try:
        photo_id = int(update.message.text)

        # Подтверждаем действительный идентификатор фотографии
        cursor.execute('SELECT * FROM photos WHERE id = ?', (photo_id,))
        photo = cursor.fetchone()
        if not photo:
            await update.message.reply_text('Неправильный номер фотографии. Попробуйте снова.',
                                            reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True))
            return BUY

        buyer_id = update.message.from_user.id

        # Подтверждаем существование пользователя
        cursor.execute('SELECT * FROM users WHERE id = ?', (buyer_id,))
        buyer = cursor.fetchone()
        if not buyer:
            await update.message.reply_text('Пожалуйста, используйте /start для регистрации сначала.', reply_markup=get_main_keyboard())
            return ConversationHandler.END

        seller_id = photo[1]
        file_id = photo[2]
        description = photo[3]
        price = photo[4]
        category = photo[5]

        # Подтверждаем, достаточно ли финансов
        if buyer[2] < price:
            await update.message.reply_text('Недостаточно средств для покупки фотографии.', reply_markup=get_main_keyboard())
            return ConversationHandler.END

        # Выполнение транзакции
        commission = price * 0.03
        net_payment = price - commission

        cursor.execute('UPDATE users SET balance = balance - ? WHERE id = ?', (price, buyer_id))
        cursor.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (net_payment, seller_id))
        cursor.execute('INSERT INTO bought_photos (user_id, file_id, description, category) VALUES (?, ?, ?, ?)', (buyer_id, file_id, description, category))
        cursor.execute('DELETE FROM photos WHERE id = ?', (photo_id,))
        cursor.execute('UPDATE users SET photos_bought = photos_bought + 1 WHERE id = ?', (buyer_id,))
        conn.commit()

        global commission_account
        commission_account += commission

        await update.message.reply_text(f'Фотография "{description}" куплена за {price} Telegram Stars! Комиссия составила {commission} на счёт биржи.')
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=file_id)
        await update.message.reply_text('Покупка прошла успешно! Вы купили фотографию.', reply_markup=get_main_keyboard())
        return ConversationHandler.END

    except (ValueError, IndexError):
        await update.message.reply_text("Пожалуйста, введите правильный номер фотографии.", reply_markup=ReplyKeyboardMarkup([["Отмена"]], resize_keyboard=True))
        return BUY

# Обработчик отмены
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Операция отменена. Возвращаемся к основному меню.', reply_markup=get_main_keyboard())
    return ConversationHandler.END

# Обработчик команды просмотра фотографий
async def view_free_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await view_photos_category(update, context, 'free')

async def view_paid_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await view_photos_category(update, context, 'paid')

async def view_photos_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str) -> None:
    cursor.execute('SELECT id, description, price FROM photos WHERE category = ?', (category,))
    records = cursor.fetchall()
    if not records:
        await update.message.reply_text('Нет доступных фотографий.')
        return
    message = ''
    for idx, (photo_id, description, price) in enumerate(records):
        message += f"{photo_id}. {description} - {'Бесплатно' if price == 0 else f'Цена: {price} 🌟'}\n"
    await update.message.reply_text(message)

# Обработчик команды /profile
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id

    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user_data = cursor.fetchone()
    if not user_data:
        await update.message.reply_text('Пожалуйста, используйте /start для регистрации сначала.')
        return

    message = (
        f"Ваш профиль:\n"
        f"ID: {user_data[0]}\n"
        f"Имя пользователя: @{user_data[1]}\n"
        f"Баланс: {user_data[2]} 🌟\n"
        f"Количество покупок: {user_data[3]}\n"
    )

    await update.message.reply_text(message)

# Обработчик команды просмотра купленных фотографий
async def view_purchased_photos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    cursor.execute('SELECT file_id, description FROM bought_photos WHERE user_id = ?', (user_id,))
    records = cursor.fetchall()
    if not records:
        await update.message.reply_text('Вы не купили ни одной фотографии.')
    else:
        media_group = []
        for record in records:
            media_group.append(InputMediaPhoto(media=record[0], caption=record[1]))
            if len(media_group) == 10:  # Send 10 photos at a time
                await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
                media_group = []
        if media_group:  # Send any remaining photos
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
# Обработчик сообщений с клавиатуры
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text

    if text.lower() == "профиль":
        await profile(update, context)
    elif text.lower() == "добавить фотографию":
        await add_photo_start(update, context)
    elif text.lower() == "бесплатные фото":
        await view_free_photos(update, context)
    elif text.lower() == "платные фото":
        await view_paid_photos(update, context)
    elif text.lower() == "мои фото":
        await view_purchased_photos(update, context)
    elif text.lower() == "купить фото":
        await buy_photo_start(update, context)
    else:
        await update.message.reply_text('Неизвестная команда. Пожалуйста, используйте /start для получения списка команд.')

# Запуск бота
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('add_photo', add_photo_start),
            MessageHandler(filters.Regex('^Добавить фотографию$'), add_photo_start),
            MessageHandler(filters.Regex('^Купить фото$'), buy_photo_start)
        ],
        states={
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_photo_description)],
            PHOTO: [MessageHandler(filters.PHOTO, add_photo_upload)],
            BUY: [MessageHandler(filters.TEXT & ~filters.COMMAND, buy_photo)]
        },
        fallbacks=[CommandHandler('start', cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("view_free_photos", view_free_photos))
    app.add_handler(CommandHandler("view_paid_photos", view_paid_photos))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("view_purchased_photos", view_purchased_photos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == '__main__':
    main()
