from pathlib import Path

import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QTextEdit, QFrame, QCheckBox)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
import sys
import asyncio
from pytonlib import TonlibClient
from tonsdk.utils import Address
import logging
import json
import os
import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WalletData:
    def __init__(self):
        self.data_file = "wallet_data.json"

    def save_data(self, address: str, seed: str):
        try:
            data = {
                "address": address,
                "seed": seed
            }
            with open(self.data_file, "w", encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"Данные сохранены в {self.data_file}")
        except Exception as e:
            print(f"Ошибка при сохранении данных: {e}")

    def load_data(self) -> tuple:
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding='utf-8') as f:
                    data = json.load(f)
                    print("Данные успешно загружены")
                    return data.get("address", ""), data.get("seed", "")
            return "", ""
        except Exception as e:
            print(f"Ошибка при загрузке данных: {e}")
            return "", ""


class TonBot:
    def __init__(self, wallet_address: str, wallet_seed: str):
        self.wallet_address = Address(wallet_address)
        self.wallet_seed = wallet_seed
        self.client = None
        self.last_transaction_lt = None
        # Создаем директорию для keystore
        self.keystore_dir = os.path.join(os.path.dirname(__file__), 'keystore')
        if not os.path.exists(self.keystore_dir):
            os.makedirs(self.keystore_dir)

    async def connect(self):
        try:
            # Актуальная конфигурация для mainnet
            config = {
                'liteservers': [
                    {
                        'ip': 84478511,
                        'port': 19949,
                        'id': {
                            '@type': 'pub.ed25519',
                            'key': 'n4VDnSCUuSpjnCyUk9e3QOOd6o0ItSWYbTnW3Wnn8wk='
                        }
                    }
                ],
                'validator': {
                    '@type': 'validator.config.global',
                    'zero_state': {
                        'workchain': -1,
                        'shard': -9223372036854775808,
                        'seqno': 0,
                        'root_hash': 'F6OpKZKqvqeFp6CQmFomXNMfMj2EnaUSOXN+Mh+wVWk=',
                        'file_hash': 'XplPz01CXAps5qeSWUtxcyBfdAo5zVb1N979KLSKD24='
                    },
                    'hardforks': [
                        {
                            'file_hash': 't/9VBPODF7Zdh4nsnA49dprO69nQNMqYL+zk5bCjV/8=',
                            'seqno': 8536841,
                            'root_hash': '08Kpc9XxrMKC6BF/FeNHPS3MEL1/Vi/fQU/C9ELUrkc=',
                            'workchain': -1,
                            'shard': -9223372036854775808
                        }
                    ]
                }
            }

            # Создаем клиент с таймаутом
            self.client = TonlibClient(
                ls_index=0,
                config=config,
                keystore=self.keystore_dir  # Используем реальную директорию
            )

            # Добавляем таймаут на подключение
            await asyncio.wait_for(self.client.init(), timeout=10.0)
            logger.info("Успешное подключение к сети TON")

        except asyncio.TimeoutError:
            logger.error("Таймаут подключения к сети TON")
            raise
        except Exception as e:
            logger.error(f"Ошибка при подключении к TON: {e}")
            raise

    async def get_balance(self):
        """Получение баланса кошелька"""
        try:
            # Преобразуем адрес в строку
            address_str = self.wallet_address.to_string()
            result = await self.client.raw_get_account_state(address_str)
            if result and 'balance' in result:
                return int(result['balance']) / 1e9  # Конвертируем в TON
            return 0.0
        except Exception as e:
            logger.error(f"Ошибка при получении баланса: {e}")
            raise

    async def get_block_transactions(self, limit=50):
        """Получение последних транзакций из блокчейна"""
        try:
            # Получаем информацию о последнем мастер-блоке
            master_block = await self.client.get_masterchain_info()
            current_seqno = master_block['last']['seqno']
            
            all_transactions = []
            
            # Получаем транзакции из последних блоков
            for seqno in range(current_seqno, max(0, current_seqno - 5), -1):
                try:
                    # Получаем транзакции блока
                    block_transactions = await self.client.get_block_transactions(
                        workchain=-1,
                        shard=-9223372036854775808,
                        seqno=seqno,
                        count=20
                    )
                    
                    # Получаем время блока
                    block_info = await self.client.get_block_header(
                        workchain=-1,
                        shard=-9223372036854775808,
                        seqno=seqno
                    )
                    block_time = block_info.get('time', 0)
                    
                    for tx in block_transactions['transactions']:
                        try:
                            # Получаем детали транзакции через get_transactions
                            tx_details = await self.client.get_transactions(
                                account=tx['account'],
                                from_transaction_lt=tx['lt'],
                                count=1
                            )
                            
                            if tx_details and len(tx_details) > 0:
                                tx_detail = tx_details[0]
                                
                                tx_info = {
                                    'hash': tx['hash'],
                                    'lt': tx['lt'],
                                    'account': tx['account'],
                                    'time': block_time,
                                    'fee': 0  # Комиссия пока недоступна
                                }
                                
                                try:
                                    # Пытаемся получить сообщения
                                    if hasattr(tx_detail, 'in_msg') and tx_detail.in_msg:
                                        tx_info['type'] = 'incoming'
                                        tx_info['from'] = tx_detail.in_msg.source if hasattr(tx_detail.in_msg, 'source') else 'Неизвестно'
                                        tx_info['to'] = tx['account']
                                        tx_info['amount'] = float(tx_detail.in_msg.value) / 1e9 if hasattr(tx_detail.in_msg, 'value') else 0
                                        tx_info['message'] = tx_detail.in_msg.message if hasattr(tx_detail.in_msg, 'message') else ''
                                    else:
                                        tx_info['type'] = 'outgoing'
                                        if hasattr(tx_detail, 'out_msgs') and tx_detail.out_msgs:
                                            out_msg = tx_detail.out_msgs[0]
                                            tx_info['from'] = tx['account']
                                            tx_info['to'] = out_msg.destination if hasattr(out_msg, 'destination') else 'Неизвестно'
                                            tx_info['amount'] = float(out_msg.value) / 1e9 if hasattr(out_msg, 'value') else 0
                                            tx_info['message'] = out_msg.message if hasattr(out_msg, 'message') else ''
                                        else:
                                            tx_info['to'] = 'Неизвестно'
                                            tx_info['amount'] = 0
                                            tx_info['message'] = ''
                                except Exception as e:
                                    logger.error(f"Ошибка при обработке сообщений транзакции: {e}")
                                    tx_info.update({
                                        'type': 'unknown',
                                        'from': 'Неизвестно',
                                        'to': 'Неизвестно',
                                        'amount': 0,
                                        'message': ''
                                    })
                                
                                all_transactions.append(tx_info)
                                
                                if len(all_transactions) >= limit:
                                    return all_transactions
                                    
                        except Exception as e:
                            logger.error(f"Ошибка при получении деталей транзакции: {e}")
                            continue
                            
                except Exception as e:
                    logger.error(f"Ошибка при получении транзакций блока {seqno}: {e}")
                    continue
                    
            return all_transactions
                
        except Exception as e:
            logger.error(f"Ошибка при получении транзакций блокчейна: {e}")
            raise

    async def monitor_transactions(self, callback=None):
        """Отслеживание новых транзакций"""
        try:
            while True:
                address_str = self.wallet_address.to_string()
                transactions = await self.client.get_transactions(
                    address_str,
                    from_transaction_lt=self.last_transaction_lt,
                    limit=10
                )

                if transactions:
                    # Обрабатываем транзакции в обратном порядке (от новых к старым)
                    for tx in reversed(transactions):
                        try:
                            # Получаем transaction_lt из транзакции
                            tx_lt = tx.get('transaction_id', {}).get('lt', 0)
                            
                            if self.last_transaction_lt is None or tx_lt > self.last_transaction_lt:
                                self.last_transaction_lt = tx_lt

                            tx_info = {
                                'hash': tx.get('transaction_id', {}).get('hash', ''),
                                'lt': tx_lt,
                                'time': tx.get('utime', 0),
                                'fee': float(tx.get('fee', 0)) / 1e9,
                            }

                            # Обработка входящего сообщения
                            in_msg = tx.get('in_msg', {})
                            if in_msg:
                                tx_info['type'] = 'incoming'
                                tx_info['from'] = in_msg.get('source', 'Неизвестно')
                                tx_info['to'] = address_str
                                value = in_msg.get('value', {})
                                if isinstance(value, dict):
                                    tx_info['amount'] = float(value.get('coins', 0)) / 1e9
                                else:
                                    tx_info['amount'] = float(value or 0) / 1e9
                                tx_info['message'] = in_msg.get('message', '')
                            else:
                                # Обработка исходящего сообщения
                                tx_info['type'] = 'outgoing'
                                out_msgs = tx.get('out_msgs', [])
                                if out_msgs:
                                    out_msg = out_msgs[0]
                                    tx_info['from'] = address_str
                                    tx_info['to'] = out_msg.get('destination', 'Неизвестно')
                                    value = out_msg.get('value', {})
                                    if isinstance(value, dict):
                                        tx_info['amount'] = float(value.get('coins', 0)) / 1e9
                                    else:
                                        tx_info['amount'] = float(value or 0) / 1e9
                                    tx_info['message'] = out_msg.get('message', '')
                                else:
                                    tx_info['to'] = 'Неизвестно'
                                    tx_info['amount'] = 0
                                    tx_info['message'] = ''

                            logger.info(f"Новая транзакция: {tx_info}")
                            if callback:
                                await callback(tx_info)
                                
                        except Exception as e:
                            logger.error(f"Ошибка при обработке транзакции: {e}")
                            continue

                await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"Ошибка при мониторинге транзакций: {e}")
            raise


