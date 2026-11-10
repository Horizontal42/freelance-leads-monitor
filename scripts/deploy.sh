#!/usr/bin/env bash
# ==============================================================================
# Automated Production Deployment Script for Freelance Leads Monitor
# Target: server-old-vm (100.73.44.69)
# ==============================================================================
set -euo pipefail

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Resolve symlink to find real repo directory
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_SOURCE" ]; do
    SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
    [[ $SCRIPT_SOURCE != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
REPO_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"
cd "$REPO_DIR"

PROD_HOST="server-old-vm"
PROD_DIR="/home/horizontal42/jobs"
PROD_SERVICE="freelance-monitor.service"
HEALTH_URL="https://jobs.3dvex.ru/health"
FORCE=false

for arg in "$@"; do
    case "$arg" in
        --force|-f)
            FORCE=true
            ;;
        --help|-h)
            echo "Usage: $0 [--force]"
            echo "Options:"
            echo "  --force, -f    Force deployment even if prod is already on latest commit"
            exit 0
            ;;
    esac
done

echo -e "${BLUE}==>${NC} Запуск раскатки Freelance Leads Monitor..."

# 1. Проверка SSH соединения с продакшн-сервером
echo -e "${BLUE}==>${NC} Проверка связи с ${PROD_HOST}..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "${PROD_HOST}" "echo OK" >/dev/null 2>&1; then
    echo -e "${RED}[ERROR]${NC} Не удалось подключиться по SSH к ${PROD_HOST}!"
    exit 1
fi

# 2. Получение свежих коммитов из origin/master
echo -e "${BLUE}==>${NC} Проверка обновлений в GitHub (origin/master)..."
git fetch origin master --quiet

LOCAL_COMMIT="$(git rev-parse HEAD)"
REMOTE_COMMIT="$(git rev-parse origin/master)"
PROD_COMMIT="$(ssh "${PROD_HOST}" "cd ${PROD_DIR} && git rev-parse HEAD" 2>/dev/null || echo "UNKNOWN")"

if [ "$LOCAL_COMMIT" != "$REMOTE_COMMIT" ]; then
    echo -e "${YELLOW}==>${NC} Обновление локальной ветки master до origin/master..."
    git merge --ff-only origin/master
    LOCAL_COMMIT="$(git rev-parse HEAD)"
fi

COMMIT_MSG="$(git log -1 --pretty=format:'%s (%h by %an)')"
echo -e "   Целевой коммит: ${GREEN}${COMMIT_MSG}${NC}"
echo -e "   Текущий коммит на проде: ${YELLOW}${PROD_COMMIT:0:7}${NC}"

if [ "${LOCAL_COMMIT:0:7}" == "${PROD_COMMIT:0:7}" ] && [ "$FORCE" != true ]; then
    echo -e "${GREEN}[OK]${NC} Прод (${PROD_HOST}) уже обновлен до последней версии (${LOCAL_COMMIT:0:7})!"
    echo "Используйте --force, если требуется принудительно пересинхронизировать и перезапустить."
    exit 0
fi

# 3. Запуск тестов на локальной машине
echo -e "${BLUE}==>${NC} Запуск тестов pytest на машине сборки..."
if [ -f ".venv/bin/pytest" ]; then
    if ! .venv/bin/pytest -q; then
        echo -e "${RED}[ERROR]${NC} Локальные тесты провалены! Отмена деплоя."
        exit 1
    fi
else
    echo -e "${YELLOW}[WARN]${NC} Локальный .venv/bin/pytest не найден, пропуск локальных тестов."
fi

# 4. Синхронизация файлов с прод-сервером
echo -e "${BLUE}==>${NC} Синхронизация файлов на ${PROD_HOST}:${PROD_DIR}..."
rsync -avz \
    --exclude='data/' \
    --exclude='.venv/' \
    --exclude='.env' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pytest_cache/' \
    --exclude='.git/index.lock' \
    "${REPO_DIR}/" "${PROD_HOST}:${PROD_DIR}/"

