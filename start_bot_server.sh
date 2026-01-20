#!/bin/bash

# 서버에서 24시간 봇 실행 스크립트
# nohup 또는 screen/tmux와 함께 사용

cd "$(dirname "$0")"

# 색상
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BOT_NAME="trading_bot"
LOG_FILE="trading_bot.log"
PID_FILE="trading_bot.pid"

start_bot() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${YELLOW}봇이 이미 실행 중입니다 (PID: $PID)${NC}"
            return 1
        fi
    fi

    echo -e "${GREEN}봇을 시작합니다...${NC}"

    # venv 확인
    if [ ! -d "venv" ]; then
        echo -e "${RED}가상환경이 없습니다. setup.sh를 먼저 실행하세요.${NC}"
        exit 1
    fi

    # .env 확인
    if [ ! -f ".env" ]; then
        echo -e "${RED}.env 파일이 없습니다.${NC}"
        exit 1
    fi

    # nohup으로 백그라운드 실행
    source venv/bin/activate
    nohup python bot/run_bot.py "$@" >> "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"
    echo -e "${GREEN}봇 시작됨 (PID: $!)${NC}"
    echo -e "로그 확인: tail -f $LOG_FILE"
}

stop_bot() {
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}PID 파일이 없습니다.${NC}"
        return 1
    fi

    PID=$(cat "$PID_FILE")
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${YELLOW}봇을 종료합니다 (PID: $PID)...${NC}"
        kill $PID
        rm -f "$PID_FILE"
        echo -e "${GREEN}봇이 종료되었습니다.${NC}"
    else
        echo -e "${YELLOW}봇이 실행 중이 아닙니다.${NC}"
        rm -f "$PID_FILE"
    fi
}

status_bot() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p $PID > /dev/null 2>&1; then
            echo -e "${GREEN}봇 실행 중 (PID: $PID)${NC}"
            echo ""
            echo "최근 로그:"
            tail -20 "$LOG_FILE"
            return 0
        fi
    fi
    echo -e "${YELLOW}봇이 실행 중이 아닙니다.${NC}"
    return 1
}

logs_bot() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo -e "${YELLOW}로그 파일이 없습니다.${NC}"
    fi
}

case "$1" in
    start)
        shift
        start_bot "$@"
        ;;
    stop)
        stop_bot
        ;;
    restart)
        stop_bot
        sleep 2
        shift
        start_bot "$@"
        ;;
    status)
        status_bot
        ;;
    logs)
        logs_bot
        ;;
    *)
        echo "사용법: $0 {start|stop|restart|status|logs} [옵션]"
        echo ""
        echo "명령어:"
        echo "  start   - 봇 시작 (백그라운드)"
        echo "  stop    - 봇 종료"
        echo "  restart - 봇 재시작"
        echo "  status  - 봇 상태 확인"
        echo "  logs    - 실시간 로그 확인"
        echo ""
        echo "예시:"
        echo "  $0 start                    # 테스트넷으로 시작"
        echo "  $0 start --live             # 실거래로 시작"
        echo "  $0 start --symbols BTCUSDT  # 특정 심볼만"
        echo "  $0 logs                     # 로그 모니터링"
        exit 1
        ;;
esac
