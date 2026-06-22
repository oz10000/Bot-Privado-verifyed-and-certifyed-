# ============================================================
# SÍMBOLOS Y OPERATIVA
# ============================================================
SYMBOLS = ['BTC', 'ETH', 'SOL', 'ADA', 'XRP']
TRADE_NOTIONAL = 1000.0      # USDT por operación
LEVERAGE = 10                # Apalancamiento fijo

# ============================================================
# TP, SL Y TRAILING STOP (optimizados)
# ============================================================
TP_MULT = 1.2
SL_MULT = 1.5
TRAILING_ENABLED = True
TRAILING_MODE = 'native'              # 'native' (OKX) o 'virtual'
TRAILING_DISTANCE_ATR = 0.8           # Múltiplos de ATR
TRAILING_ACTIVATION_PROFIT = 0.8      # % beneficio para activar

# ============================================================
# AUTOSPEED (niveles de velocidad)
# ============================================================
SPEED_LEVELS = [
    {"nivel": 1, "raw_min": 0.45, "roc_min": 0.30},
    {"nivel": 2, "raw_min": 0.40, "roc_min": 0.25},
    {"nivel": 3, "raw_min": 0.35, "roc_min": 0.20},
    {"nivel": 4, "raw_min": 0.30, "roc_min": 0.15},
    {"nivel": 5, "raw_min": 0.25, "roc_min": 0.10},
    {"nivel": 6, "raw_min": 0.20, "roc_min": 0.05},
]
DEFAULT_SPEED_LEVEL = SPEED_LEVELS[2]  # Nivel 3 (optimizado)

# ============================================================
# FILTRO HORARIO Y DIAS
# ============================================================
TIME_FILTER_ENABLED = True
TIME_FILTER_START = 12      # UTC
TIME_FILTER_END = 18
TIME_FILTER_WEEKDAYS = [0, 1, 2, 3, 4]  # Lunes a Viernes

# ============================================================
# FILTROS POR ACTIVO (optimizados)
# ============================================================
FILTERS = {
    'BTC': {'Long': {'ker_min': 0.55, 'zscore_min': 1.2},
            'Short': {'zscore_max': -1.8, 'vol_rel_min': 1.8}},
    'ETH': {'Long': {'ker_min': 0.50, 'atr_percent_min': 0.75},
            'Short': {'zscore_max': -1.5, 'ker_min': 0.50}},
    'SOL': {'Long': {'vol_rel_min': 1.8, 'ema_pend_min': 0.0015},
            'Short': {'ker_min': 0.60, 'zscore_max': -1.2}},
    'ADA': {'Long': {'ker_min': 0.45, 'vol_rel_min': 1.5, 'atr_percent_min': 0.80},
            'Short': {'ker_min': 0.45, 'zscore_max': -1.0, 'vol_rel_min': 1.5}},
    'XRP': {'Long': {'ker_min': 0.40, 'vol_rel_min': 1.5, 'zscore_min': 0.8},
            'Short': {'ker_min': 0.40, 'zscore_max': -0.8, 'vol_rel_min': 1.5}}
}

# ============================================================
# RECUPERACIÓN, REINTENTOS Y TIMEOUTS
# ============================================================
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_BACKOFF = 5
MAX_RETRIES_PER_ORDER = 3
ORDER_TIMEOUT = 15
LOCK_FILE = '.lock'
LOCK_TIMEOUT = 10

# ============================================================
# LOGGING Y AUDITORÍA
# ============================================================
LOG_DIR = 'logs'
LOG_LEVEL = 'INFO'
LOG_CONSOLE = True
LOG_FILE = True
LOG_JSON = True
MAX_LOG_SIZE_MB = 10
MAX_LOG_FILES = 5

# ============================================================
# MODO DEMO / LIVE (se lee de variable de entorno)
# ============================================================
OKX_DEMO = True   # por defecto, se sobrescribe con os.environ

# ============================================================
# UMBRALES DE SALUD (Health Check)
# ============================================================
MAX_MEMORY_MB = 256
MAX_DISK_USAGE_MB = 100
MAX_LATENCY_MS = 2000
MAX_CYCLE_DURATION_SEC = 60
MAX_CONSECUTIVE_ERRORS = 5
MAX_DAILY_LOSS_PERCENT = 5.0
MAX_DRAWDOWN_PERCENT = 10.0

# ============================================================
# VERIFICACIÓN AUTÓNOMA
# ============================================================
if __name__ == "__main__":
    print("="*70)
    print("🧪 VERIFICACIÓN DE CONFIGURACIÓN")
    print("="*70)
    required = ['SYMBOLS', 'TRADE_NOTIONAL', 'LEVERAGE', 'TP_MULT', 'SL_MULT',
                'TRAILING_ENABLED', 'TRAILING_DISTANCE_ATR', 'DEFAULT_SPEED_LEVEL',
                'TIME_FILTER_ENABLED', 'FILTERS', 'LOG_DIR']
    for v in required:
        assert v in globals(), f"Falta {v}"
        print(f"  ✅ {v}")
    print("\n✅ CONFIGURACIÓN OK")
