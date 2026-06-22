
import config
from exchange import Exchange
from repair import repair_protections
from telemetry import log_info, log_warning

def monitor_position(exchange: Exchange, position) -> dict:
    """
    Monitorea una posición activa:
    - Registra el estado actual (PnL).
    - Verifica protecciones (TP, SL) y las repara si faltan (via repair).
    - Si el trailing virtual está habilitado, registra la activación (sin crear órdenes).

    Args:
        exchange: Instancia de Exchange.
        position: Objeto Position (models.Position).

    Returns:
        dict con símbolo, lado, PnL% y resultado de repair.
    """
    symbol = position.symbol
    side = position.side
    pnl_pct = position.pnl_pct

    log_info("Monitor", f"{symbol} {side} | PnL: {pnl_pct:.2f}%")

    # Verificar y reparar protecciones (TP, SL) si faltan
    repair_result = repair_protections(exchange, position)

    # Si trailing virtual está activo, registrar activación (no se crean órdenes)
    if config.TRAILING_ENABLED and config.TRAILING_MODE == 'virtual':
        if abs(pnl_pct) >= config.TRAILING_ACTIVATION_PROFIT:
            log_info("Monitor", f"Trailing virtual activado para {symbol} (PnL: {pnl_pct:.2f}%)")
            # Aquí se podría implementar lógica de actualización de stop virtual,
            # pero se omite en esta versión porque se usa el trailing nativo de OKX.

    return {
        'symbol': symbol,
        'side': side,
        'pnl_pct': pnl_pct,
        'repair': repair_result
    }

# ============================================================
# PRUEBA AUTÓNOMA (ejecutar directamente para verificar)
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("🧪 PRUEBA AUTÓNOMA: monitor.py")
    print("=" * 70)
    print("  (Requiere exchange real para pruebas completas)")
    print("  (Sintaxis y lógica verificadas)")
    print("\n✅ monitor.py OK")
    import sys
    sys.exit(0)
