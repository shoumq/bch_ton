import telebot
import config
from trading_bot import get_historical_data, calculate_signals, place_order, get_wallet_balance
from datetime import datetime
import time

bot = telebot.TeleBot(config.TELEGRAM_TOKEN)

trading_state = {
    'last_action': None,
    'consecutive_trades': 0
}


@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, "Привет! Я торговый бот. Используйте следующие команды:\n"
                          "/balance - проверить баланс\n"
                          "/price - текущая цена SUI\n"
                          "/start_trading - начать торговлю\n"
                          "/stop_trading - остановить торговлю")


@bot.message_handler(commands=['balance'])
def balance_command(message):
    balance = get_wallet_balance()
    if balance:
        available = balance['result']['list'][0]['totalAvailableBalance']
        total = balance['result']['list'][0]['totalWalletBalance']
        bot.reply_to(message, f"💰 Баланс кошелька:\n"
                              f"Доступно USDT: {available}\n"
                              f"Всего USDT: {total}")
    else:
        bot.reply_to(message, "❌ Ошибка при получении баланса")


@bot.message_handler(commands=['price'])
def price_command(message):
    try:
        df = get_historical_data("SUIUSDT", "15")
        current_price = float(df['close'].iloc[0])
        bot.reply_to(message, f"💹 Текущая цена SUI: {current_price} USDT")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при получении цены: {e}")


def trading_process(message, symbol="SUIUSDT", interval="15", qty=0.1):
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
                f"📊 Статус торговли:\n"
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
                bot.send_message(message.chat.id, "🟢 Сигнал на покупку!")
                if place_order(symbol, "Buy", qty):
                    trading_state['last_action'] = "Buy"
                    trading_state['consecutive_trades'] += 1
            elif should_sell:
                bot.send_message(message.chat.id, "🔴 Сигнал на продажу!")
                if place_order(symbol, "Sell", qty):
                    trading_state['last_action'] = "Sell"
                    trading_state['consecutive_trades'] += 1
            else:
                trading_state['consecutive_trades'] = 0

            time.sleep(60)

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
            time.sleep(60)


@bot.message_handler(commands=['start_trading'])
def start_trading_command(message):
    bot.reply_to(message, "▶️ Торговля запущена")
    trading_process(message)


@bot.message_handler(commands=['stop_trading'])
def stop_trading_command(message):
    bot.reply_to(message, "⏹ Торговля остановлена")


def main():
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"Ошибка бота: {e}")


if __name__ == "__main__":
    main()