#!/bin/bash

# Путь к директории проекта и виртуальному окружению (измените при необходимости)
PROJECT_DIR="$(pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
SCRIPT="$PROJECT_DIR/main.py"

# Команда для crontab: запуск каждый час в HH:55 (без 5 минут каждого часа)
CRON_JOB="55 * * * * cd $PROJECT_DIR && $VENV_PYTHON $SCRIPT >> $PROJECT_DIR/scanner.log 2>&1"

# Проверка и добавление задачи в crontab, если её ещё нет
(crontab -l 2>/dev/null | grep -Fv "$SCRIPT" ; echo "$CRON_JOB") | crontab -

echo "Cron-задача успешно установлена: запуск без 5 минут каждый час (55 * * * *)."
