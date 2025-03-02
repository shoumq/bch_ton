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

# Конфигурация параметров
STOP_LOSS_PERCENT = 0.02
TAKE_PROFIT_PERCENT = 0.03
MAX_VOLATILITY_PERCENT = 0.05
RSI_OVERBOUGHT = 65
RSI_OVERSOLD = 35

def get_historical_data(symbol, interval, limit=200):
    """Улучшенная обработка данных с проверкой типов"""
    response = session.get_kline(
        category="spot",
        symbol=symbol,
        interval=interval,
        limit=limit
    )

    df = pd.DataFrame(response['result']['list'])
    df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
    df = df.iloc[::-1].reset_index(drop=True)

    # Явное преобразование всех числовых столбцов
    numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'turnover']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')  # Автоматическая обработка ошибок

    # Удаление строк с пропущенными значениями
    df.dropna(inplace=True)
    
    return df

def calculate_signals(df):
    """Улучшенный расчет сигналов с добавлением Volume_SMA20"""
    required_columns = ['close', 'volume']
    
    # Проверка наличия необходимых колонок
    for col in required_columns:
        if col not in df.columns:
            raise ValueError(f"Отсутствует обязательная колонка: {col}")

    try:
        # Скользящие средние для цены
        df['SMA20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['SMA50'] = df['close'].rolling(window=50, min_periods=1).mean()
        
        # Экспоненциальные скользящие средние
        df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # Скользящая средняя для объема
        df['Volume_SMA20'] = df['volume'].rolling(window=20, min_periods=1).mean()
        
        # RSI с защитой от нулевых значений
        delta = df['close'].diff().fillna(0)
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        avg_gain = gain.rolling(window=14, min_periods=1).mean()
        avg_loss = loss.rolling(window=14, min_periods=1).mean().replace(0, 1)
        
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs)).fillna(50)  # Заполняем нейтральным значением при ошибках

        # Волатильность с минимальным периодом
        df['volatility'] = df['close'].rolling(window=20, min_periods=5).std().bfill()
        
        # MACD с проверкой на достаточность данных
        if len(df) >= 26:
            exp1 = df['close'].ewm(span=12, adjust=False).mean()
            exp2 = df['close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = exp1 - exp2
            df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        else:
            df['MACD'] = 0.0
            df['Signal_Line'] = 0.0
    
        return df

    except Exception as e:
        print(f"Ошибка расчета сигналов: {str(e)}")
        print("Сырые данные для отладки:")
        print(df.tail().to_string())
        raise

def place_order(symbol, side, qty):
    """Улучшенная функция размещения ордера со стоп-лоссом и тейк-профитом"""
    try:
        df = get_historical_data(symbol, "1", 1)
        current_price = df['close'].iloc[0]
        print(f"Current price: {current_price}")

        price = round(current_price * 1.001, 4)
        qty = max(0.1, round(qty, 1))

        order_params = {
            'category': 'spot',
            'symbol': symbol,
            'side': side,
            'orderType': 'Limit',
            'price': str(price),
            'qty': str(qty),
            'timeInForce': 'GTC'
        }

        # Расчет уровней стоп-лосса и тейк-профита
        if side == 'Buy':
            sl_price = round(current_price * (1 - STOP_LOSS_PERCENT), 4)
            tp_price = round(current_price * (1 + TAKE_PROFIT_PERCENT), 4)
        else:
            sl_price = round(current_price * (1 + STOP_LOSS_PERCENT), 4)
            tp_price = round(current_price * (1 - TAKE_PROFIT_PERCENT), 4)

        order_params.update({
            'slTriggerBy': 'LastPrice',
            'slPrice': str(sl_price),
            'tpTriggerBy': 'LastPrice',
            'tpPrice': str(tp_price)
        })

        order = session.place_order(**order_params)
        
        f = open('log.txt','r+')
        f.write(f"{datetime.now()}: {order}\n")
        f.close()
        
        print(f"Ордер размещен: {order}")
        print(f"Стоп-лосс: {sl_price}, Тейк-профит: {tp_price}")
        return order
    except Exception as e:
        print(f"Ошибка при размещении ордера: {e}")
        return None

def trading_bot(symbol="SUIUSDT", interval="15", base_qty=3):
    """Обновленная основная логика с дополнительными проверками"""
    last_action = None
    consecutive_trades = 0

    while True:
        try:
            df = get_historical_data(symbol, interval)
            if df.empty:
                print("Нет данных для анализа. Ожидание...")
                time.sleep(60)
                continue

            df = calculate_signals(df)
            
            # Проверка наличия всех необходимых колонок
            required_columns = ['close', 'SMA20', 'EMA20', 'SMA50', 'RSI', 'volatility']
            for col in required_columns:
                if col not in df.columns:
                    raise ValueError(f"Отсутствует обязательная колонка: {col}")

            current_price = df['close'].iloc[-1]
            volatility = df['volatility'].iloc[-1]
            current_rsi = df['RSI'].iloc[-1]

            # Динамическое управление размером позиции
            volatility_multiplier = 1 - min(volatility / (current_price * MAX_VOLATILITY_PERCENT), 0.5)
            qty = max(0.1, round(base_qty * volatility_multiplier, 1))

            # Формирование сигналов
            trend_condition = (
                (df['SMA20'].iloc[-1] > df['SMA50'].iloc[-1]) and
                (df['EMA20'].iloc[-1] > df['EMA50'].iloc[-1]) and
                (df['MACD'].iloc[-1] > df['Signal_Line'].iloc[-1])
            )

            volume_condition = df['volume'].iloc[-1] > df['Volume_SMA20'].iloc[-1]

            should_buy = (
                trend_condition and
                volume_condition and
                (current_rsi < RSI_OVERSOLD) and
                (consecutive_trades < 2) and
                (last_action != "Buy")
            )

            should_sell = (
                (not trend_condition) and
                (current_rsi > RSI_OVERBOUGHT) and
                (consecutive_trades < 2) and
                (last_action != "Sell")
            )

            if should_buy:
                print(f"BUY SIGNAL: Price {current_price}, RSI {current_rsi:.1f}")
                if place_order(symbol, "Buy", qty):
                    last_action = "Buy"
                    consecutive_trades += 1
            elif should_sell:
                print(f"SELL SIGNAL: Price {current_price}, RSI {current_rsi:.1f}")
                if place_order(symbol, "Sell", qty):
                    last_action = "Sell"
                    consecutive_trades += 1
            else:
                consecutive_trades = 0

            print(f"Проверка завершена: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(60)

        except Exception as e:
            print(f"Критическая ошибка: {str(e)}")
            time.sleep(60)

def get_wallet_balance():
    """Получение баланса с обработкой ошибок"""
    try:
        balance = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
        available = float(balance['result']['list'][0]['totalAvailableBalance'])
        total = float(balance['result']['list'][0]['totalWalletBalance'])
        print(f"Доступно: {available:.2f} USDT, Всего: {total:.2f} USDT")
        return available, total
    except Exception as e:
        print(f"Ошибка получения баланса: {e}")
        return None, None

if __name__ == "__main__":
    print("Запуск улучшенного торгового бота...")
    print(f"Настройки риска: SL {STOP_LOSS_PERCENT*100}%, TP {TAKE_PROFIT_PERCENT*100}%")
    trading_bot()