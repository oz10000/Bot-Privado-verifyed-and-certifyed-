
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Signal:
    symbol: str
    direction: str
    timestamp: datetime
    entry: float
    tp: float
    sl: float
    raw_score: float
    roc_5m: float
    speed_score: float
    atr: float

@dataclass
class Position:
    symbol: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    pnl: float
    pnl_pct: float

@dataclass
class OrderResult:
    ord_id: str
    algo_id: Optional[str] = None
    avg_px: Optional[float] = None
    state: Optional[str] = None

@dataclass
class Balance:
    total: float
    free: float
    frozen: float

@dataclass
class ProtectionStatus:
    tp_exists: bool
    sl_exists: bool
    trail_exists: bool

@dataclass
class MarketData:
    symbol: str
    price: float
    atr: float
    ker: float
    zscore: float
    roc: float
    volume_ratio: float

# ============================================================
# VERIFICACIÓN AUTÓNOMA
# ============================================================
if __name__ == "__main__":
    print("="*70)
    print("🧪 VERIFICACIÓN DE models.py")
    print("="*70)
    now = datetime.now()
    s = Signal("BTC","Long",now,60000,61000,59000,0.5,0.3,0.45,500)
    p = Position("BTC","long",0.1,60000,60500,50,0.83)
    o = OrderResult("123","456",60000,"filled")
    b = Balance(10000,9500,500)
    ps = ProtectionStatus(True,True,False)
    md = MarketData("BTC",60000,500,0.65,1.2,0.3,1.8)
    print("  ✅ Todos los modelos instanciados correctamente")
    print("✅ models.py OK")
