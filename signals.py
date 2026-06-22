import sys
import numpy as np
import pandas as pd
import requests
from datetime import datetime
from typing import Optional, Dict, List, Any

import config
from models import Signal
from telemetry import log_info, log_warning, log_error, log_debug

# Parámetros
KER_PERIOD = 10
VWAP_PERIOD = 20
ATR_PERIOD = 14
EMA_PERIOD = 20
SLOPE_PERIOD = 5
MACRO_LOOKBACK = 20
ANTI_CHASE_THRESHOLD = 0.75
LOOKBACK_WINDOW = 5
PESOS = {'micro': 0.50, 'regime': 0.30, 'macro': 0.20}

# Indicadores
def calculate_ker(close: pd.Series, period: int = KER_PERIOD) -> pd.Series:
    abs_diff = abs(close.diff(period))
    sum_abs = close.diff().abs().rolling(period).sum()
    return (abs_diff / (sum_abs + 1e-9)).clip(0, 1)

def calculate_vwap_zscore(df: pd.DataFrame, period: int = VWAP_PERIOD) -> pd.Series:
    vwap = (df['c'] * df['vol']).rolling(period).sum() / (df['vol'].rolling(period).sum() + 1e-9)
    std = df['c'].rolling(period).std()
    return (df['c'] - vwap) / (std + 1e-9)

