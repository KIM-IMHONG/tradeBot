"""
바이낸스 선물 API 클라이언트
"""
import hashlib
import hmac
import time
from typing import Dict, List, Optional
from urllib.parse import urlencode

import pandas as pd
import requests

from .config import (
    TradingConfig,
    TESTNET_BASE_URL,
    MAINNET_BASE_URL,
)


class BinanceFuturesClient:
    """바이낸스 선물 API 클라이언트"""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.base_url = TESTNET_BASE_URL if config.testnet else MAINNET_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "X-MBX-APIKEY": config.api_key
        })

    def _sign(self, params: Dict) -> Dict:
        """요청 서명"""
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.config.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(self, method: str, endpoint: str, signed: bool = False, **kwargs) -> Dict:
        """API 요청"""
        url = f"{self.base_url}{endpoint}"
        params = kwargs.get("params", {})

        if signed:
            params = self._sign(params)
            kwargs["params"] = params

        response = self.session.request(method, url, **kwargs)

        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code} - {response.text}")

        return response.json()

    # === 계좌 정보 ===
    def get_account_balance(self) -> Dict:
        """계좌 잔고 조회"""
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def get_account_info(self) -> Dict:
        """계좌 정보 조회"""
        return self._request("GET", "/fapi/v2/account", signed=True)

    def get_usdt_balance(self) -> float:
        """USDT 잔고 조회"""
        balances = self.get_account_balance()
        for balance in balances:
            if balance["asset"] == "USDT":
                return float(balance["availableBalance"])
        return 0.0

    # === 포지션 정보 ===
    def get_positions(self) -> List[Dict]:
        """현재 포지션 조회"""
        account = self.get_account_info()
        positions = []
        for pos in account.get("positions", []):
            amt = float(pos["positionAmt"])
            if amt != 0:
                positions.append({
                    "symbol": pos["symbol"],
                    "side": "LONG" if amt > 0 else "SHORT",
                    "size": abs(amt),
                    "entry_price": float(pos["entryPrice"]),
                    "unrealized_pnl": float(pos["unrealizedProfit"]),
                    "leverage": int(pos["leverage"]),
                })
        return positions

    def get_position(self, symbol: str) -> Optional[Dict]:
        """특정 심볼 포지션 조회"""
        positions = self.get_positions()
        for pos in positions:
            if pos["symbol"] == symbol:
                return pos
        return None

    # === 시장 데이터 ===
    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """캔들 데이터 조회"""
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        data = self._request("GET", "/fapi/v1/klines", params=params)

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_volume",
            "taker_buy_quote_volume", "ignore"
        ])

        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        df = df[["open_time", "open", "high", "low", "close", "volume"]]
        df.columns = ["timestamp", "open", "high", "low", "close", "volume"]

        return df

    def get_ticker_price(self, symbol: str) -> float:
        """현재가 조회"""
        params = {"symbol": symbol}
        data = self._request("GET", "/fapi/v1/ticker/price", params=params)
        return float(data["price"])

    def get_exchange_info(self, symbol: str) -> Dict:
        """거래소 정보 조회 (수량/가격 정밀도)"""
        data = self._request("GET", "/fapi/v1/exchangeInfo")
        for s in data["symbols"]:
            if s["symbol"] == symbol:
                return s
        return {}

    # === 레버리지 설정 ===
    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """레버리지 설정"""
        params = {
            "symbol": symbol,
            "leverage": leverage
        }
        return self._request("POST", "/fapi/v1/leverage", signed=True, params=params)

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> Dict:
        """마진 타입 설정 (ISOLATED/CROSSED)"""
        params = {
            "symbol": symbol,
            "marginType": margin_type
        }
        try:
            return self._request("POST", "/fapi/v1/marginType", signed=True, params=params)
        except Exception as e:
            if "No need to change margin type" in str(e):
                return {"msg": "Already set"}
            raise

    # === 주문 ===
    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reduce_only: bool = False
    ) -> Dict:
        """시장가 주문"""
        params = {
            "symbol": symbol,
            "side": side,  # BUY or SELL
            "type": "MARKET",
            "quantity": quantity,
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        return self._request("POST", "/fapi/v1/order", signed=True, params=params)

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC"
    ) -> Dict:
        """지정가 주문"""
        params = {
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "quantity": quantity,
            "price": price,
            "timeInForce": time_in_force,
        }
        return self._request("POST", "/fapi/v1/order", signed=True, params=params)

    def place_stop_loss(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float
    ) -> Dict:
        """스탑로스 주문"""
        params = {
            "symbol": symbol,
            "side": side,  # 롱 청산: SELL, 숏 청산: BUY
            "type": "STOP_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": "true",
        }
        return self._request("POST", "/fapi/v1/order", signed=True, params=params)

    def place_take_profit(
        self,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float
    ) -> Dict:
        """테이크프로핏 주문"""
        params = {
            "symbol": symbol,
            "side": side,  # 롱 청산: SELL, 숏 청산: BUY
            "type": "TAKE_PROFIT_MARKET",
            "quantity": quantity,
            "stopPrice": stop_price,
            "reduceOnly": "true",
        }
        return self._request("POST", "/fapi/v1/order", signed=True, params=params)

    def cancel_all_orders(self, symbol: str) -> Dict:
        """모든 주문 취소"""
        params = {"symbol": symbol}
        return self._request("DELETE", "/fapi/v1/allOpenOrders", signed=True, params=params)

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """미체결 주문 조회"""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/fapi/v1/openOrders", signed=True, params=params)

    # === 유틸리티 ===
    def round_quantity(self, symbol: str, quantity: float) -> float:
        """수량 정밀도 맞춤"""
        info = self.get_exchange_info(symbol)
        for f in info.get("filters", []):
            if f["filterType"] == "LOT_SIZE":
                step_size = float(f["stepSize"])
                precision = len(str(step_size).rstrip("0").split(".")[-1])
                return round(quantity - (quantity % step_size), precision)
        return quantity

    def round_price(self, symbol: str, price: float) -> float:
        """가격 정밀도 맞춤"""
        info = self.get_exchange_info(symbol)
        for f in info.get("filters", []):
            if f["filterType"] == "PRICE_FILTER":
                tick_size = float(f["tickSize"])
                precision = len(str(tick_size).rstrip("0").split(".")[-1])
                return round(price - (price % tick_size), precision)
        return price
