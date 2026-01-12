# PDF to ZenMoney

Утилита для импорта банковских выписок из PDF в ZenMoney.

## Установка

1. Установите зависимости:
```bash
pip install -r requirments.txt
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
python main.py delete --help
python main.py list-accounts --help
```
