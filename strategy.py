
from typing import List, Dict, Optional
import config
from signals import generate_signal
from models import Signal
from telemetry import log_info, log_error, log_debug


def get_best_signal(
    symbols: Optional[List[str]] = None,
    speed_levels: Optional[Dict[str, Dict[str, Dict]]] = None
) -> Optional[Signal]:
    """
    Evalúa todos los símbolos y direcciones, retorna la mejor señal o None.

    Argumentos:
        symbols: Lista de símbolos a evaluar. Si es None, usa config.SYMBOLS.
        speed_levels: Diccionario con niveles de velocidad por símbolo y dirección.
                      Si es None, usa el nivel por defecto (DEFAULT_SPEED_LEVEL).

    Retorna:
        La señal con mayor `speed_score` (objeto Signal) o None si no hay señales.
    """
    # Validación de símbolos
    if symbols is None:
        symbols = config.SYMBOLS
    if not isinstance(symbols, list):
        log_error("Strategy", "symbols debe ser lista o None", {"type": type(symbols).__name__})
        return None

    if not symbols:
        log_info("Strategy", "Lista de símbolos vacía, no se evalúa ninguna señal")
        return None

    # Preparar speed_levels
    if speed_levels is None:
        speed_levels = {}
        default_level = config.DEFAULT_SPEED_LEVEL
        for sym in symbols:
            speed_levels[sym] = {'Long': default_level, 'Short': default_level}
    else:
        default_level = config.DEFAULT_SPEED_LEVEL
        for sym in symbols:
            if sym not in speed_levels:
                speed_levels[sym] = {'Long': default_level, 'Short': default_level}
            else:
                for direction in ['Long', 'Short']:
                    if direction not in speed_levels[sym]:
                        speed_levels[sym][direction] = default_level

    # Recopilar todas las señales
    all_signals = []
    for symbol in symbols:
        for direction in ['Long', 'Short']:
            level = speed_levels.get(symbol, {}).get(direction, config.DEFAULT_SPEED_LEVEL)
            log_debug("Strategy", f"Generando señal para {symbol} {direction}", {"level": level})
            try:
                signal = generate_signal(symbol, direction, level)
                if signal:
                    all_signals.append(signal)
            except Exception as e:
                log_error("Strategy", f"Error generando señal para {symbol} {direction}", {"error": str(e)})

    if not all_signals:
        log_info("Strategy", "No se encontraron señales válidas")
        return None

    # Ordenar por speed_score descendente y elegir la mejor
    all_signals.sort(key=lambda x: x.speed_score, reverse=True)
    best = all_signals[0]
    log_info("Strategy", f"Mejor señal seleccionada: {best.symbol} {best.direction}", {
        "speed_score": best.speed_score,
        "entry": best.entry,
        "tp": best.tp,
        "sl": best.sl
    })
    return best


# ============================================================
# PRUEBA AUTÓNOMA (se ejecuta si se invoca directamente)
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("🧪 PRUEBA AUTÓNOMA: strategy.py")
    print("=" * 70)

    # Simular datos de prueba sin depender de signals real
    from dataclasses import dataclass
    from datetime import datetime, timezone

    @dataclass
    class MockSignal:
        symbol: str
        direction: str
        speed_score: float
        entry: float
        tp: float
        sl: float

    def mock_generate_signal(symbol, direction, speed_level):
        base_scores = {
            'BTC': {'Long': 0.85, 'Short': 0.60},
            'ETH': {'Long': 0.75, 'Short': 0.70},
            'SOL': {'Long': 0.65, 'Short': 0.55},
            'ADA': {'Long': 0.50, 'Short': 0.45},
            'XRP': {'Long': 0.40, 'Short': 0.35},
        }
        if symbol not in base_scores:
            return None
        score = base_scores[symbol].get(direction, 0.0)
        if score < 0.3:
            return None
        return MockSignal(
            symbol=symbol,
            direction=direction,
            speed_score=score * 1.2,
            entry=60000.0 if symbol == 'BTC' else 3000.0,
            tp=61000.0 if symbol == 'BTC' else 3100.0,
            sl=59000.0 if symbol == 'BTC' else 2900.0
        )

    # Reemplazar temporalmente generate_signal por el mock
    original_generate = generate_signal
    import builtins
    builtins.__dict__['generate_signal'] = mock_generate_signal

    # Ejecutar prueba
    test_symbols = ['BTC', 'ETH', 'SOL']
    speed_levels = {
        'BTC': {'Long': config.DEFAULT_SPEED_LEVEL, 'Short': config.DEFAULT_SPEED_LEVEL},
        'ETH': {'Long': config.DEFAULT_SPEED_LEVEL, 'Short': config.DEFAULT_SPEED_LEVEL},
        'SOL': {'Long': config.DEFAULT_SPEED_LEVEL, 'Short': config.DEFAULT_SPEED_LEVEL},
    }

    # Caso 1: lista normal
    best = get_best_signal(test_symbols, speed_levels)
    print("Caso 1 (todos los símbolos):", best.symbol, best.direction if best else "None")
    assert best and best.symbol == 'BTC', "Falló caso 1"

    # Caso 2: lista vacía
    best = get_best_signal([])
    print("Caso 2 (lista vacía):", best)
    assert best is None, "Falló caso 2"

    # Caso 3: símbolo inválido
    best = get_best_signal(['INVALID'])
    print("Caso 3 (símbolo inválido):", best)
    assert best is None, "Falló caso 3"

    # Caso 4: filtro de símbolos
    best = get_best_signal(['ETH', 'SOL'])
    print("Caso 4 (filtro ETH, SOL):", best.symbol if best else "None")
    assert best and best.symbol == 'ETH', "Falló caso 4"

    # Restaurar función original
    builtins.__dict__['generate_signal'] = original_generate

    print("\n✅ TODAS LAS PRUEBAS PASARON")
    import sys
    sys.exit(0)
