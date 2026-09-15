"""Dominio criptoactivos: tablas, modelo, cálculo y lectura.

Espejo de portfolio.py pero para criptomonedas (BTC, ETH).
Precios históricos en tabla propia `cripto_precios` (no se mezcla con nav_history).
Operaciones en tabla propia `cripto_operaciones`.
"""
import os
import datetime
import sqlite3
from typing import Dict, List, Any

# --- RUTAS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "portfolio_history.db")

# --- CONFIG DE CRIPTOACTIVOS ---
CRYPTO_COINS = {
    'bitcoin': {
        'symbol': 'BTC',
        'name': 'Bitcoin',
        'color': '#f7931a',      # naranja Bitcoin
        'operador_default': 'Bitvavo',
        'par_binance': 'BTCEUR', # par EUR en Binance para el histórico de precios
    },
    'ethereum': {
        'symbol': 'ETH',
        'name': 'Ethereum',
        'color': '#627eea',      # azul Ethereum
        'operador_default': 'bit2me',
        'par_binance': 'ETHEUR',
    },
}

# Mapeo de símbolos legibles → ids CoinGecko (para datalist/modal)
SYMBOL_TO_CG = {v['symbol']: k for k, v in CRYPTO_COINS.items()}


# --- TABLAS ---
def init_cripto_db():
    """Crea las tablas cripto_operaciones y cripto_precios si no existen."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cripto_operaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                fecha TEXT NOT NULL,
                importe REAL NOT NULL,
                cantidad REAL NOT NULL,
                precio_unitario REAL NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'Compra',
                operador TEXT,
                fuente TEXT NOT NULL DEFAULT 'manual',
                UNIQUE(fecha, symbol, cantidad, importe)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cripto_precios (
                symbol TEXT NOT NULL,
                fecha TEXT NOT NULL,
                precio_eur REAL NOT NULL,
                PRIMARY KEY (symbol, fecha)
            )
        """)
        conn.commit()


# --- OPERACIONES ---
def insert_cripto_operacion(symbol: str, fecha: str, importe: float,
                            cantidad: float, precio_unitario: float = 0.0,
                            operador: str = '', fuente: str = 'manual',
                            tipo: str = 'Compra') -> int:
    """Inserta una operación de cripto. Devuelve id o 0 si duplicada."""
    if importe <= 0 or cantidad <= 0:
        raise ValueError('Importe y cantidad deben ser mayores que 0')
    precio = precio_unitario if precio_unitario > 0 else (importe / cantidad)
    init_cripto_db()
    with sqlite3.connect(DB_PATH) as conn:
        try:
            cur = conn.execute(
                "INSERT INTO cripto_operaciones "
                "(symbol, fecha, importe, cantidad, precio_unitario, tipo, operador, fuente) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, fecha, round(importe, 2), round(cantidad, 8),
                 round(precio, 4), tipo, operador or None, fuente)
            )
            conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return 0  # ya existía


def cripto_compra_existe_alta(symbol: str, fecha: str,
                              importe: float, cantidad: float) -> bool:
    """Comprueba si una compra de cripto ya está registrada."""
    init_cripto_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM cripto_operaciones "
            "WHERE fecha = ? AND symbol = ? "
            "AND ROUND(cantidad, 8) = ROUND(?, 8) "
            "AND ROUND(importe, 2) = ROUND(?, 2)",
            (fecha, symbol, cantidad, importe)
        ).fetchone()
        return row is not None


def get_all_cripto_operaciones() -> List[Dict[str, Any]]:
    """Devuelve todas las operaciones de cripto ordenadas por fecha DESC."""
    init_cripto_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, symbol, fecha, importe, cantidad, precio_unitario, "
            "tipo, operador, fuente "
            "FROM cripto_operaciones ORDER BY fecha DESC, id DESC"
        ).fetchall()
    return [{
        'id': r[0], 'symbol': r[1], 'fecha': r[2], 'importe': r[3],
        'cantidad': r[4], 'precio_unitario': r[5], 'tipo': r[6],
        'operador': r[7] or '', 'fuente': r[8]
    } for r in rows]


# --- PRECIOS ---
def get_cripto_precio_map(symbol: str) -> Dict[str, float]:
    """Devuelve {fecha: precio_eur} para un symbol (CoinGecko id)."""
    init_cripto_db()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT fecha, precio_eur FROM cripto_precios WHERE symbol = ?",
            (symbol,)
        ).fetchall()
    return {row[0]: row[1] for row in rows}


def save_cripto_precio(symbol: str, fecha_str: str, precio_eur: float):
    """Guarda o actualiza el precio de un criptoactivo en un día."""
    if precio_eur <= 0:
        return
    init_cripto_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cripto_precios (symbol, fecha, precio_eur) "
            "VALUES (?, ?, ?)",
            (symbol, fecha_str, precio_eur)
        )
        conn.commit()


