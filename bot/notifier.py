"""
알림 모듈 - 텔레그램/디스코드 알림
"""
import logging
import requests
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NotifierConfig:
    """알림 설정"""
    # 텔레그램
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # 디스코드
    discord_webhook_url: str = ""

    # 알림 활성화
    enabled: bool = True


class Notifier:
    """알림 전송"""

    def __init__(self, config: NotifierConfig):
        self.config = config

    def send(self, message: str, level: str = "INFO") -> bool:
        """알림 전송"""
        if not self.config.enabled:
            return False

        success = False

        # 텔레그램
        if self.config.telegram_token and self.config.telegram_chat_id:
            success = self._send_telegram(message) or success

        # 디스코드
        if self.config.discord_webhook_url:
            success = self._send_discord(message, level) or success

        return success

    def _send_telegram(self, message: str) -> bool:
        """텔레그램 전송"""
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_token}/sendMessage"
            data = {
                "chat_id": self.config.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"텔레그램 전송 실패: {e}")
            return False

    def _send_discord(self, message: str, level: str) -> bool:
        """디스코드 전송"""
        try:
            # 레벨별 색상
            colors = {
                "INFO": 3447003,    # 파랑
                "SUCCESS": 3066993, # 초록
                "WARNING": 15105570, # 주황
                "ERROR": 15158332,  # 빨강
            }

            data = {
                "embeds": [{
                    "description": message,
                    "color": colors.get(level, 3447003)
                }]
            }
            response = requests.post(
                self.config.discord_webhook_url,
                json=data,
                timeout=10
            )
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"디스코드 전송 실패: {e}")
            return False

    # === 편의 메서드 ===
    def notify_trade_open(self, symbol: str, side: str, entry: float, tp: float, sl: float, reasons: list):
        """거래 진입 알림"""
        msg = f"""🚀 <b>포지션 오픈</b>

심볼: {symbol}
방향: {side}
진입가: ${entry:,.2f}
익절(TP): ${tp:,.2f}
손절(SL): ${sl:,.2f}

사유: {', '.join(reasons)}"""
        self.send(msg, "SUCCESS")

    def notify_trade_close(self, symbol: str, side: str, entry: float, exit_price: float, pnl: float, reason: str):
        """거래 청산 알림"""
        emoji = "✅" if pnl > 0 else "❌"
        level = "SUCCESS" if pnl > 0 else "WARNING"

        msg = f"""{emoji} <b>포지션 청산</b>

심볼: {symbol}
방향: {side}
진입가: ${entry:,.2f}
청산가: ${exit_price:,.2f}
손익: ${pnl:,.2f} ({pnl/entry*100:.2f}%)

사유: {reason}"""
        self.send(msg, level)

    def notify_error(self, error: str):
        """에러 알림"""
        msg = f"""⚠️ <b>오류 발생</b>

{error}"""
        self.send(msg, "ERROR")

    def notify_status(self, balance: float, positions: dict):
        """상태 알림"""
        pos_text = ""
        for symbol, pos in positions.items():
            pos_text += f"\n  • {symbol}: {pos['side']} @ ${pos['entry_price']:,.2f}"

        if not pos_text:
            pos_text = "\n  없음"

        msg = f"""📊 <b>봇 상태</b>

잔고: ${balance:,.2f}
포지션:{pos_text}"""
        self.send(msg, "INFO")
