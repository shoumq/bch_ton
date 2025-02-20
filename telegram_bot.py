import telebot
import os
from dotenv import load_dotenv
from trading_bot import get_historical_data, calculate_signals, place_order, get_wallet_balance
import time
from telebot import types

load_dotenv()

bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))

trading_state = {
    'last_action': None,
    'consecutive_trades': 0,
    'current_symbol': None
}

available_symbols = ["SUIUSDT", "BTCUSDT", "ETHUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT"]


@bot.message_handler(commands=['start'])
def start_command(message):
    bot.send_message(message.chat.id, "Привет! Я торговый бот. Используйте следующие команды:\n"
                          "/clear - сбросить чат\n"
                          "/set_symbol - выбрать криптовалюту\n"
                          "/add_symbol - добавить криптовалюту\n"
                          "/balance - проверить баланс\n"
                          "/price - текущая цена криптовалюты\n"
                          "/start_trading - начать торговлю\n"
                          "/stop_trading - остановить торговлю\n")


@bot.message_handler(commands=['set_symbol'])
def set_crypto_command(message):
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for symbol in available_symbols:
        markup.add(symbol)
    bot.send_message(message.chat.id, "Выберите криптовалюту:", reply_markup=markup)
    bot.register_next_step_handler(message, process_symbol_selection)


def process_crypto_selection(message):
    selected_symbol = message.text.upper()
    if selected_symbol in available_symbols:
        trading_state['current_symbol'] = selected_symbol
        bot.send_message(message.chat.id, f"✅ Выбрана криптовалюта: {selected_symbol}")
    else:
        bot.send_message(message.chat.id, "❌ Эта криптовалюта недоступна. Пожалуйста, выберите из: " + ", ".join(available_symbols))


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
                              f"Всего USDT: {total}")
    else:
        bot.send_message(message.chat.id, "❌ Ошибка при получении баланса")


@bot.message_handler(commands=['price'])
def price_command(message):
    symbol = trading_state.get('current_symbol', "SUIUSDT")
    try:
        df = get_historical_data(symbol, "15")
        current_price = float(df['close'].iloc[0])
        bot.send_message(message.chat.id, f"💹 Текущая цена {symbol}: {current_price} USDT")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при получении цены: {e}")


@bot.message_handler(commands=['add_symbol'])
def add_crypto_command(message):
    bot.send_message(message.chat.id, "Введите название криптовалюты (например, BTC):")
    bot.register_next_step_handler(message, process_new_symbol)


def process_new_crypto(message):
    new_symbol = message.text.upper() + "USDT"
    if new_symbol not in available_symbols:
        available_symbols.append(new_symbol)
        bot.send_message(message.chat.id, f"✅ Криптовалюта {new_symbol} добавлена в список доступных.")
    else:
        bot.send_message(message.chat.id, "❌ Эта криптовалюта уже в списке доступных.")


def trading_bot(message, symbol=None, interval="15", qty=0.1):
    if symbol is None:
        symbol = trading_state.get('current_symbol', "SUIUSDT")
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
                f"Цена: {current_price} USDT\n"
                f"RSI: {current_rsi:.2f}\n"
                f"Волатильность: {volatility:.2f}"
            )
            bot.send_message(message.chat.id, status_message)

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
                    bot.send_message(message.chat.id, "🟢 Сигнал на покупку!")
            elif should_sell:
                if place_order(symbol, "Sell", qty):
                    trading_state['last_action'] = "Sell"
                    trading_state['consecutive_trades'] += 1
                    bot.send_message(message.chat.id, "🔴 Сигнал на продажу!")
            else:
                trading_state['consecutive_trades'] = 0

            time.sleep(60)

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
            time.sleep(60)


@bot.message_handler(commands=['start_trading'])
def start_trading_command(message):
    bot.send_message(message.chat.id, "▶️ Торговля запущена")
    trading_bot(message)


@bot.message_handler(commands=['stop_trading'])
def stop_trading_command(message):
    bot.send_message(message.chat.id, "⏹ Торговля остановлена")


def main():
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка бота: {e}")


if __name__ == "__main__":
    main()