# --- LECTURA DE MERCADO (espejo de fetch_market_nav) ---
def fetch_cripto_market(symbol: str) -> Dict[str, Any]:
    """Lee el precio más reciente y variaciones de cripto_precios."""
    precio_map = get_cripto_precio_map(symbol)
    if not precio_map:
        return {'precio': 0.0, 'fecha': '-', 'd1': 0.0, 'w1': 0.0, 'm1': 0.0, 'y1': None}

    precio_by_date = {
        datetime.datetime.strptime(d, '%Y-%m-%d').date(): v
        for d, v in precio_map.items()
    }
    sorted_dates = sorted(precio_by_date.keys())
    latest = sorted_dates[-1]
    live = precio_by_date[latest]
    latest_str = latest.strftime('%Y-%m-%d')

    def closest(target_days, max_window=10):
        target = latest - datetime.timedelta(days=target_days)
        for i in range(max_window):
            check = target - datetime.timedelta(days=i)
            if check in precio_by_date:
                return precio_by_date[check]
        return None

    prev = precio_by_date[sorted_dates[-2]] if len(sorted_dates) >= 2 else live
    d1 = round(((live - prev) / prev) * 100, 2) if prev else 0.0

    w1_nav = closest(7, 10)
    w1 = round(((live - w1_nav) / w1_nav) * 100, 2) if w1_nav else 0.0

    m1_nav = closest(30, 15)
    m1 = round(((live - m1_nav) / m1_nav) * 100, 2) if m1_nav else 0.0

    y1_nav = closest(365, 30)
    y1 = round(((live - y1_nav) / y1_nav) * 100, 2) if y1_nav else None

    return {
        'precio': live,
        'fecha': latest_str,
        'd1': d1, 'w1': w1, 'm1': m1, 'y1': y1,
    }


# --- SERIES TEMPORALES (espejo de generate_fund_timeseries) ---
def generate_cripto_timeseries(symbol: str, orders: List[Dict[str, Any]],
                               start_date: datetime.date,
                               today: datetime.date) -> List[Dict[str, Any]]:
    """Serie diaria del valor de una posición de cripto."""
    if not orders:
        return []

    sorted_orders = sorted(orders, key=lambda x: x['date_obj'])
    cripto_start = sorted_orders[0]['date_obj']
    precio_map = get_cripto_precio_map(symbol)

    events_by_date: Dict[datetime.date, List[Dict[str, Any]]] = {}
    for o in sorted_orders:
        events_by_date.setdefault(o['date_obj'], []).append(o)

    cur_cant = 0.0
    cur_inv = 0.0
    series = []
    last_price = (sorted_orders[0]['precio_unitario']
                  if sorted_orders[0]['precio_unitario'] > 0 else 1.0)

    cur = cripto_start
    while cur <= today:
        d_str = cur.strftime('%Y-%m-%d')

        if cur in events_by_date:
            for ev in events_by_date[cur]:
                cur_cant += ev['cantidad']
                cur_inv += ev['importe']

        if d_str in precio_map and precio_map[d_str] > 0:
            last_price = precio_map[d_str]

        val = cur_cant * last_price
        gain_eur = val - cur_inv if cur_inv > 0 else 0.0
        gain_pct = (gain_eur / cur_inv * 100) if cur_inv > 0 else 0.0

        if cur_cant > 0:
            series.append({
                'date': d_str,
                'price': round(last_price, 2),
                'market_value': round(val, 2),
                'invested': round(cur_inv, 2),
                'gain_pct': round(gain_pct, 2)
            })

        cur += datetime.timedelta(days=1)

    return series


