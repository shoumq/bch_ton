import requests

def get_all_crypto():
    url = "https://api.bybit.com/v5/market/instruments-info"
    params = {
        "category": "spot"  # Указываем, что нужны данные для спотового рынка
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        # Извлекаем список символов
        if data["retCode"] == 0:
            symbols = [item["symbol"] for item in data["result"]["list"]]
            return symbols
        else:
            print(f"Ошибка API: {data['retMsg']}")
            return []
    except Exception as e:
        print(f"Ошибка при запросе к API: {e}")
        return []

if __name__ == "__main__":
    get_all_crypto()