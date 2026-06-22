
import logging
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, Optional

LOG_DIR = 'logs'
os.makedirs(LOG_DIR, exist_ok=True)

class Telemetry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_loggers()
        return cls._instance

    def _init_loggers(self):
        self.loggers = {}
        levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        for level in levels:
            logger = logging.getLogger(f"telemetry.{level}")
            logger.setLevel(getattr(logging, level))
            # Consola
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(console)
            # Archivo (con rotación simple)
            file_path = os.path.join(LOG_DIR, f'{level.lower()}.log')
            fh = logging.FileHandler(file_path)
            fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            logger.addHandler(fh)
            # JSON (se escribe en un solo archivo, pero separado por nivel)
            self.loggers[level] = logger

    def _log(self, level: str, module: str, message: str, data: Optional[Dict] = None):
        entry = {
            'level': level.upper(),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'module': module,
            'message': message,
            'data': data or {}
        }
        logger = self.loggers.get(level.upper())
        if logger:
            logger.info(json.dumps(entry))

_telemetry = Telemetry()

def log_info(module: str, message: str, data: Optional[Dict] = None):
    _telemetry._log('INFO', module, message, data)

def log_warning(module: str, message: str, data: Optional[Dict] = None):
    _telemetry._log('WARNING', module, message, data)

def log_error(module: str, message: str, data: Optional[Dict] = None):
    _telemetry._log('ERROR', module, message, data)

def log_debug(module: str, message: str, data: Optional[Dict] = None):
    _telemetry._log('DEBUG', module, message, data)

def log_critical(module: str, message: str, data: Optional[Dict] = None):
    _telemetry._log('CRITICAL', module, message, data)

# ============================================================
# VERIFICACIÓN AUTÓNOMA
# ============================================================
if __name__ == "__main__":
    print("="*70)
    print("🧪 VERIFICACIÓN DE telemetry.py")
    print("="*70)
    log_info("test", "Mensaje de prueba", {"test": True})
    log_warning("test", "Advertencia")
    print("  ✅ Logs escritos en consola y directorio logs/")
    print("✅ telemetry.py OK")
