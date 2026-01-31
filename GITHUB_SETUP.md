# Инструкция по публикации на GitHub

## Шаг 1: Подготовка файлов

Убедитесь, что все файлы готовы:
- ✅ `main.py` - основной код
- ✅ `requirements.txt` - зависимости
- ✅ `README.md` - документация
- ✅ `.gitignore` - игнорируемые файлы

## Шаг 2: Добавление файлов в git

```bash
# Добавить все файлы
git add main.py requirements.txt README.md .gitignore

# Или добавить все файлы сразу
git add .
```

## Шаг 3: Создание первого коммита

```bash
git commit -m "Initial commit: PDF to ZenMoney import utility"
```

## Шаг 4: Создание репозитория на GitHub

1. Откройте https://github.com/new
2. Заполните:
   - **Repository name**: `pdf-to-zenmoney` (или другое название)
   - **Description**: "Утилита для импорта банковских выписок из PDF в ZenMoney"
   - **Visibility**: Public или Private (на ваш выбор)
   - **НЕ** создавайте README, .gitignore или license (они уже есть)
3. Нажмите "Create repository"

## Шаг 5: Подключение к GitHub и отправка кода

После создания репозитория GitHub покажет инструкции. Выполните:

```bash
# Добавить remote (замените YOUR_USERNAME на ваш GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/pdf-to-zenmoney.git

# Или через SSH (если настроен):
# git remote add origin git@github.com:YOUR_USERNAME/pdf-to-zenmoney.git

# Переименовать ветку в main (если нужно)
git branch -M main

# Отправить код на GitHub
git push -u origin main
```

## Шаг 6: Проверка

Откройте ваш репозиторий на GitHub и убедитесь, что все файлы загружены.

## Дополнительно: Настройка GitHub Actions (опционально)

Если хотите добавить автоматические проверки, создайте файл `.github/workflows/ci.yml`:

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Check syntax
        run: |
          python -m py_compile main.py
```

## Полезные команды для будущих обновлений

```bash
# Посмотреть статус изменений
git status

# Добавить изменения
git add .

# Создать коммит
git commit -m "Описание изменений"

# Отправить на GitHub
git push
```
