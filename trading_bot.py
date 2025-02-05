from pybit.unified_trading import HTTP
import pandas as pd
import time
from datetime import datetime
import config

# Инициализация клиента Bybit
session = HTTP(
    api_key=config.API_KEY,
    api_secret=config.API_SECRET
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
    # Переименовываем колонки, так как API возвращает список значений
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
    print(f"Текущая цена: {df['close'].iloc[0]}")  # Выводим последнюю цену
    print(f"Последние цены:\n{df['close'].head()}")  # Выведет первые 5 цен
    df['close'] = df['close'].astype(float)
    return df

def calculate_signals(df):
    """Расчет торговых сигналов на основе SMA"""
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()
    return df

def place_order(symbol, side, qty):
    """Размещение ордера"""
    try:
        order = session.place_order(
            category="spot",
            symbol=symbol,
            side=side,
            orderType="Market",
            qty=str(qty),
            timeInForce="GTC"
        )
        print(f"Ордер размещен: {order}")
        return order
    except Exception as e:
        print(f"Ошибка при размещении ордера: {e}")
        return None

def trading_bot(symbol="BTCUSDT", interval="15", qty=0.001):
    """Основная логика торгового бота"""
    while True:
        try:
            # Получение данных
            df = get_historical_data(symbol, interval)
            df = calculate_signals(df)
            
            # Получение последних значений SMA
            last_sma20 = df['SMA20'].iloc[-1]
            last_sma50 = df['SMA50'].iloc[-1]
            
            # Торговая логика
            if last_sma20 > last_sma50:  # Сигнал на покупку
                place_order(symbol, "Buy", qty)
            elif last_sma20 < last_sma50:  # Сигнал на продажу
                place_order(symbol, "Sell", qty)
                
            print(f"Проверка сигналов завершена: {datetime.now()}")
            time.sleep(60)  # Пауза 1 минута
            
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(60)

if __name__ == "__main__":
    print(get_historical_data("BTCUSDT", "15"))
    trading_bot() 