def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    tr = pd.concat([
        df['h'] - df['l'],
        abs(df['h'] - df['c'].shift()),
        abs(df['l'] - df['c'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calculate_roc(close: pd.Series, period: int = 1) -> pd.Series:
    return close.pct_change(period) * 100

def calculate_macro(df: pd.DataFrame, period: int = MACRO_LOOKBACK) -> pd.Series:
    atr = calculate_atr(df, period=ATR_PERIOD)
    macro = atr.rolling(period).apply(
        lambda x: (x.iloc[-1] - x.min()) / (x.max() - x.min() + 1e-9)
    )
    return macro.clip(0, 1)

def fetch_okx_candles(symbol: str, bar: str = '5m', limit: int = 150) -> pd.DataFrame:
    inst_id = f"{symbol}-USDT-SWAP"
    url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get('code') != '0':
            return pd.DataFrame()
        raw = data['data']
        ts_list = [int(x[0]) for x in raw]
        df = pd.DataFrame({
            'ts': pd.to_datetime(ts_list, unit='ms'),
            'o': [float(x[1]) for x in raw],
            'h': [float(x[2]) for x in raw],
            'l': [float(x[3]) for x in raw],
            'c': [float(x[4]) for x in raw],
            'vol': [float(x[5]) for x in raw],
        })
        return df.sort_values('ts').reset_index(drop=True)
    except Exception as e:
        log_error("Signals", f"Error descargando {symbol}", {"error": str(e)})
        return pd.DataFrame()

def compute_pidelta_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df['ker'] = calculate_ker(df['c'])
    df['vwap_z'] = calculate_vwap_zscore(df)
    df['atr'] = calculate_atr(df)
    df['roc_5m'] = calculate_roc(df['c'])
    df['ema20'] = df['c'].ewm(span=EMA_PERIOD, adjust=False).mean()
    df['slope'] = (df['ema20'].diff(SLOPE_PERIOD)) / (df['atr'] + 1e-9)
    df['micro'] = df['slope']
    df['regime'] = df['ker']
    df['macro'] = calculate_macro(df)
    raw = (PESOS['micro'] * df['micro'] +
           PESOS['regime'] * df['regime'] +
           PESOS['macro'] * df['macro'])
    df['raw_score'] = np.tanh(raw)
    df['direction'] = 0
    df.loc[df['raw_score'] > 0.20, 'direction'] = 1
    df.loc[df['raw_score'] < -0.20, 'direction'] = -1
    return df

def apply_filters(df: pd.DataFrame, symbol: str, direction: str) -> pd.Series:
    cfg = config.FILTERS.get(symbol, {}).get(direction, {})
    if not cfg:
        return pd.Series(True, index=df.index)
    mask = pd.Series(True, index=df.index)
    mask &= (df['c'] > 0) & (df['vol'] > 0)
    if direction == 'Long':
        if 'ker_min' in cfg:
            mask &= (df['ker'] > cfg['ker_min']) & df['ker'].notna()
        if 'zscore_min' in cfg:
            mask &= (df['vwap_z'] > cfg['zscore_min']) & df['vwap_z'].notna()
        if 'atr_percent_min' in cfg:
            atr_pct = (df['atr'] / df['c']) * 100
            mask &= (atr_pct > cfg['atr_percent_min']) & atr_pct.notna()
        if 'vol_rel_min' in cfg:
            vol_rel = df['vol'] / df['vol'].rolling(20).mean()
            mask &= (vol_rel > cfg['vol_rel_min']) & vol_rel.notna()
        if 'ema_pend_min' in cfg:
            pend = df['c'] / df['ema20'] - 1
            mask &= (pend > cfg['ema_pend_min']) & pend.notna()
    else:
        if 'zscore_max' in cfg:
            mask &= (df['vwap_z'] < cfg['zscore_max']) & df['vwap_z'].notna()
        if 'vol_rel_min' in cfg:
            vol_rel = df['vol'] / df['vol'].rolling(20).mean()
            mask &= (vol_rel > cfg['vol_rel_min']) & vol_rel.notna()
        if 'ker_min' in cfg:
            mask &= (df['ker'] > cfg['ker_min']) & df['ker'].notna()
    return mask

def generate_signal(symbol: str, direction: str, speed_level: Dict) -> Optional[Signal]:
    df = fetch_okx_candles(symbol, bar='5m', limit=150)
    if df.empty:
        return None
    # Validar integridad
    if len(df) < 30:
        log_warning("Signals", f"Velas insuficientes para {symbol}")
        return None
    if df['ts'].isnull().any() or df['c'].isnull().any():
        log_warning("Signals", f"Datos corruptos para {symbol}")
        return None
    df = compute_pidelta_columns(df)
    mask = apply_filters(df, symbol, direction)
    df_filtered = df[mask].copy()
    if df_filtered.empty:
        return None
    last_n = df_filtered.tail(LOOKBACK_WINDOW)
    if last_n.empty:
        return None
    raw_th = speed_level['raw_min']
    roc_th = speed_level['roc_min']
    speed_mask = (
        (last_n['raw_score'].abs() > raw_th) &
        (last_n['roc_5m'].abs() > roc_th) &
        (last_n['direction'] == (1 if direction == 'Long' else -1))
    )
    candidates = last_n[speed_mask]
    if candidates.empty:
        return None
    # Anti-chase
    candidates['pos'] = (candidates['c'] - candidates['l']) / (candidates['h'] - candidates['l'] + 1e-9)
    if direction == 'Long':
        candidates = candidates[candidates['pos'] <= ANTI_CHASE_THRESHOLD]
    else:
        candidates = candidates[(1 - candidates['pos']) <= ANTI_CHASE_THRESHOLD]
    if candidates.empty:
        return None
    candidates['speed_score'] = candidates['raw_score'].abs() * (1 + np.tanh(candidates['roc_5m'].abs() / 5))
    best = candidates.loc[candidates['speed_score'].idxmax()]
    atr = best['atr']
    entry = best['c']
    if direction == 'Long':
        tp = entry + atr * config.TP_MULT
        sl = entry - atr * config.SL_MULT
    else:
        tp = entry - atr * config.TP_MULT
        sl = entry + atr * config.SL_MULT
    signal = Signal(
        symbol=symbol, direction=direction,
        timestamp=best['ts'], entry=entry, tp=tp, sl=sl,
        raw_score=best['raw_score'], roc_5m=best['roc_5m'],
        speed_score=best['speed_score'], atr=atr
    )
    log_info("Signals", f"Señal generada {symbol} {direction}", {"entry": entry})
    return signal

# ============================================================
# VERIFICACIÓN AUTÓNOMA
# ============================================================
if __name__ == "__main__":
    print("="*70)
    print("🧪 VERIFICACIÓN DE signals.py")
    print("="*70)
    # Datos sintéticos
    np.random.seed(42)
    n = 200
    price = 60000 + np.cumsum(np.random.randn(n) * 100)
    df = pd.DataFrame({
        'ts': pd.date_range('2026-01-01', periods=n, freq='5min'),
        'o': price + np.random.randn(n)*10,
        'h': price + np.abs(np.random.randn(n)*20),
        'l': price - np.abs(np.random.randn(n)*20),
        'c': price,
        'vol': np.random.randint(100,1000,n)
    })
    ker = calculate_ker(df['c'])
    assert 0 <= ker.iloc[-1] <= 1
    print("  ✅ KER")
    z = calculate_vwap_zscore(df)
    assert np.isfinite(z.iloc[-1])
    print("  ✅ VWAP Z")
    atr = calculate_atr(df)
    assert atr.iloc[-1] > 0
    print("  ✅ ATR")
    df_calc = compute_pidelta_columns(df.copy())
    assert 'raw_score' in df_calc.columns
    print("  ✅ PiDelta")
    print("✅ signals.py OK")
