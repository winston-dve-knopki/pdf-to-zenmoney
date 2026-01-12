import typing as tp
import PyPDF2
import re
import requests
import os
import uuid
import click
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any

def pdf_to_text(file_path: str) -> str:
    with open(file_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text

def parse_bank_statement(text: str) -> List[Dict[str, Any]]:
    """
    Парсит текст банковской выписки и извлекает транзакции в CSV формат.
    """
    
    transactions = []
    
    # Удаляем служебную информацию
    text = re.sub(r'Страница \d+ из \d+', '', text)
    text = re.sub(r'Продолжение на следующей странице', '', text)
    text = re.sub(r'Входящий остаток.*?₽', '', text)
    text = re.sub(r'Исходящий остаток.*?₽', '', text)
    
    # Паттерн для поиска транзакций
    # Ищем: описание + дата_время + дата_обработки + (карта?) + сумма1 + сумма2
    # Используем более точный паттерн
    
    # Разбиваем по паттерну даты и времени операции
    # Формат: DD.MM.YYYY в HH:MM
    pattern = r'(\d{2}\.\d{2}\.\d{4})\s+в\s+(\d{2}:\d{2})'
    
    # Находим все совпадения с их позициями
    matches = list(re.finditer(pattern, text))
    
    for i, match in enumerate(matches):
        # Позиция начала даты
        date_start = match.start()
        date_str = match.group(1)
        time_str = match.group(2)
        transaction_datetime = f"{date_str} в {time_str}"
        
        # Текст до этой даты - это описание
        if i == 0:
            prev_end = 0
        else:
            prev_end = matches[i-1].end()
        
        description = text[prev_end:date_start].strip()
        # Удаляем суммы из конца описания
        description = re.sub(r'[+\-–]\s*\d.*?₽\s*$', '', description, flags=re.MULTILINE)
        description = re.sub(r'\s+', ' ', description).strip()
        
        # Текст после даты содержит остальные данные
        after_date = text[match.end():]
        
        # Извлекаем дату обработки (следующая дата после даты операции)
        processing_date_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', after_date)
        if not processing_date_match:
            continue
        processing_date = processing_date_match.group(1)
        
        # Извлекаем карту (опционально)
        card_match = re.search(r'\*(\d{4,5})', after_date)
        card = '*' + card_match.group(1) if card_match else ''
        
        # Извлекаем две суммы
        amount_pattern = r'([+\-–])\s*(\d{1,3}(?:\s+\d{3})*(?:,\d{2})?)\s*₽'
        amounts = re.findall(amount_pattern, after_date)
        
        if len(amounts) < 2:
            continue
        
        # Очищаем суммы
        def clean_amount(sign, value):
            cleaned = value.replace(' ', '').replace(',', '.')
            # Заменяем длинное тире на минус
            if sign == '–':
                sign = '-'
            return sign + cleaned
        
        transaction_amount = clean_amount(amounts[0][0], amounts[0][1])
        account_amount = clean_amount(amounts[1][0], amounts[1][1])
        
        # Пропускаем служебные строки
        if any(word in description for word in ['Описание операции', 'Дата и время', 'МСК', 'Страница']):
            continue
        
        if len(description) < 5:
            continue
        
        transactions.append({
            'Description': description,
            'Transaction_DateTime': transaction_datetime,
            'Processing_Date': processing_date,
            'Card': card,
            'Transaction_Amount': transaction_amount,
            'Account_Amount': account_amount
        })
    print(f"{len(transactions)} transactions found")
    return transactions

def get_zenmoney_data(access_token: str) -> tp.Dict[str, tp.Any]:
    """
    Получает данные из ZenMoney (счета, инструменты, пользователь).
    
    Args:
        access_token: OAuth токен доступа
    
    Returns:
        Словарь с данными из ZenMoney API
    """
    url = "https://api.zenmoney.ru/v8/diff/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "currentClientTimestamp": int(datetime.now().timestamp()),
        "serverTimestamp": 0
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Ошибка получения данных: {response.status_code} - {response.text}")


def convert_to_zenmoney_format(
    transactions: tp.List[tp.Dict[str, tp.Any]], 
    account_title: str,
    access_token: str
) -> tp.List[tp.Dict[str, tp.Any]]:
    """
    Конвертирует транзакции из формата словарей в формат ZenMoney API.
    
    Args:
        transactions: Список транзакций с полями:
                     - Description: описание транзакции
                     - Processing_Date: дата в формате 'DD.MM.YYYY'
                     - Account_Amount: сумма в формате '+1200.00' или '-500.00'
        account_id: ID счета в ZenMoney для всех транзакций
        access_token: OAuth токен для получения данных о валюте
    
    Returns:
        Список транзакций в формате ZenMoney API
    """
    # Получаем данные из ZenMoney для получения ID валюты и пользователя
    zenmoney_data = get_zenmoney_data(access_token)
    account_id = [account.get('id') for account in zenmoney_data.get('account', []) if account.get('title') == account_title]
    if not account_id:
        raise ValueError(f"Не найден счет с названием {account_title}")
    account_id = account_id[0]

    instruments = zenmoney_data.get('instrument', [])
    users = zenmoney_data.get('user', [])
    user_id = users[0].get('id', 1) if users else 1
    
    # Находим рубль
    rub_instrument = None
    for inst in instruments:
        if inst.get('shortTitle') == 'RUB' or inst.get('title') == 'Российский рубль':
            rub_instrument = inst.get('id')
            break
    
    if not rub_instrument:
        raise ValueError("Не найден инструмент для рубля")
    
    zenmoney_transactions = []
    current_timestamp = int(datetime.now().timestamp())
    
    for txn in transactions:
        description = txn.get('Description', '').strip()
        date_str = txn.get('Processing_Date', '') or txn.get('Transaction_DateTime', '')
        amount_str = txn.get('Account_Amount', '') or txn.get('Transaction_Amount', '')
        
        # Пропускаем пустые строки
        if not description or not date_str or not amount_str:
            print(f"Skipping empty transaction: {description}, {date_str}, {amount_str}")
            continue
        
        # Конвертируем дату из формата '27.07.2025' в '2025-07-27'
        date = None
        
        # Очищаем строку от лишних пробелов и символов
        date_str_clean = date_str.strip()
        
        # Пробуем разные варианты парсинга
        date_formats = [
            '%d.%m.%Y',           # 27.07.2025
            '%d.%m.%Y в %H:%M',   # 27.07.2025 в 08:16
            '%Y-%m-%d',           # 2025-07-27 (уже правильный формат)
            '%d/%m/%Y',           # 27/07/2025
            '%Y.%m.%d',           # 2025.07.27
        ]
        
        # Сначала пробуем разделить по " в " для формата с временем
        date_parts = date_str_clean.split(' в ')
        date_part = date_parts[0].strip() if date_parts else date_str_clean
        
        # Пробуем распарсить разными форматами
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_part, fmt)
                date = dt.strftime('%Y-%m-%d')
                break
            except (ValueError, AttributeError):
                continue
        
        # Если не получилось, пробуем извлечь дату регулярным выражением
        if not date:
            # Ищем паттерн DD.MM.YYYY или DD/MM/YYYY
            date_match = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', date_str_clean)
            if date_match:
                try:
                    day, month, year = date_match.groups()
                    # Проверяем валидность даты (день должен быть 1-31, месяц 1-12)
                    day_int = int(day)
                    month_int = int(month)
                    year_int = int(year)
                    
                    # Если день > 12, то это точно день (не месяц)
                    # Иначе пробуем оба варианта: день.месяц.год или месяц.день.год
                    if day_int > 12:
                        # Точный формат: день.месяц.год
                        dt = datetime(year_int, month_int, day_int)
                        date = dt.strftime('%Y-%m-%d')
                    elif month_int > 12:
                        # Формат: месяц.день.год (американский) - переставляем
                        dt = datetime(year_int, day_int, month_int)
                        date = dt.strftime('%Y-%m-%d')
                    else:
                        # Пробуем оба варианта, начиная с российского формата
                        try:
                            dt = datetime(year_int, month_int, day_int)
                            date = dt.strftime('%Y-%m-%d')
                        except ValueError:
                            # Пробуем американский формат
                            dt = datetime(year_int, day_int, month_int)
                            date = dt.strftime('%Y-%m-%d')
                except (ValueError, AttributeError) as e:
                    print(f"Error creating date from regex match: {e}, day={day}, month={month}, year={year}")
        
        if not date:
            print(f"Error parsing date: '{date_str}' (cleaned: '{date_str_clean}')")
            continue
        
        # Парсим сумму: конвертируем из '+1200.00' в рубли (суммы уже в рублях)
        amount_clean = None
        try:
            # Очищаем строку: убираем все пробелы и whitespace символы
            amount_clean = ''.join(amount_str.split())
            
            # Определяем знак
            is_negative = amount_clean.startswith('-') or amount_clean.startswith('–')
            is_positive = amount_clean.startswith('+')
            
            # Убираем знаки из начала строки
            if is_negative or is_positive:
                amount_clean = amount_clean[1:]
            
            # Заменяем запятую на точку (для десятичного разделителя)
            amount_clean = amount_clean.replace(',', '.')
            
            # Парсим число
            amount_float = float(amount_clean)
            
            # Применяем знак
            if is_negative:
                amount_float = -abs(amount_float)
            else:
                amount_float = abs(amount_float)
            
            # Суммы уже в рублях
            # ZenMoney API ожидает суммы в копейках, но по факту суммы уже в правильном формате
            # Убираем умножение на 100, так как суммы уже в нужном формате
            amount_in_cents = int(round(amount_float))
        except Exception as e:
            cleaned_info = amount_clean if amount_clean is not None else 'N/A'
            print(f"Error parsing amount: '{amount_str}' -> cleaned: '{cleaned_info}' - {e}")
            continue
        
        if amount_in_cents == 0:
            continue
        
        # Определяем доход или расход
        is_income = amount_str.startswith('+')
        
        # Извлекаем получателя из описания (опционально)
        payee = None
        comment = description
        
        # Паттерны для извлечения получателя
        payee_patterns = [
            r'Входящий перевод СБП, ([^,]+)',
            r'Исходящий перевод СБП, ([^,]+)',
            r'Оплата товаров и услуг ([A-Z_0-9]+)',
        ]
        
        for pattern in payee_patterns:
            match = re.search(pattern, description)
            if match:
                payee = match.group(1).strip()
                break
        
        # Создаем транзакцию в формате ZenMoney
        transaction = {
            'id': str(uuid.uuid4()),
            'changed': current_timestamp,
            'created': current_timestamp,
            'user': user_id,
            'deleted': False,
            'incomeInstrument': rub_instrument,
            'incomeAccount': account_id if is_income else None,
            'incomeBankID': None,
            'income': amount_in_cents if is_income else 0,
            'outcomeInstrument': rub_instrument,
            'outcomeAccount': account_id if not is_income else None,
            'outcomeBankID': None,
            'outcome': abs(amount_in_cents) if not is_income else 0,
            'tag': [],
            'merchant': None,
            'payee': payee,
            'originalPayee': None,
            'comment': comment,
            'date': date,
            'mcc': None,
            'reminderMarker': None,
            'opIncome': None,
            'opIncomeInstrument': None,
            'opOutcome': None,
            'opOutcomeInstrument': None,
            'latitude': None,
            'longitude': None
        }
        
        zenmoney_transactions.append(transaction)
    print(f"{len(zenmoney_transactions)} transactions converted")
    return zenmoney_transactions

