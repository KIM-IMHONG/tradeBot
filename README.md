# 바이낸스 선물 백테스트 - 옵션 A vs B 비교

## 개요

이 프로젝트는 바이낸스 선물 트레이딩 전략의 백테스트를 수행합니다.

### 전략 비교

| 전략 | 설명 | 예상 특성 |
|------|------|----------|
| **Option A (보수적)** | 모든 조건 AND | 높은 승률, 낮은 거래 빈도 |
| **Option B (균형)** | 필수 + 확인조건 | 적절한 승률, 적절한 거래 빈도 |

#### Option A 조건 (모두 충족)
- RSI < 35 + 상승 전환
- 스토캐스틱 골든크로스 (K > D)
- 볼린저밴드 하단 터치 + 반등
- 거래량 1.3배 이상 증가

#### Option B 조건
**필수 (모두 충족):**
- RSI < 40
- 가격 < BB 중간선

**확인 (2개 이상 충족):**
- RSI 상승 전환
- 스토캐스틱 골든크로스
- 스토캐스틱 < 35
- BB 하단 근접 (2% 이내)
- 거래량 1.2배 이상 증가

## 설치

```bash
# 1. 프로젝트 폴더로 이동
cd /Users/kim-imhong/Documents/daniel/tradeBot

# 2. 가상환경 설정 및 패키지 설치
chmod +x setup.sh
./setup.sh

# 3. 가상환경 활성화
source venv/bin/activate
```

## 사용법

### 기본 실행 (BTC, ETH, SOL / 180일)
```bash
python run_backtest.py
```

### 옵션 설정
```bash
# 특정 심볼만
python run_backtest.py --symbols BTCUSDT

# 기간 변경 (1년)
python run_backtest.py --days 365

# 레버리지 변경
python run_backtest.py --leverage 10

# 거래 내역 CSV 저장
python run_backtest.py --save-trades

# 차트 생성 안함
python run_backtest.py --no-chart

# 전체 옵션
python run_backtest.py \
    --symbols BTCUSDT,ETHUSDT \
    --days 90 \
    --balance 10000 \
    --leverage 5 \
    --risk 0.02 \
    --save-trades
```

### 빠른 실행
```bash
chmod +x run.sh
./run.sh
./run.sh --symbols BTCUSDT --days 90
```

## 출력 결과

### 콘솔 출력
- 전략별 비교 테이블
- 상세 거래 통계
- 최근 거래 내역

### 파일 출력
- `results/backtest_{심볼}_{날짜}.png` - 비교 차트
- `results/trades_{전략}_{심볼}.csv` - 거래 내역 (--save-trades 옵션)

## 프로젝트 구조

```
tradeBot/
├── backtest/
│   ├── __init__.py
│   ├── strategies.py    # 전략 클래스 (Option A, B)
│   └── engine.py        # 백테스트 엔진
├── data/                # 다운로드된 데이터 (미사용)
├── results/             # 결과 파일
├── venv/                # 가상환경
├── requirements.txt     # 패키지 목록
├── setup.sh            # 설치 스크립트
├── run.sh              # 실행 스크립트
├── run_backtest.py     # 메인 실행 파일
└── README.md
```

## 성과 지표 설명

| 지표 | 설명 |
|------|------|
| 승률 | 수익 거래 / 전체 거래 |
| Profit Factor | 총 이익 / 총 손실 (1 이상이면 수익) |
| Sharpe Ratio | 위험 대비 수익률 (1 이상 권장) |
| 최대 낙폭 | 최고점 대비 최대 하락폭 |

## 주의사항

⚠️ **면책조항**: 이 백테스트 결과는 과거 데이터 기반이며, 미래 수익을 보장하지 않습니다.

- 슬리피지, 유동성 등 실제 거래 환경 요소 미반영
- 수수료는 0.04% (바이낸스 선물 기본) 적용
- 실제 거래 전 충분한 테스트 필요
