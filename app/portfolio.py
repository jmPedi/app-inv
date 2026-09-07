import os
import glob
import csv
import datetime
import sqlite3
from typing import Dict, List, Any
import mstarpy

# --- CONFIGURACIÓN DE RUTAS Y BASE DE DATOS ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "portfolio_history.db")

def init_db():
    """Inicializa la base de datos SQLite para almacenar el historial de NAVs."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS nav_history (
                isin TEXT NOT NULL,
                fecha TEXT NOT NULL,
                nav REAL NOT NULL,
                PRIMARY KEY (isin, fecha)
            )
        """)
        conn.commit()

def get_stored_nav_map(isin: str) -> Dict[str, float]:
    """Obtiene todo el historial de NAVs guardados en SQLite para un ISIN."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT fecha, nav FROM nav_history WHERE isin = ?", (isin,))
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}

def save_nav_to_db(isin: str, fecha_str: str, nav: float):
    """Guarda o actualiza un NAV específico en la base de datos."""
    if nav <= 0:
        return
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO nav_history (isin, fecha, nav) VALUES (?, ?, ?)",
            (isin, fecha_str, nav)
        )
        conn.commit()

def populate_missing_history(isin: str, first_order_date: datetime.date):
    """
    Descarga el historial completo si detecta que faltan datos en la base de datos.
    """
    existing_navs = get_stored_nav_map(isin)
    
    # Ampliamos el margen a 100 días para asegurar que descargue la serie continua,
    # no solo los días sueltos de tus compras.
    if len(existing_navs) > 100:
        return

    try:
        start_date = first_order_date - datetime.timedelta(days=30)
        end_date = datetime.date.today()
        
        fund = mstarpy.Funds(term=isin, country='es')
        history = fund.historicalData(start_date=start_date, end_date=end_date)
        
        if history and 'nav' in history:
            for item in history['nav']:
                date_str = item['date'].split('T')[0]
                nav_val = float(item['nav'])
                save_nav_to_db(isin, date_str, nav_val)
                
    except Exception as e:
        print(f"Aviso: No se pudo descargar historial de Morningstar para {isin}: {e}")

# --- FONDOS Y METADATOS ---
KNOWN_FUNDS = {
    'IE000ZYRH0Q7': {
        'name': 'iShares Developed World Index (IE) S Acc EUR',
        'short_name': 'iShares Developed World',
        'category': 'RV Global Desarrollados',
        'ter': '0.06%',
        'risk': 4,
        'operador': 'myInvestor'
    },
    'IE000QAZP7L2': {
        'name': 'iShares Emerging Markets Index Fund (IE) S Acc EUR',
        'short_name': 'iShares Emerging Markets',
        'category': 'RV Emergentes',
        'ter': '0.16%',
        'risk': 5,
        'operador': 'myInvestor'
    },
    'ES0146309002': {
        'name': 'Horos Value Internacional FI',
        'short_name': 'Horos Value Internacional',
        'category': 'RV Global Value',
        'ter': '1.80%',
        'risk': 6,
        'operador': 'Horos'
    },
    'LU3256039929': {
        'name': 'Silverway Global - Apex Equity R',
        'short_name': 'Silverway Global Apex',
        'category': 'RV Global Concentrada',
        'ter': '2.10%',
        'risk': 5,
        'operador': 'Silverway'
    },
    'IE00BYX5MX67': {
        'name': 'Fidelity S&P 500 Index Fund',
        'short_name': 'Fidelity S&P 500',
        'category': 'RV USA (Traspasado)',
        'ter': '0.06%',
        'risk': 5,
        'operador': 'myInvestor'
    },
    'IE00BFZMJT78': {
        'name': 'Neuberger Berman Short Duration Euro Bond EUR I Acc',
        'short_name': 'Neuberger Berman Short Duration',
        'category': 'Renta Fija Corto Plazo (Traspasado)',
        'ter': '0.21%',
        'risk': 2,
        'operador': 'myInvestor'
    }
}

ACTIVE_ISINS = ['IE000ZYRH0Q7', 'IE000QAZP7L2', 'ES0146309002', 'LU3256039929']
NAV_CACHE: Dict[str, Dict[str, Any]] = {}

# --- FUNCIONES AUXILIARES ---
def parse_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace(' EUR', '').replace(' ', '')
    if not val_str:
        return 0.0
    if ',' in val_str and '.' in val_str:
        if val_str.find('.') < val_str.find(','):
            val_str = val_str.replace('.', '').replace(',', '.')
        else:
            val_str = val_str.replace(',', '')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def parse_date(date_str: str) -> datetime.date:
    formats = ['%d/%m/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M']
    clean_str = date_str.strip().strip('\ufeff')
    for fmt in formats:
        try:
            return datetime.datetime.strptime(clean_str, fmt).date()
        except (ValueError, AttributeError):
            pass
    return datetime.date(2000, 1, 1)

def fetch_market_nav(isin: str, force_refresh: bool = False) -> Dict[str, Any]:
    now = datetime.datetime.now()

    if not force_refresh and isin in NAV_CACHE:
        cache_item = NAV_CACHE[isin]
        if (now - cache_item['time']).total_seconds() < 900:
            return cache_item['data']

    try:
        # 1. Traer solo el último NAV de mercado para mantener la BBDD al día
        fund = mstarpy.Funds(term=isin, country='es')
        market_data = fund.historicalData(
            start_date=datetime.date.today() - datetime.timedelta(days=10), 
            end_date=datetime.date.today()
        )
        if market_data and 'nav' in market_data and len(market_data['nav']) > 0:
            last_entry = market_data['nav'][-1]
            save_nav_to_db(isin, last_entry['date'].split('T')[0], float(last_entry['nav']))
    except Exception as e:
        print(f"Aviso: No se pudo actualizar NAV de hoy para {isin}: {e}")

    # 2. Calcular todas las variaciones leyendo la BBDD local completa
    db_navs = get_stored_nav_map(isin)
    if not db_navs:
        return {'nav': 0.0, 'date': '-', 'd1': 0.0, 'w1': 0.0, 'm1': 0.0, 'y1': None}

    # Ordenar fechas para cálculos
    nav_by_date_obj = {datetime.datetime.strptime(d, '%Y-%m-%d').date(): v for d, v in db_navs.items()}
    sorted_dates = sorted(nav_by_date_obj.keys())
    
    latest_obj = sorted_dates[-1]
    live_nav = nav_by_date_obj[latest_obj]
    latest_date_str = latest_obj.strftime('%Y-%m-%d')

    # Función auxiliar para buscar el NAV más cercano a X días atrás
    def get_closest_nav(target_days_ago):
        target = latest_obj - datetime.timedelta(days=target_days_ago)
        for i in range(7): # Buscar hasta 7 días atrás (fines de semana/festivos)
            check_date = target - datetime.timedelta(days=i)
            if check_date in nav_by_date_obj:
                return nav_by_date_obj[check_date]
        return None

    # Variación 1 Día (el día inmediatamente anterior registrado)
    prev_nav = nav_by_date_obj[sorted_dates[-2]] if len(sorted_dates) >= 2 else live_nav
    d1 = round(((live_nav - prev_nav) / prev_nav) * 100, 2) if prev_nav else 0.0

    # Variación 1 Semana, 1 Mes, 1 Año
    week_nav = get_closest_nav(7)
    w1 = round(((live_nav - week_nav) / week_nav) * 100, 2) if week_nav else 0.0

    month_nav = get_closest_nav(30)
    m1 = round(((live_nav - month_nav) / month_nav) * 100, 2) if month_nav else 0.0

    year_nav = get_closest_nav(365)
    y1 = round(((live_nav - year_nav) / year_nav) * 100, 2) if year_nav else None

    result = {
        'nav': live_nav, 
        'date': latest_date_str, 
        'd1': d1, 'w1': w1, 'm1': m1, 'y1': y1
    }
    
    NAV_CACHE[isin] = {'time': now, 'data': result}
    return result

def get_row_value(row: Dict[str, Any], candidate_keys: List[str]) -> str:
    normalized_row = {k.strip().lower().replace('"', '').replace("'", ''): v for k, v in row.items()}
    for ck in candidate_keys:
        clean_ck = ck.strip().lower()
        if clean_ck in normalized_row and normalized_row[clean_ck] is not None:
            return str(normalized_row[clean_ck]).strip()
    return ''

def load_all_orders(in_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    csv_files = glob.glob(os.path.join(in_dir, '*.csv'))
    if not csv_files:
        parent = os.path.dirname(in_dir)
        csv_files = glob.glob(os.path.join(parent, '*.csv'))

    orders_by_isin: Dict[str, List[Dict[str, Any]]] = {}
    seen = set()

    for path in csv_files:
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(path, 'r', encoding='latin-1') as f:
                content = f.read()

        delimiter = ';' if ';' in content else ','
        reader = csv.DictReader(content.splitlines(), delimiter=delimiter)

        for row in reader:
            estado = get_row_value(row, ['estado', 'status'])
            if estado.lower() != 'finalizada':
                continue

            isin = get_row_value(row, ['isin', 'fondo'])
            if not isin:
                continue

            fecha = get_row_value(row, ['fecha de la orden', 'fecha de operación', 'fecha'])
            importe = parse_float(get_row_value(row, ['importe estimado', 'importe', 'monto']))
            participaciones = parse_float(get_row_value(row, ['nº de participaciones', 'participaciones']))
            precio_unit = parse_float(get_row_value(row, ['precio titulo', 'precio titulo compra', 'precio']))

            if participaciones <= 0 and importe <= 0:
                continue

            dedup_key = (fecha, isin, round(participaciones, 4), round(importe, 2))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            if isin not in orders_by_isin:
                orders_by_isin[isin] = []

            nav_op = precio_unit if precio_unit > 0 else ((importe / participaciones) if participaciones > 0 else 0.0)
            dt = parse_date(fecha)

            if isin and nav_op > 0 and dt.year >= 2020:
                save_nav_to_db(isin, dt.strftime('%Y-%m-%d'), nav_op)

            orders_by_isin[isin].append({
                'fecha': fecha,
                'date_obj': dt,
                'isin': isin,
                'importe': importe,
                'participaciones': participaciones,
                'nav_operacion': round(nav_op, 4),
                'tipo': get_row_value(row, ['tipo operación', 'tipo']) or 'Compra',
                'operador': get_row_value(row, ['operador']) or KNOWN_FUNDS.get(isin, {}).get('operador', 'myInvestor')
            })

    for isin in orders_by_isin:
        orders_by_isin[isin].sort(key=lambda x: x['date_obj'])

    return orders_by_isin

# --- GENERACIÓN DE SERIES TEMPORALES CON SQLITE ---
def generate_fund_timeseries(isin: str, orders: List[Dict[str, Any]], start_date: datetime.date, today: datetime.date) -> List[Dict[str, Any]]:
    if not orders:
        return []

    sorted_orders = sorted(orders, key=lambda x: x['date_obj'])
    fund_start = sorted_orders[0]['date_obj']

    # 1. Rellenar historial dinámico en SQLite si la tabla está vacía
    populate_missing_history(isin, fund_start)

    # 2. Cargar datos de SQLite
    db_navs = get_stored_nav_map(isin)

    events_by_date: Dict[datetime.date, List[Dict[str, Any]]] = {}
    for o in sorted_orders:
        d = o['date_obj']
        events_by_date.setdefault(d, []).append(o)

    cur_parts = 0.0
    cur_inv = 0.0
    series = []
    last_known_nav = sorted_orders[0]['nav_operacion'] if sorted_orders[0]['nav_operacion'] > 0 else 10.0

    cur = fund_start
    while cur <= today:
        d_str = cur.strftime('%Y-%m-%d')

        if cur in events_by_date:
            for ev in events_by_date[cur]:
                cur_parts += ev['participaciones']
                cur_inv += ev['importe']

        if d_str in db_navs and db_navs[d_str] > 0:
            last_known_nav = db_navs[d_str]
        elif cur == today:
            market = fetch_market_nav(isin)
            if market and market.get('nav'):
                last_known_nav = market['nav']

        val = cur_parts * last_known_nav
        gain_eur = val - cur_inv if cur_inv > 0 else 0.0
        gain_pct = (gain_eur / cur_inv * 100) if cur_inv > 0 else 0.0

        if cur_parts > 0:
            series.append({
                'date': d_str,
                'nav': round(last_known_nav, 4),
                'market_value': round(val, 2),
                'invested': round(cur_inv, 2),
                'gain_pct': round(gain_pct, 2)
            })

        cur += datetime.timedelta(days=1)

    return series

def generate_timeseries(orders: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    all_dates = [o['date_obj'] for isin in orders for o in orders[isin] if o.get('date_obj')]
    if not all_dates:
        return {'portfolio': [], 'funds': {}}

    start_date = min(all_dates)
    today = datetime.date.today()

    fund_series = {}
    for isin in ACTIVE_ISINS:
        fund_orders = orders.get(isin, [])
        fund_series[isin] = generate_fund_timeseries(isin, fund_orders, start_date, today)

    date_map: Dict[str, Dict[str, float]] = {}
    for isin, s_list in fund_series.items():
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

    return {
        'portfolio': portfolio_series,
        'funds': fund_series
    }

def get_portfolio_summary(in_dir: str, force_refresh: bool = False) -> Dict[str, Any]:
    orders = load_all_orders(in_dir)
    funds = []
    tot_invested = 0.0
    tot_value = 0.0
    today = datetime.date.today()

    all_isins = list(set(ACTIVE_ISINS + list(orders.keys())))
    all_flat_operations = []

    for isin, o_list in orders.items():
        meta = KNOWN_FUNDS.get(isin, {})
        for o in o_list:
            all_flat_operations.append({
                'fecha': o['fecha'],
                'date_obj': o['date_obj'],
                'isin': isin,
                'fondo_name': meta.get('short_name', isin),
                'tipo': o.get('tipo', 'Compra'),
                'operador': o.get('operador', meta.get('operador', 'N/D')),
                'importe': o['importe'],
                'participaciones': o['participaciones'],
                'precio_titulo': o['nav_operacion']
            })

    all_flat_operations.sort(key=lambda x: x['date_obj'], reverse=True)

    for isin in all_isins:
        fund_orders = orders.get(isin, [])
        
        # --- CÁLCULO EXACTO BASADO EN CADA ORDEN INDIVIDUAL ---
        total_parts = sum(o['participaciones'] for o in fund_orders)
        
        # Invertido real exacto sumando el importe monetario de cada orden de compra
        total_inv = sum(o['importe'] for o in fund_orders)
        
        is_active = isin in ACTIVE_ISINS
        first_date = fund_orders[0]['date_obj'] if fund_orders else today
        days_active = (today - first_date).days if first_date.year >= 2020 else 0

        market_info = fetch_market_nav(isin, force_refresh=force_refresh) if is_active else {'nav': 0.0, 'date': '-', 'd1': 0, 'w1': 0, 'm1': 0, 'y1': None}
        curr_nav = market_info['nav']
        
        # Valor de mercado actual estricto: Participaciones acumuladas × NAV actual de mercado
        curr_val = total_parts * curr_nav if is_active else 0.0
        
        # Beneficio neto real sumando todas las aportaciones históricas
        gain_eur = curr_val - total_inv if is_active else 0.0
        gain_pct = (gain_eur / total_inv * 100) if (total_inv > 0 and is_active) else 0.0

        meta = KNOWN_FUNDS.get(isin, {
            'name': isin,
            'short_name': isin,
            'category': 'Otros',
            'ter': 'N/D',
            'risk': 0,
            'operador': 'N/D'
        })

        fund_entry = {
            'isin': isin,
            'name': meta['name'],
            'short_name': meta['short_name'],
            'category': meta['category'],
            'ter': meta['ter'],
            'risk': meta['risk'],
            'operador': meta.get('operador', 'N/D'),
            'is_active': is_active,
            'first_purchase': first_date.strftime('%d/%m/%Y') if first_date.year >= 2020 else 'N/D',
            'days_active': days_active,
            'months_active': round(days_active / 30.4, 1),
            'participaciones': round(total_parts, 4),
            'invertido': round(total_inv, 2),
            'nav_actual': curr_nav,
            'fecha_nav': market_info.get('date', '-'),
            'valor_actual': round(curr_val, 2),
            'beneficio_eur': round(gain_eur, 2),
            'beneficio_pct': round(gain_pct, 2),
            'variacion_dia': market_info.get('d1', 0.0),
            'variacion_semana': market_info.get('w1', 0.0),
            'variacion_mes': market_info.get('m1', 0.0),
            'variacion_ano': market_info.get('y1', None),
            'ordenes_count': len(fund_orders)
        }

        if is_active:
            tot_invested += total_inv
            tot_value += curr_val

        funds.append(fund_entry)

    funds.sort(key=lambda x: (not x['is_active'], -x['valor_actual']))

    for f in funds:
        f['peso_pct'] = round((f['valor_actual'] / tot_value * 100), 2) if (tot_value > 0 and f['is_active']) else 0.0

    tot_gain_eur = tot_value - tot_invested
    tot_gain_pct = (tot_gain_eur / tot_invested * 100) if tot_invested > 0 else 0.0

    ts_data = generate_timeseries(orders)

    return {
        'totales': {
            'invertido': round(tot_invested, 2),
            'valor_mercado': round(tot_value, 2),
            'beneficio_eur': round(tot_gain_eur, 2),
            'beneficio_pct': round(tot_gain_pct, 2),
            'fondos_activos': sum(1 for f in funds if f['is_active']),
            'actualizado': datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        },
        'fondos': funds,
        'timeseries': ts_data['portfolio'],
        'fund_timeseries': ts_data['funds'],
        'all_operations': all_flat_operations
    }
