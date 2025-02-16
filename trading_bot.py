import telebot
import os
from pybit.unified_trading import HTTP
import pandas as pd
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

session = HTTP(
    api_key=os.getenv("API_KEY"),
    api_secret=os.getenv("API_SECRET")
)

def get_historical_data(symbol, interval, limit=200):
    """Получение исторических данных"""
    response = session.get_kline(
        category="spot",
        symbol=symbol,
        interval=interval,
        limit=limit
    )

    df = pd.DataFrame(response['result']['list'])
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
    print(f"Текущая цена: {df['close'].iloc[0]}")
    df['close'] = df['close'].astype(float)
    return df


def calculate_signals(df):
    """Расчет торговых сигналов на основе SMA и дополнительных индикаторов"""

    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    df['volatility'] = df['close'].rolling(window=20).std()
    return df


def place_order(symbol, side, qty):
    """Размещение ордера"""
    try:
        current_price = float(get_historical_data(symbol, "1")['close'].iloc[0])
        print(f"Current price: {current_price}")

        price = round(current_price * 1.001, 3)

        order = session.place_order(
            category="spot",
            symbol=symbol,
            side=side,
            orderType="Limit",
            price=str(price),
            qty=str(qty),
            timeInForce="GTC"
        )
        print(f"Количество: {qty}")
        print(f"Цена: {price}")
        print(f"Ордер размещен: {order}")
        return order
    except Exception as e:
        print(f"Ошибка при размещении ордера: {e}")
        return None


def place_order_for_usdt(symbol, side, usdt_amount):
    """Размещение спотового ордера на определенную сумму USDT"""
    try:
        current_price = float(get_historical_data(symbol, "1")['close'].iloc[0])
        print(f"Current price: {current_price}")

        sui_amount = usdt_amount / current_price
        contract_qty = round(sui_amount * 10)
        contract_qty = max(1, min(contract_qty, 30))

        real_usdt_amount = (contract_qty / 10) * current_price
        if real_usdt_amount > usdt_amount * 1.1:
            contract_qty = max(1, round((usdt_amount / current_price) * 10))

        order = session.place_order(
            category="spot",
            symbol=symbol,
            side=side,
            orderType="Limit",
            price=str(round(current_price * 1.001, 4)),
            qty=str(contract_qty / 10),
            timeInForce="GTC"
        )
        real_usdt_amount = (contract_qty / 10) * current_price
        print(f"Количество SUI: {contract_qty / 10}")
        print(f"Сумма USDT: {round(real_usdt_amount, 2)}")
        print(f"Ордер размещен: {order}")
        return order
    except Exception as e:
        print(f"Ошибка при размещении ордера: {e}")
        return None


def trading_bot(symbol="SUIUSDT", interval="15", qty=0.1):
    """Основная логика торгового бота"""
    last_action = None
    consecutive_trades = 0

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

            print(f"Текущая цена: {current_price} USDT")
            print(f"RSI: {current_rsi:.2f}")
            print(f"Волатильность: {volatility:.2f}")

            should_buy = (
                    last_sma20 > last_sma50 and
                    current_rsi < 70 and
                    consecutive_trades < 3 and
                    last_action != "Buy"
            )

            should_sell = (
                    last_sma20 < last_sma50 and
                    current_rsi > 30 and
                    consecutive_trades < 3 and
                    last_action != "Sell"
            )

            if should_buy:
                print("BUY!")
                if place_order(symbol, "Buy", qty):
                    last_action = "Buy"
                    consecutive_trades += 1
            elif should_sell:
                print("SELL")
                if place_order(symbol, "Sell", qty):
                    last_action = "Sell"
                    consecutive_trades += 1
            else:
                consecutive_trades = 0

            print(f"Проверка сигналов завершена: {datetime.now()}")
            time.sleep(60)

        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(60)


def get_wallet_balance():
    """Получение баланса кошелька"""
    try:
        balance = session.get_wallet_balance(
            accountType="UNIFIED",
            coin="USDT"
        )
        print("\nБаланс кошелька:")
        print(f"Доступно USDT: {balance['result']['list'][0]['totalAvailableBalance']}")
        print(f"Всего USDT: {balance['result']['list'][0]['totalWalletBalance']}")
        return balance
    except Exception as e:
        print(f"Ошибка при получении баланса: {e}")
        return None


if __name__ == "__main__":
    trading_bot()