def post_transactions(
    transactions: tp.List[tp.Dict[str, tp.Any]], 
    access_token: str
) -> tp.Dict[str, tp.Any]:
    """
    Отправляет транзакции в ZenMoney через Diff API.
    
    Args:
        transactions: Список транзакций в формате ZenMoney API
        access_token: OAuth токен доступа
    
    Returns:
        Ответ от API ZenMoney
    """
    url = "https://api.zenmoney.ru/v8/diff/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Получаем serverTimestamp из текущих данных
    zenmoney_data = get_zenmoney_data(access_token)
    server_timestamp = zenmoney_data.get('serverTimestamp', 0)
    
    current_timestamp = int(datetime.now().timestamp())
    
    payload = {
        "currentClientTimestamp": current_timestamp,
        "serverTimestamp": server_timestamp,
        "transaction": transactions
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Ошибка отправки транзакций: {response.status_code} - {response.text}")


def delete_transactions(
    access_token: str,
    account_title: str = None,
    start_date: str = None,
    end_date: str = None
) -> tp.Dict[str, tp.Any]:
    """
    Удаляет транзакции из ZenMoney.
    
    Args:
        access_token: OAuth токен доступа
        account_title: Название счета (если указано, удаляет только транзакции этого счета)
        start_date: Начальная дата в формате 'YYYY-MM-DD' (если указано, удаляет только транзакции после этой даты)
        end_date: Конечная дата в формате 'YYYY-MM-DD' (если указано, удаляет только транзакции до этой даты)
    
    Returns:
        Ответ от API ZenMoney
    """
    # Получаем все данные из ZenMoney
    zenmoney_data = get_zenmoney_data(access_token)
    server_timestamp = zenmoney_data.get('serverTimestamp', 0)
    
    transactions = zenmoney_data.get('transaction', [])
    accounts = zenmoney_data.get('account', [])
    users = zenmoney_data.get('user', [])
    user_id = users[0].get('id', 1) if users else 1
    
    # Находим account_id если указано название счета
    account_id = None
    if account_title:
        account_ids = [acc.get('id') for acc in accounts if acc.get('title') == account_title]
        if account_ids:
            account_id = account_ids[0]
        else:
            raise ValueError(f"Не найден счет с названием {account_title}")
    
    # Фильтруем транзакции для удаления
    transactions_to_delete = []
    
    for txn in transactions:
        # Пропускаем уже удаленные транзакции
        if txn.get('deleted', False):
            continue
        
        # Фильтр по счету
        if account_id:
            txn_account = txn.get('incomeAccount') or txn.get('outcomeAccount')
            if txn_account != account_id:
                continue
        
        # Фильтр по дате
        txn_date = txn.get('date', '')
        if start_date and txn_date < start_date:
            continue
        if end_date and txn_date > end_date:
            continue
        
        transactions_to_delete.append(txn)
    
    if not transactions_to_delete:
        print("Нет транзакций для удаления")
        return {}
    
    print(f"Найдено транзакций для удаления: {len(transactions_to_delete)}")
    
    # Создаем объекты для удаления
    # Согласно документации, можно использовать либо deletion, либо транзакции с deleted: true
    current_timestamp = int(datetime.now().timestamp())
    
    deleted_transactions = []
    for txn in transactions_to_delete:
        deleted_txn = {
            'id': txn.get('id'),
            'changed': current_timestamp,
            'created': txn.get('created', current_timestamp),
            'user': user_id,
            'deleted': True,
            'incomeInstrument': txn.get('incomeInstrument'),
            'incomeAccount': txn.get('incomeAccount'),
            'incomeBankID': txn.get('incomeBankID'),
            'income': txn.get('income', 0),
            'outcomeInstrument': txn.get('outcomeInstrument'),
            'outcomeAccount': txn.get('outcomeAccount'),
            'outcomeBankID': txn.get('outcomeBankID'),
            'outcome': txn.get('outcome', 0),
            'tag': txn.get('tag', []),
            'merchant': txn.get('merchant'),
            'payee': txn.get('payee'),
            'originalPayee': txn.get('originalPayee'),
            'comment': txn.get('comment', ''),
            'date': txn.get('date'),
            'mcc': txn.get('mcc'),
            'reminderMarker': txn.get('reminderMarker'),
            'opIncome': txn.get('opIncome'),
            'opIncomeInstrument': txn.get('opIncomeInstrument'),
            'opOutcome': txn.get('opOutcome'),
            'opOutcomeInstrument': txn.get('opOutcomeInstrument'),
            'latitude': txn.get('latitude'),
            'longitude': txn.get('longitude')
        }
        deleted_transactions.append(deleted_txn)
    
    # Отправляем запрос на удаление
    url = "https://api.zenmoney.ru/v8/diff/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "currentClientTimestamp": current_timestamp,
        "serverTimestamp": server_timestamp,
        "transaction": deleted_transactions
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        print(f"Успешно удалено транзакций: {len(transactions_to_delete)}")
        return result
    else:
        raise Exception(f"Ошибка удаления транзакций: {response.status_code} - {response.text}")


@click.group()
@click.option('--token', default=None, help='ZenMoney API токен (можно указать через переменную окружения ZEN_TOKEN)')
@click.pass_context
def cli(ctx, token):
    """Утилита для импорта банковских выписок в ZenMoney."""
    ctx.ensure_object(dict)
    
    # Загружаем переменные окружения из .env файла
    load_dotenv()
    
    # Получаем токен: сначала из аргумента, потом из переменной окружения
    if not token:
        token = os.getenv('ZEN_TOKEN')
    
    if not token:
        raise click.ClickException(
            "Токен не указан. Укажите через:\n"
            "  - аргумент --token\n"
            "  - переменную окружения ZEN_TOKEN\n"
            "  - файл .env с ZEN_TOKEN=ваш_токен"
        )
    
    ctx.obj['token'] = token


@cli.command()
@click.argument('pdf_file', type=click.Path(exists=True, path_type=Path))
@click.option('--account', required=True, help='Название счета в ZenMoney (например: "yandex bank")')
@click.option('--dry-run', is_flag=True, help='Показать транзакции без отправки в ZenMoney')
@click.pass_context
def import_transactions(ctx, pdf_file, account, dry_run):
    """Импортировать транзакции из PDF файла банковской выписки."""
    token = ctx.obj['token']
    
    click.echo(f"Читаю PDF файл: {pdf_file}")
    text = pdf_to_text(str(pdf_file))
    
    click.echo("Парсю транзакции из выписки...")
    transactions = parse_bank_statement(text)
    click.echo(f"Найдено транзакций: {len(transactions)}")
    
    if not transactions:
        click.echo("Транзакции не найдены в файле", err=True)
        return
    
    click.echo(f"Конвертирую транзакции для счета '{account}'...")
    try:
        zenmoney_transactions = convert_to_zenmoney_format(transactions, account, token)
        click.echo(f"Готово к отправке: {len(zenmoney_transactions)} транзакций")
    except Exception as e:
        click.echo(f"Ошибка конвертации: {e}", err=True)
        raise click.Abort()
    
    if dry_run:
        click.echo("\n=== ПРЕДПРОСМОТР ТРАНЗАКЦИЙ (dry-run) ===")
        for i, txn in enumerate(zenmoney_transactions[:10], 1):
            click.echo(f"{i}. {txn['date']} | {txn['comment'][:50]} | "
                      f"{'+' if txn['income'] > 0 else '-'}{abs(txn['income'] or txn['outcome'])/100:.2f} руб")
        if len(zenmoney_transactions) > 10:
            click.echo(f"... и еще {len(zenmoney_transactions) - 10} транзакций")
        click.echo("\nДля отправки запустите без флага --dry-run")
        return
    
    if not click.confirm(f'Отправить {len(zenmoney_transactions)} транзакций в ZenMoney?'):
        click.echo("Отменено")
        return
    
    click.echo("Отправляю транзакции в ZenMoney...")
    try:
        result = post_transactions(zenmoney_transactions, token)
        click.echo(f"✓ Успешно отправлено {len(zenmoney_transactions)} транзакций!")
    except Exception as e:
        click.echo(f"✗ Ошибка отправки: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--account', help='Название счета (удалить только транзакции этого счета)')
@click.option('--start-date', help='Начальная дата в формате YYYY-MM-DD')
@click.option('--end-date', help='Конечная дата в формате YYYY-MM-DD')
@click.option('--all', 'delete_all', is_flag=True, help='Удалить ВСЕ транзакции (осторожно!)')
@click.confirmation_option(prompt='Вы уверены, что хотите удалить транзакции?')
@click.pass_context
def delete(ctx, account, start_date, end_date, delete_all):
    """Удалить транзакции из ZenMoney."""
    token = ctx.obj['token']
    
    if delete_all:
        if not click.confirm('⚠️  ВНИМАНИЕ: Вы собираетесь удалить ВСЕ транзакции! Продолжить?'):
            click.echo("Отменено")
            return
        click.echo("Удаляю все транзакции...")
    elif account:
        click.echo(f"Удаляю транзакции на счете '{account}'...")
    elif start_date or end_date:
        click.echo(f"Удаляю транзакции за период {start_date or '...'} - {end_date or '...'}...")
    else:
        click.echo("Укажите --account, --start-date/--end-date или --all", err=True)
        raise click.Abort()
    
    try:
        result = delete_transactions(token, account_title=account, start_date=start_date, end_date=end_date)
        click.echo("✓ Транзакции успешно удалены!")
    except Exception as e:
        click.echo(f"✗ Ошибка удаления: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.pass_context
def list_accounts(ctx):
    """Показать список всех счетов в ZenMoney."""
    token = ctx.obj['token']
    
    click.echo("Получаю список счетов из ZenMoney...")
    try:
        zenmoney_data = get_zenmoney_data(token)
        accounts = zenmoney_data.get('account', [])
        
        if not accounts:
            click.echo("Счета не найдены")
            return
        
        click.echo(f"\nНайдено счетов: {len(accounts)}\n")
        click.echo(f"{'Название':<30} {'ID':<40} {'Валюта':<10} {'Удален'}")
        click.echo("-" * 90)
        
        for acc in accounts:
            if not acc.get('deleted', False):
                instruments = zenmoney_data.get('instrument', [])
                inst_id = acc.get('instrument')
                currency = next((inst.get('shortTitle', '?') for inst in instruments if inst.get('id') == inst_id), '?')
                click.echo(f"{acc.get('title', 'N/A'):<30} {acc.get('id', 'N/A'):<40} {currency:<10} {'Нет'}")
    except Exception as e:
        click.echo(f"✗ Ошибка: {e}", err=True)
        raise click.Abort()


if __name__ == "__main__":
    cli()