# --- RESUMEN COMPLETO (espejo de get_portfolio_summary) ---
def get_cripto_portfolio_summary() -> Dict[str, Any]:
    """Devuelve el resumen completo del portfolio de criptoactivos."""
    init_cripto_db()
    ops = get_all_cripto_operaciones()
    today = datetime.date.today()

    # Agrupar operaciones por symbol
    orders_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for op in ops:
        sym = op['symbol']
        dt = datetime.datetime.strptime(op['fecha'], '%Y-%m-%d').date()
        if sym not in orders_by_symbol:
            orders_by_symbol[sym] = []
        orders_by_symbol[sym].append({
            'fecha': op['fecha'],
            'date_obj': dt,
            'symbol': sym,
            'importe': op['importe'],
            'cantidad': op['cantidad'],
            'precio_unitario': op['precio_unitario'],
            'tipo': op['tipo'] or 'Compra',
            'operador': op['operador'] or CRYPTO_COINS.get(sym, {}).get('operador_default', ''),
        })

    activos = []
    tot_invested = 0.0
    tot_value = 0.0

    all_symbols = sorted(orders_by_symbol.keys())

    # Operaciones planas para la tabla de historial
    all_flat = []
    for sym, o_list in orders_by_symbol.items():
        meta = CRYPTO_COINS.get(sym, {'symbol': sym, 'name': sym})
        for o in o_list:
            all_flat.append({
                'fecha': o['fecha'],
                'symbol': sym,
                'symbol_legible': meta.get('symbol', sym),
                'nombre': meta.get('name', sym),
                'tipo': o.get('tipo', 'Compra'),
                'operador': o.get('operador', ''),
                'importe': o['importe'],
                'cantidad': o['cantidad'],
                'precio_unitario': o['precio_unitario'],
            })
    all_flat.sort(key=lambda x: x['fecha'], reverse=True)

    for sym in all_symbols:
        o_list = orders_by_symbol[sym]
        total_cant = sum(o['cantidad'] for o in o_list)
        total_inv = sum(o['importe'] for o in o_list)
        first_date = o_list[0]['date_obj']
        days_active = (today - first_date).days

        market = fetch_cripto_market(sym)
        precio_actual = market['precio']
        valor_actual = total_cant * precio_actual
        gain_eur = valor_actual - total_inv
        gain_pct = (gain_eur / total_inv * 100) if total_inv > 0 else 0.0

        meta = CRYPTO_COINS.get(sym, {'symbol': sym, 'name': sym, 'operador_default': ''})
        activos.append({
            'symbol': sym,
            'symbol_legible': meta.get('symbol', sym),
            'name': meta.get('name', sym),
            'color': meta.get('color', '#94a3b8'),
            'operador': meta.get('operador_default', ''),
            'fecha_primera_compra': first_date.strftime('%d/%m/%Y'),
            'days_active': days_active,
            'cantidad': round(total_cant, 8),
            'invertido': round(total_inv, 2),
            'precio_actual': precio_actual,
            'fecha_precio': market.get('fecha', '-'),
            'valor_actual': round(valor_actual, 2),
            'beneficio_eur': round(gain_eur, 2),
            'beneficio_pct': round(gain_pct, 2),
            'variacion_dia': market.get('d1', 0.0),
            'variacion_semana': market.get('w1', 0.0),
            'variacion_mes': market.get('m1', 0.0),
            'variacion_ano': market.get('y1', None),
            'ordenes_count': len(o_list),
        })
        tot_invested += total_inv
        tot_value += valor_actual

    activos.sort(key=lambda x: -x['valor_actual'])

    for a in activos:
        a['peso_pct'] = round((a['valor_actual'] / tot_value * 100), 2) if tot_value > 0 else 0.0

    tot_gain = tot_value - tot_invested
    tot_pct = (tot_gain / tot_invested * 100) if tot_invested > 0 else 0.0

    # --- Series temporales ---
    all_dates = [o['date_obj'] for sym in orders_by_symbol for o in orders_by_symbol[sym]]
    if all_dates:
        start_date = min(all_dates)
        fund_series = {}
        for sym in all_symbols:
            fund_series[sym] = generate_cripto_timeseries(
                sym, orders_by_symbol[sym], start_date, today)

        # Agregar serie de portfolio total
        date_map: Dict[str, Dict[str, float]] = {}
        for sym, s_list in fund_series.items():
            for pt in s_list:
                d_str = pt['date']
                if d_str not in date_map:
                    date_map[d_str] = {'invested': 0.0, 'market_value': 0.0}
                date_map[d_str]['invested'] += pt['invested']
                date_map[d_str]['market_value'] += pt['market_value']

        portfolio_series = []
        for d_str in sorted(date_map.keys()):
            inv = date_map[d_str]['invested']
            val = date_map[d_str]['market_value']
            if inv > 0:
                gain_eur = val - inv
                gain_pct = (gain_eur / inv * 100) if inv > 0 else 0.0
                portfolio_series.append({
                    'date': d_str,
                    'invested': round(inv, 2),
                    'market_value': round(val, 2),
                    'gain_eur': round(gain_eur, 2),
                    'gain_pct': round(gain_pct, 2)
                })
    else:
        portfolio_series = []
        fund_series = {}

    return {
        'totales': {
            'invertido': round(tot_invested, 2),
            'valor_mercado': round(tot_value, 2),
            'beneficio_eur': round(tot_gain, 2),
            'beneficio_pct': round(tot_pct, 2),
            'activos_count': len(activos),
            'actualizado': datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        },
        'activos': activos,
        'timeseries': portfolio_series,
        'crypto_timeseries': fund_series,
        'operaciones': all_flat,
    }
