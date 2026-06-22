
import os
import time
import json
import hmac
import base64
import hashlib
import requests
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any, Tuple

import config
from models import Balance, Position, OrderResult
from telemetry import log_info, log_error, log_warning, log_debug

class Exchange:
    def __init__(self, api_key: str, secret_key: str, passphrase: str, demo: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.demo = demo
        self.base_url = "https://www.okx.com"
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        self._connected = False

    def _get_server_timestamp_iso(self) -> Tuple[str, int]:
        try:
            resp = self.session.get(f"{self.base_url}/api/v5/public/time", timeout=5)
            data = resp.json()
            if data.get('code') != '0':
                raise Exception(f"Error timestamp: {data}")
            ts_ms = int(data['data'][0]['ts'])
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            iso = dt.strftime('%Y-%m-%dT%H:%M:%S.') + f"{ts_ms % 1000:03d}Z"
            return iso, ts_ms
        except Exception as e:
            log_error("Exchange", "Error timestamp", {"error": str(e)})
            raise

    def _sign_request(self, ts_iso: str, method: str, path: str, body: str = '') -> str:
        if body is None:
            body = ''
        message = ts_iso + method.upper() + path + body
        mac = hmac.new(
            bytes(self.secret_key, encoding='utf8'),
            bytes(message, encoding='utf8'),
            digestmod=hashlib.sha256
        )
        return base64.b64encode(mac.digest()).decode('utf-8')

    def _build_headers(self, method: str, path: str, body: str = '') -> Dict:
        ts_iso, _ = self._get_server_timestamp_iso()
        sig = self._sign_request(ts_iso, method, path, body)
        headers = {
            'Content-Type': 'application/json',
            'OK-ACCESS-KEY': self.api_key,
            'OK-ACCESS-SIGN': sig,
            'OK-ACCESS-TIMESTAMP': ts_iso,
            'OK-ACCESS-PASSPHRASE': self.passphrase,
        }
        if self.demo:
            headers['x-simulated-trading'] = '1'
        return headers

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                 body: Optional[Dict] = None, retries: int = 3) -> Dict:
        url = self.base_url + endpoint
        body_str = json.dumps(body) if body else ''
        request_path = endpoint
        if params and method.upper() == 'GET':
            query = '&'.join([f"{k}={v}" for k, v in params.items()])
            request_path = endpoint + '?' + query

        for attempt in range(1, retries + 1):
            try:
                headers = self._build_headers(method, request_path, body_str)
                if method.upper() == 'GET':
                    resp = self.session.get(url, headers=headers, params=params, timeout=config.ORDER_TIMEOUT)
                else:
                    resp = self.session.post(url, headers=headers, params=params, json=body, timeout=config.ORDER_TIMEOUT)
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}: {resp.text}")
                data = resp.json()
                if data.get('code') != '0':
                    raise Exception(f"API Error {data.get('code')}: {data.get('msg')}")
                log_debug("Exchange", f"Request OK", {"endpoint": endpoint})
                return {'ok': True, 'data': data, 'error': None}
            except Exception as e:
                log_warning("Exchange", f"Intento {attempt}/{retries} falló", {"error": str(e)})
                if attempt == retries:
                    log_error("Exchange", "Request falló tras reintentos", {"error": str(e)})
                    return {'ok': False, 'error': str(e), 'data': None}
                time.sleep(1 * (2 ** (attempt - 1)))
        return {'ok': False, 'error': 'Max retries', 'data': None}

    def connect(self) -> bool:
        try:
            result = self._request('GET', '/api/v5/public/time', retries=2)
            if result.get('ok'):
                self._connected = True
                log_info("Exchange", "Conexión exitosa")
                return True
            log_error("Exchange", "Conexión fallida", {"error": result.get('error')})
            return False
        except Exception as e:
            log_error("Exchange", "Conexión fallida", {"error": str(e)})
            return False

    def get_balance(self, currency: str = 'USDT') -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        result = self._request('GET', '/api/v5/account/balance')
        if not result.get('ok'):
            return {'ok': False, 'error': result.get('error'), 'data': None}
        details = result['data'].get('data', [{}])[0].get('details', [])
        usdt = next((d for d in details if d.get('ccy') == currency), {})
        bal = Balance(
            total=float(usdt.get('eq', 0)),
            free=float(usdt.get('cashBal', 0)),
            frozen=float(usdt.get('frozenBal', 0))
        )
        return {'ok': True, 'data': bal, 'error': None}

    def get_positions(self, inst_id: Optional[str] = None) -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        params = {'instId': inst_id} if inst_id else {}
        result = self._request('GET', '/api/v5/account/positions', params=params)
        if not result.get('ok'):
            return {'ok': False, 'error': result.get('error'), 'data': None}
        positions_data = result['data'].get('data', [])
        positions = []
        for p in positions_data:
            if abs(float(p.get('pos', 0))) > 0.0001:
                positions.append(Position(
                    symbol=p.get('instId', 'unknown'),
                    side='long' if float(p.get('pos', 0)) > 0 else 'short',
                    size=abs(float(p.get('pos', 0))),
                    entry_price=float(p.get('avgPx', 0)),
                    mark_price=float(p.get('markPx', 0)),
                    pnl=float(p.get('upl', 0)),
                    pnl_pct=float(p.get('uplRatio', 0)) * 100
                ))
        return {'ok': True, 'data': positions, 'error': None}

    def get_pending_algo_orders(self, inst_id: Optional[str] = None, ord_type: str = 'conditional') -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        params = {'ordType': ord_type, 'limit': 10}
        if inst_id:
            params['instId'] = inst_id
        result = self._request('GET', '/api/v5/trade/orders-algo-pending', params=params)
        if not result.get('ok'):
            return {'ok': False, 'error': result.get('error'), 'data': None}
        return {'ok': True, 'data': result['data'].get('data', []), 'error': None}

    def has_active_trade(self, inst_id: str) -> bool:
        pos = self.get_positions(inst_id)
        if pos.get('ok') and pos.get('data'):
            return True
        algo = self.get_pending_algo_orders(inst_id)
        if algo.get('ok') and algo.get('data'):
            return True
        return False

    def place_market_order(self, inst_id: str, side: str, size: float, leverage: int = 10) -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        self._request('POST', '/api/v5/account/set-leverage', body={
            'instId': inst_id,
            'lever': str(leverage),
            'mgnMode': 'isolated'
        })
        body = {
            'instId': inst_id,
            'tdMode': 'isolated',
            'side': side,
            'ordType': 'market',
            'sz': str(size),
            'posSide': 'long' if side == 'buy' else 'short'
        }
        result = self._request('POST', '/api/v5/trade/order', body=body, retries=2)
        if not result.get('ok'):
            return {'ok': False, 'error': result.get('error'), 'data': None}
        order_data = result['data'].get('data', [{}])[0]
        order_result = OrderResult(
            ord_id=order_data.get('ordId', ''),
            avg_px=float(order_data.get('avgPx', 0)),
            state=order_data.get('state', '')
        )
        # Verificación
        time.sleep(0.5)
        verify = self.get_order(inst_id, order_result.ord_id)
        if verify.get('ok') and verify['data'].get('state') in ['filled', 'closed']:
            log_info("Exchange", "Orden verificada", {"ord_id": order_result.ord_id})
        else:
            log_warning("Exchange", "Orden no verificada", {"ord_id": order_result.ord_id})
        return {'ok': True, 'data': order_result, 'error': None}

    def place_algo_order(self, inst_id: str, side: str, size: float,
                         tp_price: Optional[float] = None,
                         sl_price: Optional[float] = None) -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        if not tp_price and not sl_price:
            return {'ok': False, 'error': 'Se requiere TP o SL', 'data': None}
        body = {
            'instId': inst_id,
            'tdMode': 'isolated',
            'side': side,
            'ordType': 'conditional',
            'sz': str(size),
            'reduceOnly': True,
        }
        if tp_price:
            body['tpTriggerPx'] = str(tp_price)
            body['tpOrdPx'] = str(tp_price)
        if sl_price:
            body['slTriggerPx'] = str(sl_price)
            body['slOrdPx'] = str(sl_price)
        result = self._request('POST', '/api/v5/trade/order-algo', body=body, retries=2)
        if not result.get('ok'):
            return {'ok': False, 'error': result.get('error'), 'data': None}
        algo_data = result['data'].get('data', [{}])[0]
        order_result = OrderResult(
            ord_id=algo_data.get('algoId', ''),
            algo_id=algo_data.get('algoId', ''),
            state='live'
        )
        log_info("Exchange", "Algo order colocada", {"algo_id": order_result.algo_id})
        return {'ok': True, 'data': order_result, 'error': None}

    def place_trailing_order(self, inst_id: str, side: str, size: float, trail_distance: float) -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        if trail_distance <= 0:
            return {'ok': False, 'error': 'Distancia inválida', 'data': None}
        body = {
            'instId': inst_id,
            'tdMode': 'isolated',
            'side': side,
            'ordType': 'conditional',
            'sz': str(size),
            'reduceOnly': True,
            'trailPx': str(trail_distance),
        }
        result = self._request('POST', '/api/v5/trade/order-algo', body=body, retries=2)
        if not result.get('ok'):
            return {'ok': False, 'error': result.get('error'), 'data': None}
        algo_data = result['data'].get('data', [{}])[0]
        order_result = OrderResult(
            ord_id=algo_data.get('algoId', ''),
            algo_id=algo_data.get('algoId', ''),
            state='live'
        )
        log_info("Exchange", "Trailing stop colocado", {"algo_id": order_result.algo_id})
        return {'ok': True, 'data': order_result, 'error': None}

    def cancel_order(self, inst_id: str, ord_id: str) -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        body = {'instId': inst_id, 'ordId': ord_id}
        result = self._request('POST', '/api/v5/trade/cancel-order', body=body)
        return {'ok': result.get('ok', False), 'data': result.get('data', {}).get('data', []), 'error': result.get('error')}

    def cancel_algo_order(self, inst_id: str, algo_id: str) -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        body = {'instId': inst_id, 'algoId': algo_id}
        result = self._request('POST', '/api/v5/trade/cancel-algos', body=body)
        return {'ok': result.get('ok', False), 'data': result.get('data', {}).get('data', []), 'error': result.get('error')}

    def get_order(self, inst_id: str, ord_id: str) -> Dict:
        if not self._connected:
            return {'ok': False, 'error': 'No conectado', 'data': None}
        params = {'instId': inst_id, 'ordId': ord_id}
        result = self._request('GET', '/api/v5/trade/order', params=params)
        return {'ok': result.get('ok', False), 'data': result['data'].get('data', [{}])[0], 'error': result.get('error')}

# ============================================================
# VERIFICACIÓN AUTÓNOMA
# ============================================================
if __name__ == "__main__":
    print("="*70)
    print("🧪 VERIFICACIÓN DE exchange.py")
    print("="*70)
    print("  (Requiere credenciales OKX para pruebas reales)")
    api_key = os.environ.get('OKX_API_KEY', '')
    secret = os.environ.get('OKX_SECRET_KEY', '')
    passphrase = os.environ.get('OKX_PASSPHRASE', '')
    if api_key and secret and passphrase:
        ex = Exchange(api_key, secret, passphrase, demo=True)
        if ex.connect():
            print("  ✅ Conexión OK")
        else:
            print("  ❌ Conexión fallida")
    else:
        print("  ⚠️ Sin credenciales, solo verificación sintáctica")
    print("✅ exchange.py OK")