class WalletMonitor(QThread):
    balance_signal = pyqtSignal(float)
    transaction_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    blockchain_transactions_signal = pyqtSignal(list)

    def __init__(self, wallet_address, wallet_seed):
        super().__init__()
        self.wallet_address = wallet_address
        self.wallet_seed = wallet_seed
        self.running = True
        self.bot = None
        self.loop = None

    def run(self):
        try:
            print("Запуск мониторинга...")
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.monitor_loop())
        except Exception as e:
            print(f"Ошибка в run(): {str(e)}")
            self.error_signal.emit(f"Критическая ошибка: {str(e)}")
        finally:
            if self.loop:
                self.loop.close()

    async def load_blockchain_transactions(self):
        """Загрузка транзакций из блокчейна"""
        try:
            if not self.bot:
                return []
            transactions = await self.bot.get_block_transactions(limit=50)
            return transactions
        except Exception as e:
            logger.error(f"Ошибка при загрузке транзакций блокчейна: {e}")
            return []

    async def monitor_loop(self):
        try:
            print("Создание TonBot...")
            self.bot = TonBot(self.wallet_address, self.wallet_seed)
            print("Подключение к сети...")
            await self.bot.connect()
            print("Подключение успешно")

            while self.running:
                try:
                    print(1)
                    balance = await self.bot.get_balance()
                    print(2)
                    self.balance_signal.emit(balance)
                    print(f"Текущий баланс: {balance} TON")

                    async def tx_callback(tx_info):
                        self.transaction_signal.emit(tx_info)

                    await self.bot.monitor_transactions(callback=tx_callback)

                except Exception as e:
                    print(f"Ошибка при обновлении: {str(e)}")
                    self.error_signal.emit(f"Ошибка обновления: {str(e)}")
                    await asyncio.sleep(5)

        except Exception as e:
            print(f"Ошибка в monitor_loop(): {str(e)}")
            self.error_signal.emit(f"Ошибка мониторинга: {str(e)}")


class TonWalletApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.wallet_data = WalletData()
        self.monitoring = False
        self.monitor_thread = None
        self.initUI()

    def initUI(self):
        self.setWindowTitle("TON Wallet Monitor")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Секция настроек кошелька
        wallet_frame = QFrame()
        wallet_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        wallet_layout = QVBoxLayout(wallet_frame)

        self.wallet_address_input = QLineEdit()
        self.wallet_address_input.setPlaceholderText("Введите адрес кошелька")
        wallet_layout.addWidget(QLabel("Адрес кошелька:"))
        wallet_layout.addWidget(self.wallet_address_input)

        self.wallet_seed_input = QLineEdit()
        self.wallet_seed_input.setPlaceholderText("Введите seed-фразу")
        self.wallet_seed_input.setEchoMode(QLineEdit.EchoMode.Password)
        wallet_layout.addWidget(QLabel("Seed-фраза:"))
        wallet_layout.addWidget(self.wallet_seed_input)

        layout.addWidget(wallet_frame)

        # Чекбокс для сохранения данных
        self.save_data_checkbox = QCheckBox("Сохранить данные")
        layout.addWidget(self.save_data_checkbox)

        # Секция баланса
        balance_frame = QFrame()
        balance_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        balance_layout = QHBoxLayout(balance_frame)

        self.balance_label = QLabel("Баланс: 0 TON")
        self.balance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        balance_layout.addWidget(self.balance_label)

        layout.addWidget(balance_frame)

        # Кнопки управления
        self.start_button = QPushButton("Начать мониторинг")
        self.start_button.clicked.connect(self.toggle_monitoring)
        layout.addWidget(self.start_button)

        # Область транзакций
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(QLabel("История транзакций:"))
        layout.addWidget(self.log_area)

        # Добавляем разделитель
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(separator)

        # Создаем секцию для мониторинга сети TON
        network_frame = QFrame()
        network_frame.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        network_layout = QVBoxLayout(network_frame)

        network_label = QLabel("Мониторинг сети TON")
        network_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        network_layout.addWidget(network_label)

        buttons_layout = QHBoxLayout()

        # Кнопка для просмотра последних транзакций
        self.view_all_button = QPushButton("Последние транзакции сети")
        self.view_all_button.clicked.connect(self.view_all_transactions)
        buttons_layout.addWidget(self.view_all_button)

        # Кнопка для включения/выключения мониторинга сети
        self.network_monitor_button = QPushButton("Включить мониторинг сети")
        self.network_monitor_button.clicked.connect(self.toggle_network_monitoring)
        buttons_layout.addWidget(self.network_monitor_button)

        network_layout.addLayout(buttons_layout)
        layout.addWidget(network_frame)

        # Создаем отдельное окно для транзакций сети
        self.network_transactions = QTextEdit()
        self.network_transactions.setReadOnly(True)
        self.network_transactions.setWindowTitle("Транзакции сети TON")
        self.network_transactions.resize(800, 600)

        # Добавляем атрибут для отслеживания состояния мониторинга сети
        self.network_monitoring = False

        # Загружаем сохраненные данные
        saved_address, saved_seed = self.wallet_data.load_data()
        if saved_address and saved_seed:
            self.wallet_address_input.setText(saved_address)
            self.wallet_seed_input.setText(saved_seed)
            self.save_data_checkbox.setChecked(True)

    def toggle_monitoring(self):
        if not self.monitoring:
            wallet_address = self.wallet_address_input.text()
            wallet_seed = self.wallet_seed_input.text()

            if not wallet_address or not wallet_seed:
                self.log_area.append("❌ Ошибка: Введите адрес кошелька и seed-фразу")
                return

            # Сохраняем данные, если выбран чекбокс
            if self.save_data_checkbox.isChecked():
                self.wallet_data.save_data(wallet_address, wallet_seed)

            self.monitor_thread = WalletMonitor(wallet_address, wallet_seed)
            self.monitor_thread.balance_signal.connect(self.update_balance)
            self.monitor_thread.transaction_signal.connect(self.handle_transaction)
            self.monitor_thread.error_signal.connect(self.handle_error)
            self.monitor_thread.blockchain_transactions_signal.connect(self.display_blockchain_transactions)
            self.monitor_thread.start()

            self.start_button.setText("Остановить мониторинг")
            self.monitoring = True
            self.log_area.append("✅ Мониторинг запущен...")
        else:
            if self.monitor_thread:
                self.monitor_thread.running = False
                self.monitor_thread.quit()
                self.monitor_thread.wait()

            self.start_button.setText("Начать мониторинг")
            self.monitoring = False
            self.log_area.append("🛑 Мониторинг остановлен")

    def update_balance(self, balance):
        self.balance_label.setText(f"Баланс: {balance:.6f} TON")

    def handle_transaction(self, tx_info):
        if tx_info['type'] == 'incoming':
            message = f"📥 Получено {tx_info['amount']:.6f} TON от {tx_info['from']}"
        else:
            message = f"📤 Отправлено {tx_info['amount']:.6f} TON на {tx_info['to']}"

        self.log_area.append(f"{message}\nКомиссия: {tx_info['fee']:.6f} TON\n")

    def handle_error(self, error_message):
        self.log_area.append(f"❌ Ошибка: {error_message}")
        self.toggle_monitoring()

    def view_all_transactions(self):
        """Обработчик нажатия кнопки просмотра всех транзакций"""
        if not self.monitoring:
            self.log_area.append("❌ Сначала запустите мониторинг")
            return

        self.network_transactions.clear()
        self.network_transactions.append("🔄 Загрузка транзакций из сети...")
        self.network_transactions.show()

        async def load_and_emit():
            transactions = await self.monitor_thread.load_blockchain_transactions()
            self.monitor_thread.blockchain_transactions_signal.emit(transactions)

        if self.monitor_thread and self.monitor_thread.loop:
            future = asyncio.run_coroutine_threadsafe(
                load_and_emit(),
                self.monitor_thread.loop
            )
            # Добавляем обработку ошибок
            def callback(future):
                try:
                    future.result()
                except Exception as e:
                    self.log_area.append(f"❌ Ошибка при загрузке транзакций: {str(e)}")
            
            future.add_done_callback(callback)

    def toggle_network_monitoring(self):
        """Включение/выключение мониторинга сети"""
        if not self.monitoring:
            self.log_area.append("❌ Сначала запустите мониторинг кошелька")
            return

        if not self.network_monitoring:
            self.network_monitoring = True
            self.network_monitor_button.setText("Выключить мониторинг сети")
            self.network_transactions.clear()
            self.network_transactions.show()
            self.start_network_monitoring()
        else:
            self.network_monitoring = False
            self.network_monitor_button.setText("Включить мониторинг сети")
            self.network_transactions.hide()

    def start_network_monitoring(self):
        """Запуск постоянного мониторинга сети"""
        async def monitor_network():
            while self.network_monitoring:
                try:
                    transactions = await self.monitor_thread.load_blockchain_transactions()
                    self.monitor_thread.blockchain_transactions_signal.emit(transactions)
                    await asyncio.sleep(10)  # Обновляем каждые 10 секунд
                except Exception as e:
                    self.log_area.append(f"❌ Ошибка мониторинга сети: {str(e)}")
                    break

        if self.monitor_thread and self.monitor_thread.loop:
            future = asyncio.run_coroutine_threadsafe(
                monitor_network(),
                self.monitor_thread.loop
            )
            def callback(future):
                try:
                    future.result()
                except Exception as e:
                    self.log_area.append(f"❌ Ошибка мониторинга сети: {str(e)}")
                    self.network_monitoring = False
                    self.network_monitor_button.setText("Включить мониторинг сети")
            
            future.add_done_callback(callback)

    def display_blockchain_transactions(self, transactions):
        """Отображение транзакций блокчейна"""
        if not self.network_monitoring:
            return

        self.network_transactions.clear()
        self.network_transactions.append("=== ТРАНЗАКЦИИ СЕТИ TON ===\n")
        
        for tx in transactions:
            try:
                timestamp = datetime.datetime.fromtimestamp(tx.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S')
                
                # Безопасное получение значений с значениями по умолчанию
                tx_type = tx.get('type', 'unknown')
                tx_from = tx.get('from', 'Неизвестно')
                tx_to = tx.get('to', 'Неизвестно')
                tx_amount = float(tx.get('amount', 0))
                tx_fee = float(tx.get('fee', 0))
                tx_hash = tx.get('hash', 'Неизвестно')
                tx_message = tx.get('message', '')

                # Определяем иконку типа транзакции
                icon = '📥' if tx_type == 'incoming' else '📤' if tx_type == 'outgoing' else '❓'
                
                details = f"""
⏰ {timestamp}
{icon} {tx_from} ➜ {tx_to}
💎 Сумма: {tx_amount:.6f} TON
💸 Комиссия: {tx_fee:.6f} TON
🔗 Хеш: {tx_hash}
"""
                if tx_message:
                    details += f"📝 Сообщение: {tx_message}\n"
                
                self.network_transactions.append(f"{details}\n{'='*50}\n")
            except Exception as e:
                logger.error(f"Ошибка при отображении транзакции: {e}")
                continue
        
        # Прокручиваем до начала
        self.network_transactions.verticalScrollBar().setValue(0)


if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = QApplication(sys.argv)
    window = TonWalletApp()
    window.show()
    sys.exit(app.exec())