
import os
import sys
import time
import fcntl
import requests
from typing import Optional, Dict, Any
from telemetry import log_info, log_warning, log_error
import config

# ============================================================
# LOCKING (evitar ejecuciones simultáneas)
# ============================================================

def acquire_lock(lock_file: str = config.LOCK_FILE, timeout: int = config.LOCK_TIMEOUT) -> Optional[int]:
    """
    Adquiere un lock exclusivo usando fcntl.flock.
    Retorna el descriptor de archivo o None si falla.
    """
    try:
        fd = open(lock_file, 'w')
        start = time.time()
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                log_info("Utils", f"Lock adquirido: {lock_file}")
                return fd
            except BlockingIOError:
                if time.time() - start > timeout:
                    log_warning("Utils", f"Timeout adquiriendo lock: {lock_file}")
                    return None
                time.sleep(0.5)
    except Exception as e:
        log_error("Utils", f"Error adquiriendo lock: {e}")
        return None

def release_lock(fd: Optional[int]) -> None:
    """Libera el lock y cierra el archivo."""
    if fd is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
            log_info("Utils", "Lock liberado")
        except Exception as e:
            log_error("Utils", f"Error liberando lock: {e}")

# ============================================================
# VALIDACIÓN DE CONFIGURACIÓN
# ============================================================

def validate_config() -> bool:
    """
    Valida la configuración esencial del bot.
    Retorna True si es válida, False en caso contrario.
    """
    if not config.SYMBOLS:
        log_error("Utils", "SYMBOLS vacío")
        return False
    if config.LEVERAGE <= 0:
        log_error("Utils", "LEVERAGE inválido (<= 0)")
        return False
    if config.TP_MULT <= 0 or config.SL_MULT <= 0:
        log_error("Utils", "TP_MULT o SL_MULT inválidos (<= 0)")
        return False
    if config.TRAILING_ENABLED and config.TRAILING_DISTANCE_ATR <= 0:
        log_error("Utils", "TRAILING_DISTANCE_ATR inválido (<= 0)")
        return False
    return True

# ============================================================
# FILTRO HORARIO
# ============================================================

def is_trading_time() -> bool:
    """
    Verifica si la hora actual está dentro del filtro horario configurado.
    Si TIME_FILTER_ENABLED es False, siempre retorna True.
    """
    if not config.TIME_FILTER_ENABLED:
        return True
    now = time.gmtime()
    weekday = now.tm_wday
    hour = now.tm_hour + now.tm_min / 60.0
    if weekday not in config.TIME_FILTER_WEEKDAYS:
        return False
    return config.TIME_FILTER_START <= hour < config.TIME_FILTER_END

# ============================================================
# HEALTH CHECK (memoria, disco, latencia)
# ============================================================

def health_check() -> Dict[str, bool]:
    """
    Realiza un health check liviano:
    - Memoria disponible (psutil)
    - Espacio en disco (psutil)
    - Latencia hacia OKX (requests)
    Retorna diccionario con banderas de estado.
    """
    status = {'memory_ok': True, 'disk_ok': True, 'latency_ok': True}
    try:
        import psutil
        mem = psutil.virtual_memory()
        used_mb = mem.used / (1024 * 1024)
        if used_mb > config.MAX_MEMORY_MB:
            status['memory_ok'] = False
            log_warning("Utils", "Memoria excedida", {"used_mb": used_mb})
    except ImportError:
        log_warning("Utils", "psutil no instalado, omitiendo health check de memoria/disco")
    except Exception as e:
        log_warning("Utils", "Error en health check de memoria", {"error": str(e)})

    try:
        import psutil
        disk = psutil.disk_usage('.')
        used_mb = disk.used / (1024 * 1024)
        if used_mb > config.MAX_DISK_USAGE_MB:
            status['disk_ok'] = False
            log_warning("Utils", "Disco excedido", {"used_mb": used_mb})
    except ImportError:
        pass
    except Exception as e:
        log_warning("Utils", "Error en health check de disco", {"error": str(e)})

    try:
        start = time.time()
        requests.get("https://www.okx.com/api/v5/public/time", timeout=5)
        latency = (time.time() - start) * 1000
        if latency > config.MAX_LATENCY_MS:
            status['latency_ok'] = False
            log_warning("Utils", "Latencia alta", {"latency_ms": latency})
    except Exception as e:
        status['latency_ok'] = False
        log_warning("Utils", "Latencia fallida", {"error": str(e)})

    return status

# ============================================================
# PRUEBA AUTÓNOMA (ejecutar directamente para verificar)
# ============================================================
if __name__ == "__main__":
    print("="*70)
    print("🧪 PRUEBA AUTÓNOMA: utils.py")
    print("="*70)

    # Probar locking
    fd = acquire_lock('.test_lock', timeout=2)
    if fd:
        print("  ✅ Lock adquirido")
        release_lock(fd)
    else:
        print("  ⚠️ No se pudo adquirir lock (puede ser normal en Windows)")

    # Probar validación
    print(f"  Config valid: {validate_config()}")

    # Probar filtro horario
    print(f"  Trading time: {is_trading_time()}")

    # Probar health check
    hc = health_check()
    print(f"  Health: {hc}")

    print("\n✅ utils.py OK")
    sys.exit(0)
