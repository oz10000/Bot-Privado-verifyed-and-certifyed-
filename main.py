
import os
import sys
import time
from datetime import datetime
from typing import Optional

import config
from exchange import Exchange
from strategy import get_best_signal
from repair import repair_protections
from monitor import monitor_position
from utils import acquire_lock, release_lock, validate_config, is_trading_time, health_check
from telemetry import log_info, log_error, log_warning, log_critical, log_debug

# ============================================================
# CONSTANTES DE ESTADO
# ============================================================
STATE_INIT                = "INIT"
STATE_LOAD_CONFIG         = "LOAD_CONFIG"
STATE_CONNECT_OKX         = "CONNECT_OKX"
STATE_SYNC_EXCHANGE       = "SYNC_EXCHANGE"
STATE_MONITOR_POSITION    = "MONITOR_POSITION"
STATE_POSITION_CLOSED     = "POSITION_CLOSED"
STATE_SEARCH_SIGNAL       = "SEARCH_SIGNAL"
STATE_VERIFY_POSITION     = "VERIFY_POSITION"
STATE_OPEN_POSITION       = "OPEN_POSITION"
STATE_CREATE_PROTECTIONS  = "CREATE_PROTECTIONS"
STATE_REPAIR_PROTECTIONS  = "REPAIR_PROTECTIONS"
STATE_WAIT_NEXT_CYCLE     = "WAIT_NEXT_CYCLE"
STATE_ERROR_RECOVERY      = "ERROR_RECOVERY"
STATE_SHUTDOWN            = "SHUTDOWN"

