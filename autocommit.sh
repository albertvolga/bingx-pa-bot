#!/bin/bash
PROJECT_DIR="/root/bingx-pa-bot"

cd "$PROJECT_DIR" || exit

# Проверяем, есть ли незакоммиченные изменения
if [ -n "$(git status --porcelain)" ]; then
    git add .
    git commit -m "Auto-backup: $(date '+%Y-%m-%d %H:%M:%S')"
    git push origin main
fi