# 5. Обновление зависимостей и прогон тестов на прод-сервере
echo -e "${BLUE}==>${NC} Проверка и установка зависимостей на ${PROD_HOST}..."
ssh "${PROD_HOST}" "cd ${PROD_DIR} && .venv/bin/pip install -q -e ."

echo -e "${BLUE}==>${NC} Запуск тестов pytest на ${PROD_HOST}..."
if ! ssh "${PROD_HOST}" "cd ${PROD_DIR} && .venv/bin/pytest -q"; then
    echo -e "${RED}[ERROR]${NC} Тесты на прод-сервере провалены! Сервис не перезапущен."
    exit 1
fi

# 6. Перезапуск systemd службы
echo -e "${BLUE}==>${NC} Перезапуск службы ${PROD_SERVICE} на ${PROD_HOST}..."
ssh "${PROD_HOST}" "sudo systemctl stop --no-block ${PROD_SERVICE} 2>/dev/null || true"

# Ждем до 5 секунд штатного завершения, при необходимости форсированно завершаем старый PID
STOP_WAIT=0
while [ $STOP_WAIT -lt 5 ]; do
    OLD_PID="$(ssh "${PROD_HOST}" "pgrep -f 'src.main' || true")"
    if [ -z "$OLD_PID" ]; then
        break
    fi
    sleep 1
    STOP_WAIT=$((STOP_WAIT + 1))
done

OLD_PID="$(ssh "${PROD_HOST}" "pgrep -f 'src.main' || true")"
if [ -n "$OLD_PID" ]; then
    echo -e "${YELLOW}[WARN]${NC} Процесс не завершился за 5 секунд, завершаю принудительно PID ${OLD_PID}..."
    ssh "${PROD_HOST}" "sudo kill -9 ${OLD_PID} 2>/dev/null || true"
    sleep 1
fi

ssh "${PROD_HOST}" "sudo systemctl restart ${PROD_SERVICE}"

# 7. Проверка активности службы
echo -e "${BLUE}==>${NC} Ожидание запуска службы..."
ATTEMPTS=0
ACTIVE=false
while [ $ATTEMPTS -lt 10 ]; do
    STATUS="$(ssh "${PROD_HOST}" "systemctl is-active ${PROD_SERVICE}" 2>/dev/null || true)"
    if [ "$STATUS" == "active" ]; then
        ACTIVE=true
        break
    fi
    sleep 1
    ATTEMPTS=$((ATTEMPTS + 1))
done

if [ "$ACTIVE" != true ]; then
    echo -e "${RED}[ERROR]${NC} Служба ${PROD_SERVICE} не перешла в статус active!"
    ssh "${PROD_HOST}" "systemctl status ${PROD_SERVICE} --no-pager"
    exit 1
fi

# 8. Проверка health check
echo -e "${BLUE}==>${NC} Проверка работоспособности Health Check..."
sleep 2

HEALTH_CHECK_PASSED=false
for i in {1..15}; do
    HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" -u Horizontal42:qaz403111 "${HEALTH_URL}" 2>/dev/null || true)"
    if [ "$HTTP_CODE" == "200" ]; then
        HEALTH_CHECK_PASSED=true
        break
    fi
    sleep 1
done

if [ "$HEALTH_CHECK_PASSED" == true ]; then
    echo -e "${GREEN}[SUCCESS]${NC} Обновление успешно раскатано на прод!"
    echo -e "   Коммит: ${GREEN}${COMMIT_MSG}${NC}"
    echo -e "   Health Check: ${GREEN}200 OK${NC} (${HEALTH_URL})"
    echo -e "   Статус: ${GREEN}active (running)${NC}"
else
    echo -e "${RED}[ERROR]${NC} Health Check вернул код: ${HTTP_CODE}!"
    exit 1
fi