# ============================================================
# CLASE BOT
# ============================================================
class Bot:
    def __init__(self):
        self.state = STATE_INIT
        self.running = True
        self.error_count = 0
        self.max_errors = config.MAX_CONSECUTIVE_ERRORS
        self.exchange: Optional[Exchange] = None
        self.speed_levels = {}
        self._current_signal = None
        self._current_order = None
        self._symbols = config.SYMBOLS
        self._leverage = config.LEVERAGE
        self._trade_notional = config.TRADE_NOTIONAL
        self._lock_fd = None
        self.cycle_id = 0
        log_info("Main", "Bot inicializado")

    def run(self):
        """Bucle principal del bot."""
        # Locking
        self._lock_fd = acquire_lock()
        if self._lock_fd is None:
            log_critical("Main", "No se pudo adquirir lock, saliendo")
            return

        if not validate_config():
            log_critical("Main", "Configuración inválida, saliendo")
            release_lock(self._lock_fd)
            return

        log_info("Main", "Iniciando bucle principal")
        while self.running:
            self.cycle_id += 1
            cycle_start = time.time()
            try:
                # Health check liviano
                hc = health_check()
                if not hc.get('memory_ok') or not hc.get('disk_ok'):
                    log_warning("Main", "Health check falló", {"health": hc})
                    # Si es crítico, podríamos bloquear nuevas operaciones,
                    # pero seguimos monitoreando las posiciones existentes.

                self._run_state()

                # Watchdog: si el ciclo dura demasiado, registrar advertencia
                elapsed = time.time() - cycle_start
                if elapsed > config.MAX_CYCLE_DURATION_SEC:
                    log_warning("Main", "Ciclo largo", {"duration": elapsed, "cycle": self.cycle_id})

            except KeyboardInterrupt:
                log_info("Main", "Interrupción recibida")
                self.state = STATE_SHUTDOWN
                self._run_state()
                break
            except Exception as e:
                log_critical("Main", "Error inesperado", {"error": str(e), "cycle": self.cycle_id})
                self.state = STATE_ERROR_RECOVERY
                self._run_state()
                time.sleep(1)

        # Al salir del bucle, liberar lock
        if self._lock_fd:
            release_lock(self._lock_fd)
        log_info("Main", "Bot finalizado")

    def _run_state(self):
        """Ejecuta el estado actual y transiciona al siguiente."""
        log_debug("Main", f"Ciclo {self.cycle_id} Estado: {self.state}")

        if self.state == STATE_INIT:
            self._init()
        elif self.state == STATE_LOAD_CONFIG:
            self._load_config()
        elif self.state == STATE_CONNECT_OKX:
            self._connect_okx()
        elif self.state == STATE_SYNC_EXCHANGE:
            self._sync_exchange()
        elif self.state == STATE_MONITOR_POSITION:
            self._monitor_position()
        elif self.state == STATE_POSITION_CLOSED:
            self._position_closed()
        elif self.state == STATE_SEARCH_SIGNAL:
            self._search_signal()
        elif self.state == STATE_VERIFY_POSITION:
            self._verify_position()
        elif self.state == STATE_OPEN_POSITION:
            self._open_position()
        elif self.state == STATE_CREATE_PROTECTIONS:
            self._create_protections()
        elif self.state == STATE_REPAIR_PROTECTIONS:
            self._repair_protections()
        elif self.state == STATE_WAIT_NEXT_CYCLE:
            self._wait_next_cycle()
        elif self.state == STATE_ERROR_RECOVERY:
            self._error_recovery()
        elif self.state == STATE_SHUTDOWN:
            self._shutdown()
        else:
            log_error("Main", f"Estado desconocido: {self.state}, forzando SHUTDOWN")
            self.state = STATE_SHUTDOWN

    # ============================================================
    # IMPLEMENTACIÓN DE ESTADOS
    # ============================================================

    def _init(self):
        log_info("Main", "INIT -> LOAD_CONFIG")
        self.state = STATE_LOAD_CONFIG

    def _load_config(self):
        log_info("Main", "Cargando configuración")
        # AutoSpeed: se usa el nivel por defecto (ya optimizado)
        for sym in self._symbols:
            self.speed_levels[sym] = {
                'Long': config.DEFAULT_SPEED_LEVEL,
                'Short': config.DEFAULT_SPEED_LEVEL
            }
        self.state = STATE_CONNECT_OKX

    def _connect_okx(self):
        log_info("Main", "Conectando a OKX")
        api_key = os.environ.get('OKX_API_KEY')
        secret = os.environ.get('OKX_SECRET_KEY')
        passphrase = os.environ.get('OKX_PASSPHRASE')
        demo = os.environ.get('OKX_DEMO', 'true').lower() == 'true'

        if not api_key or not secret or not passphrase:
            log_error("Main", "Faltan credenciales de OKX en variables de entorno")
            self.state = STATE_ERROR_RECOVERY
            return

        self.exchange = Exchange(api_key, secret, passphrase, demo=demo)
        if self.exchange.connect():
            log_info("Main", "Conexión OKX exitosa")
            self.state = STATE_SYNC_EXCHANGE
        else:
            log_error("Main", "Conexión OKX fallida")
            self.state = STATE_ERROR_RECOVERY

    def _sync_exchange(self):
        log_info("Main", "Sincronizando con exchange")
        if not self.exchange:
            self.state = STATE_ERROR_RECOVERY
            return

        # Verificar horario de trading
        if not is_trading_time():
            log_info("Main", "Fuera de horario de trading, esperando")
            self.state = STATE_WAIT_NEXT_CYCLE
            return

        # Obtener posiciones actuales
        positions = self.exchange.get_positions()
        if not positions.get('ok'):
            log_error("Main", "Error obteniendo posiciones", {"error": positions.get('error')})
            self.state = STATE_ERROR_RECOVERY
            return

        active_positions = positions.get('data', [])
        if active_positions:
            log_info("Main", f"Posición activa detectada: {len(active_positions)}")
            self.state = STATE_MONITOR_POSITION
        else:
            log_info("Main", "Sin posiciones activas")
            self.state = STATE_SEARCH_SIGNAL

    def _monitor_position(self):
        log_info("Main", "Monitoreando posición")
        if not self.exchange:
            self.state = STATE_ERROR_RECOVERY
            return

        # Verificar si la posición sigue abierta
        positions = self.exchange.get_positions()
        if not positions.get('ok') or not positions.get('data'):
            log_info("Main", "Posición cerrada detectada")
            self.state = STATE_POSITION_CLOSED
            return

        # Para cada posición, ejecutar monitor y reparar si es necesario
        for pos in positions['data']:
            result = monitor_position(self.exchange, pos)
            if not result.get('repair', {}).get('sl', True):
                log_warning("Main", "SL faltante, reparando")
                self.state = STATE_REPAIR_PROTECTIONS
                return

        # Si todo está bien, esperar siguiente ciclo
        log_info("Main", "Protecciones verificadas, esperando siguiente ciclo")
        self.state = STATE_WAIT_NEXT_CYCLE

    def _position_closed(self):
        log_info("Main", "Posición cerrada, sincronizando...")
        self.state = STATE_SYNC_EXCHANGE

    def _search_signal(self):
        log_info("Main", "Buscando señales")
        if not self.exchange:
            self.state = STATE_ERROR_RECOVERY
            return

        signal = get_best_signal(self._symbols, self.speed_levels)
        if signal:
            log_info("Main", f"Señal encontrada: {signal.symbol} {signal.direction}")
            self._current_signal = signal
            self.state = STATE_VERIFY_POSITION
        else:
            log_info("Main", "No se encontraron señales")
            self.state = STATE_WAIT_NEXT_CYCLE

    def _verify_position(self):
        log_info("Main", "Verificando posición antes de abrir")
        if not self.exchange or not self._current_signal:
            self.state = STATE_ERROR_RECOVERY
            return

        symbol = self._current_signal.symbol
        if self.exchange.has_active_trade(symbol):
            log_warning("Main", f"Posición activa detectada para {symbol}, descartando señal")
            self._current_signal = None
            self.state = STATE_SEARCH_SIGNAL
        else:
            log_info("Main", "Sin posición activa, procediendo a abrir")
            self.state = STATE_OPEN_POSITION

    def _open_position(self):
        log_info("Main", "Abriendo posición")
        if not self.exchange or not self._current_signal:
            self.state = STATE_ERROR_RECOVERY
            return

        signal = self._current_signal
        side = 'buy' if signal.direction == 'Long' else 'sell'
        size = self._trade_notional / signal.entry

        result = self.exchange.place_market_order(signal.symbol, side, size, self._leverage)
        if result.get('ok'):
            log_info("Main", f"Orden abierta: {result['data'].ord_id}")
            self._current_order = result['data']
            self.state = STATE_CREATE_PROTECTIONS
        else:
            log_error("Main", f"Error abriendo orden: {result.get('error')}")
            self._current_signal = None
            self.state = STATE_ERROR_RECOVERY

    def _create_protections(self):
        log_info("Main", "Creando protecciones (TP/SL/Trailing)")
        if not self.exchange or not self._current_signal or not self._current_order:
            self.state = STATE_ERROR_RECOVERY
            return

        signal = self._current_signal
        size = self._trade_notional / signal.entry
        close_side = 'sell' if signal.direction == 'Long' else 'buy'

        # 1. TP y SL
        tp_res = self.exchange.place_algo_order(
            signal.symbol,
            close_side,
            size,
            tp_price=signal.tp,
            sl_price=signal.sl
        )
        if not tp_res.get('ok'):
            log_error("Main", f"Error creando TP/SL: {tp_res.get('error')}")
            self.state = STATE_REPAIR_PROTECTIONS
            return

        # 2. Trailing (si está habilitado)
        if config.TRAILING_ENABLED and config.TRAILING_MODE == 'native':
            trail_distance = signal.atr * config.TRAILING_DISTANCE_ATR
            trail_res = self.exchange.place_trailing_order(
                signal.symbol,
                close_side,
                size,
                trail_distance
            )
            if trail_res.get('ok'):
                log_info("Main", f"Trailing nativo creado: {trail_res['data'].algo_id}")
            else:
                log_warning("Main", f"Trailing falló, continuando sin él: {trail_res.get('error')}")

        self._current_signal = None
        self._current_order = None
        self.state = STATE_WAIT_NEXT_CYCLE

    def _repair_protections(self):
        log_info("Main", "Reparando protecciones")
        if not self.exchange:
            self.state = STATE_ERROR_RECOVERY
            return

        positions = self.exchange.get_positions()
        if not positions.get('ok') or not positions.get('data'):
            log_warning("Main", "No hay posición para reparar")
            self.state = STATE_SYNC_EXCHANGE
            return

        pos = positions['data'][0]
        rep = repair_protections(self.exchange, pos)
        if rep.get('sl'):
            log_info("Main", "Protecciones reparadas exitosamente")
            self.state = STATE_WAIT_NEXT_CYCLE
        else:
            log_error("Main", "Fallo reparando protecciones")
            self.state = STATE_ERROR_RECOVERY

    def _wait_next_cycle(self):
        log_info("Main", "Esperando 5 minutos para siguiente ciclo")
        time.sleep(300)  # 5 minutos
        self.state = STATE_SYNC_EXCHANGE

    def _error_recovery(self):
        log_info("Main", "Recuperando de error")
        self.error_count += 1
        if self.error_count >= self.max_errors:
            log_critical("Main", f"Máximo de errores ({self.max_errors}) alcanzado, apagando")
            self.state = STATE_SHUTDOWN
        else:
            log_warning("Main", f"Reintentando conexión ({self.error_count}/{self.max_errors})")
            time.sleep(config.RECONNECT_BACKOFF * self.error_count)
            self.state = STATE_CONNECT_OKX

    def _shutdown(self):
        log_info("Main", "Apagando bot")
        self.running = False
        if self.exchange:
            try:
                # Limpiar sesión si es necesario
                self.exchange.session.close()
            except Exception as e:
                log_error("Main", f"Error durante cierre de sesión: {e}")
        sys.exit(0)

# ============================================================
# PUNTO DE ENTRADA
# ============================================================
def main():
    bot = Bot()
    bot.run()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_critical("Main", f"Error fatal en main", {"error": str(e)})
        import traceback
        traceback.print_exc()
        sys.exit(1)
