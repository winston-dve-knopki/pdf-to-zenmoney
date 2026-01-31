# PDF to ZenMoney

Утилита для импорта банковских выписок из PDF в ZenMoney.

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` в корне проекта:
```
ZEN_TOKEN=ваш_токен_zenmoney
```

Токен можно получить через [Zerro.app](https://zerro.app) или зарегистрировав свое приложение в ZenMoney.

## Использование

### Импорт транзакций из PDF

```bash
python main.py import-transactions путь/к/файлу.pdf --account "название счета"
```

Пример:
```bash
python main.py import-transactions ~/Downloads/bank_statement.pdf --account "yandex bank"
```

**Опции:**
- `--account` (обязательно) - название счета в ZenMoney
- `--dry-run` - показать транзакции без отправки в ZenMoney

### Удаление транзакций

```bash
# Удалить все транзакции на определенном счете
python main.py delete --account "yandex bank"

# Удалить транзакции за период
python main.py delete --start-date "2025-07-01" --end-date "2025-11-30"

# Удалить транзакции на счете за период
python main.py delete --account "yandex bank" --start-date "2025-07-01" --end-date "2025-11-30"

# Удалить ВСЕ транзакции (осторожно!)
python main.py delete --all
```

### Просмотр счетов

```bash
python main.py list-accounts
```

Показывает список всех счетов в ZenMoney с их ID и валютами.

### Экспорт транзакций в CSV

Скачать все транзакции из ZenMoney и сохранить в CSV для анализа (доход, расход, сумма, категория, комментарий, получатель, счёт, валюта).

```bash
# Все транзакции
python main.py export --output transactions.csv

# Только один счёт
python main.py export --output transactions.csv --account "yandex bank"

# За период
python main.py export --output transactions.csv --start-date "2025-01-01" --end-date "2025-12-31"

# Счёт и период
python main.py export -o report.csv --account "yandex bank" --start-date "2025-07-01" --end-date "2025-11-30"
```

**Колонки CSV:** date, income, outcome, amount, currency, comment, payee, category, account, id. Суммы в рублях.

### Аналитика: HTML с графиками по CSV

Скрипт находит все CSV в репозитории, объединяет их и генерирует одностраничный HTML с графиками Plotly. Удобно захостить на любом статическом хостинге (GitHub Pages, Netlify и т.д.).

```bash
# По умолчанию ищет CSV в текущей папке, результат — analytics.html
python prepare_analytics_html.py

# Указать папку с CSV и выходной файл
python prepare_analytics_html.py --csv-dir . -o analytics.html

# Топ 5 категорий вместо 3
python prepare_analytics_html.py --top 5 -o report.html
```

**Что в отчёте:**
- Сводка: сумма доходов, расходов и баланс
- Area-график расходов по дням/неделям (переключатель): топ N категорий + «Остальное»
- Горизонтальный bar по категориям (доли расходов)
- Таблица: топ категории и крупные траты в каждой

Файл один (`analytics.html`), подключает Plotly с CDN — можно открыть локально или выложить на сервер.

**Как посмотреть отчёт:**

- **В Cursor/VS Code:** установите расширение **Live Preview** (Microsoft) → откройте `analytics.html` → правый клик по вкладке → «Show Preview» (или кнопка «Show Preview» справа вверху).
- **Просто открыть в браузере:** дважды кликните по `analytics.html` в проводнике или выполните в терминале:
  ```bash
  open analytics.html          # macOS
  start analytics.html         # Windows
  xdg-open analytics.html     # Linux
  ```
- **Локальный сервер одной командой** (удобно, если браузер ругается на file://):
  ```bash
  python -m http.server 8000
  ```
  Затем откройте в браузере: **http://localhost:8000/analytics.html** (остановить сервер: Ctrl+C).

## Примеры

### Полный цикл: импорт и проверка

```bash
# 1. Посмотреть доступные счета
python main.py list-accounts

# 2. Предпросмотр транзакций (без отправки)
python main.py import-transactions statement.pdf --account "yandex bank" --dry-run

# 3. Импорт транзакций
python main.py import-transactions statement.pdf --account "yandex bank"

# 4. Если что-то пошло не так - удалить транзакции
python main.py delete --account "yandex bank"
```

## Поддерживаемые форматы

Утилита поддерживает выписки из:
- Яндекс Банк
- Другие банки с похожим форматом выписки

Формат выписки должен содержать:
- Описание операции
- Дата и время операции
- Дата обработки
- Сумма операции
- Номер карты (опционально)

## Помощь

Для просмотра всех доступных команд:
```bash
python main.py --help
```

Для помощи по конкретной команде:
```bash
python main.py import-transactions --help
python main.py export --help
python main.py delete --help
python main.py list-accounts --help
```
