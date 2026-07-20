#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Формирует ЧИСТЫЙ снимок кода для передачи разработчикам:
#   • без git-истории (только текущее состояние, один initial-коммит);
#   • без служебных артефактов (node_modules, dist, .env, ключи, __pycache__);
#   • с вендор-нейтральными именами (AI_API_KEY вместо провайдер-специфичных).
#
# Живой репозиторий и деплой НЕ затрагиваются — работаем в отдельной папке.
#
# Использование:
#   bash scripts/make-clean-snapshot.sh [DEST_DIR]
# DEST_DIR по умолчанию: ../uzassets-platform-snapshot
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$REPO_ROOT/../uzassets-platform-snapshot}"

echo ">> Источник: $REPO_ROOT"
echo ">> Назначение: $DEST"

rm -rf "$DEST"
mkdir -p "$DEST"

# 1) Экспортируем ТОЛЬКО отслеживаемые файлы текущего HEAD — без .git и без
#    неотслеживаемых артефактов (node_modules/dist/.env туда не попадут, если
#    они в .gitignore).
git -C "$REPO_ROOT" archive --format=tar HEAD | tar -x -C "$DEST"

# 2) Подчистка на всякий случай (если что-то отслеживалось зря).
find "$DEST" -type d -name node_modules -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -type d -name dist -prune -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -type f \( -name '*.pem' -o -name '*.key' -o -name '.env' -o -name '.env.*' ! -name '.env*.example' \) -delete 2>/dev/null || true

# 3) Вендор-нейтральные имена. Переименовываем провайдер-специфичную переменную
#    окружения в общий AI_API_KEY во всех текстовых файлах.
grep -rIl 'ANTHROPIC_API_KEY' "$DEST" 2>/dev/null | while read -r f; do
  sed -i 's/ANTHROPIC_API_KEY/AI_API_KEY/g' "$f"
done
# Убираем возникшую избыточную подстановку ${AI_API_KEY:-${AI_API_KEY:-}} → ${AI_API_KEY:-}
grep -rIl '${AI_API_KEY:-${AI_API_KEY:-}}' "$DEST" 2>/dev/null | while read -r f; do
  sed -i 's/${AI_API_KEY:-${AI_API_KEY:-}}/${AI_API_KEY:-}/g' "$f"
done
# Нейтрализуем вендор-упоминание в комментарии.
grep -rIl 'Anthropic' "$DEST" 2>/dev/null | while read -r f; do
  sed -i 's/Anthropic/провайдер/g' "$f"
done

# 4) Контроль остаточных вендор-упоминаний.
echo ">> Проверка остаточных упоминаний:"
RESID=$(grep -rIin -e 'anthropic' -e 'claude' -e 'firebase' -e 'монолит' -e 'monolith' \
          "$DEST" 2>/dev/null | grep -viE 'model|fable|opus|sonnet|haiku' || true)
if [ -n "$RESID" ]; then
  echo "!! Найдены упоминания — проверьте вручную:"
  echo "$RESID"
else
  echo "   чисто."
fi

# 5) Свежая история — один initial-коммит.
cd "$DEST"
git init -q
git add -A
git -c user.name='UzAssets' -c user.email='dev@uz-assets.uz' \
    commit -q -m "Initial commit: Единая платформа трансформации"

echo ">> Готово. Чистый снимок: $DEST (git-история = 1 коммит)."
echo ">> Архив: (cd \"$DEST/..\" && tar -czf uzassets-platform-snapshot.tar.gz \"$(basename "$DEST")\")"
