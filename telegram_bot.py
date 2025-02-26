import telebot
import os
from dotenv import load_dotenv
from trading_bot import get_historical_data, calculate_signals, place_order, get_wallet_balance
import time
from telebot import types
from all_crypto import get_all_cryptocurrencies

load_dotenv()

bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))

trading_state = {
    'last_action': None,
    'consecutive_trades': 0,
    'current_symbol': None
}
available_symbols = get_all_cryptocurrencies()

def update_available_symbols():
    global available_symbols
    available_symbols = get_all_cryptocurrencies()

update_available_symbols()


markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)

com_clear = types.KeyboardButton('Очистить чат')
com_set_symbol = types.KeyboardButton('Выбрать криптовалюту')
com_add_symbol = types.KeyboardButton('Добавить криптовалюту')
com_balance = types.KeyboardButton('Проверить баланс')
com_price = types.KeyboardButton('Текущая цена')
com_start_trading = types.KeyboardButton('Начать торговлю')
com_stop_trading = types.KeyboardButton('Остановить торговлю')

markup.add(com_clear, com_set_symbol, com_add_symbol, com_balance, com_price, com_start_trading, com_stop_trading)


@bot.message_handler(commands=['start'])
def start_command(message):
    bot.send_message(message.chat.id, "Привет! Я торговый бот. Выберите действие:", reply_markup=markup)


@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    if message.text == 'Очистить чат':
        clear_command(message)
    elif message.text == 'Выбрать криптовалюту':
        set_symbol_command(message)
    elif message.text == 'Добавить криптовалюту':
        add_symbol_command(message)
    elif message.text == 'Проверить баланс':
        balance_command(message)
    elif message.text == 'Текущая цена':
        price_command(message)
    elif message.text == 'Начать торговлю':
        start_trading_command(message)
    elif message.text == 'Остановить торговлю':
        stop_trading_command(message)
    else:
        bot.send_message(message.chat.id, "❌ Неизвестная команда. Используйте кнопки.", reply_markup=markup)


@bot.message_handler(commands=['set_symbol'])
def set_symbol_command(message):
    markup = types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
    buttons = [types.KeyboardButton(symbol) for symbol in available_symbols]
    markup.add(*buttons)
    bot.send_message(message.chat.id, "Выберите криптовалюту:", reply_markup=markup)
    bot.register_next_step_handler(message, process_symbol_selection)


def process_symbol_selection(message):
    selected_symbol = message.text.upper()
    if selected_symbol in available_symbols:
        trading_state['current_symbol'] = selected_symbol  
        bot.send_message(message.chat.id, f"✅ Выбрана криптовалюта: {selected_symbol}", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❌ Эта криптовалюта недоступна. Пожалуйста, выберите из: " + ", ".join(available_symbols), reply_markup=markup)


@bot.message_handler(commands=['clear'])
def clear_command(message):
    chat_id = message.chat.id
    message_id = message.message_id

    for i in range(message_id, 0, -1):
        try:
            bot.delete_message(chat_id, i)
        except:
            continue


@bot.message_handler(commands=['balance'])
def balance_command(message):
    balance = get_wallet_balance()
    if balance:
        available = balance['result']['list'][0]['totalAvailableBalance']
        total = balance['result']['list'][0]['totalWalletBalance']
        bot.send_message(message.chat.id, f"💰 Баланс кошелька:\n"
                              f"Доступно USDT: {available}\n"
                              f"Всего USDT: {total}", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❌ Ошибка при получении баланса", reply_markup=markup)


@bot.message_handler(commands=['price'])
def price_command(message):
    symbol = trading_state.get('current_symbol', "SUI")
    try:
        df = get_historical_data(symbol, "15")
        current_price = float(df['close'].iloc[0])
        bot.send_message(message.chat.id, f"💹 Текущая цена {symbol}: {current_price}", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при получении цены: {e}", reply_markup=markup)


@bot.message_handler(commands=['add_symbol'])
def add_symbol_command(message):
    bot.send_message(message.chat.id, "Введите название криптовалюты (например, BTC):", reply_markup=markup)
    bot.register_next_step_handler(message, process_new_symbol)


def process_new_symbol(message):
    new_symbol = message.text.upper()
    if new_symbol not in available_symbols:
        available_symbols.append(new_symbol+"USDT")
        bot.send_message(message.chat.id, f"✅ Криптовалюта {new_symbol} добавлена в список доступных.", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❌ Эта криптовалюта уже в списке доступных.", reply_markup=markup)


def trading_bot(message, symbol=None, interval="15", qty=0.1):
    if symbol is None:
        symbol = trading_state.get('current_symbol', "SUI")
    while True:
        try:
            df = get_historical_data(symbol, interval)
            df = calculate_signals(df)

            current_price = float(df['close'].iloc[0])
            last_sma20 = df['SMA20'].iloc[-1]
            last_sma50 = df['SMA50'].iloc[-1]
            current_rsi = df['RSI'].iloc[-1]
            volatility = df['volatility'].iloc[-1]

            min_qty = 0.1
            if qty < min_qty:
                qty = min_qty

            status_message = (
                f"📊 Статус торговли для {symbol}:\n"
                f"Цена: {current_price} \n"
                f"RSI: {current_rsi:.2f}\n"
                f"Волатильность: {volatility:.2f}"
            )
            bot.send_message(message.chat.id, status_message, reply_markup=markup)

            should_buy = (
                    last_sma20 > last_sma50 and
                    current_rsi < 70 and
                    trading_state['consecutive_trades'] < 3 and
                    trading_state['last_action'] != "Buy"
            )

            should_sell = (
                    last_sma20 < last_sma50 and
                    current_rsi > 30 and
                    trading_state['consecutive_trades'] < 3 and
                    trading_state['last_action'] != "Sell"
            )

            if should_buy:
                if place_order(symbol, "Buy", qty):
                    trading_state['last_action'] = "Buy"
                    trading_state['consecutive_trades'] += 1
                    bot.send_message(message.chat.id, "🟢 Сигнал на покупку!", reply_markup=markup)
            elif should_sell:
                if place_order(symbol, "Sell", qty):
                    trading_state['last_action'] = "Sell"
                    trading_state['consecutive_trades'] += 1
                    bot.send_message(message.chat.id, "🔴 Сигнал на продажу!", reply_markup=markup)
            else:
                trading_state['consecutive_trades'] = 0

            time.sleep(60)

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {e}", reply_markup=markup)
            time.sleep(60)


@bot.message_handler(commands=['start_trading'])
def start_trading_command(message):
    bot.send_message(message.chat.id, "▶️ Торговля запущена", reply_markup=markup)
    trading_bot(message)


@bot.message_handler(commands=['stop_trading'])
def stop_trading_command(message):
    bot.send_message(message.chat.id, "⏹ Торговля остановлена", reply_markup=markup)


def main():
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка бота: {e}")


if __name__ == "__main__":
    main()