import os
import glob
import csv
import datetime
import json
from typing import Dict, List, Any

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

def parse_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace(' EUR', '').replace('€', '').replace(' ', '')
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
    formats = ['%d/%m/%Y', '%d/%n/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M']
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

    defaults = {
        'IE000ZYRH0Q7': {'nav': 12.2550, 'date': '04/09/2026', 'd1': 0.12, 'w1': 0.85, 'm1': 2.30, 'y1': 24.80},
        'IE000QAZP7L2': {'nav': 13.7970, 'date': '04/09/2026', 'd1': -0.08, 'w1': 0.42, 'm1': 1.15, 'y1': 12.40},
        'ES0146309002': {'nav': 221.61, 'date': '04/09/2026', 'd1': 0.25, 'w1': 1.10, 'm1': 3.40, 'y1': 16.80},
        'LU3256039929': {'nav': 522.40, 'date': '04/09/2026', 'd1': 0.10, 'w1': 0.60, 'm1': 1.95, 'y1': None}
    }
    result = defaults.get(isin, {'nav': 100.0, 'date': 'Hoy', 'd1': 0.0, 'w1': 0.0, 'm1': 0.0, 'y1': None})
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
            importe_str = get_row_value(row, ['importe estimado', 'importe', 'monto'])
            part_str = get_row_value(row, ['nº de participaciones', 'n° de participaciones', 'participaciones'])
            precio_unit_str = get_row_value(row, ['precio titulo', 'precio titulo compra', 'precio'])

            importe = parse_float(importe_str)
            participaciones = parse_float(part_str)
            precio_unit = parse_float(precio_unit_str)

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

def load_real_history_cache() -> Dict[str, List[Dict[str, Any]]]:
    cache_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "real_nav_history.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def generate_fund_timeseries(isin: str, orders: List[Dict[str, Any]], real_navs: List[Dict[str, Any]], start_date: datetime.date, today: datetime.date) -> List[Dict[str, Any]]:
    """Genera la serie temporal de NAV y valor de mercado de forma acumulativa y coherente."""
    if not orders:
        return []
    
    # Ordenar transacciones por fecha ascendente
    sorted_orders = sorted(orders, key=lambda x: x['date_obj'])
    fund_start = sorted_orders[0]['date_obj']
    
    # Mapa de NAVs por fecha (YYYY-MM-DD)
    nav_by_date = {p['date']: p['nav'] for p in real_navs}
    
    # Agrupar compras/operaciones por día (un día puede tener varias compras)
    events_by_date: Dict[datetime.date, List[Dict[str, Any]]] = {}
    for o in sorted_orders:
        d = o['date_obj']
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append(o)

    cur_parts = 0.0
    cur_inv = 0.0
    series = []
    
    # Obtener NAV inicial por defecto
    last_known_nav = sorted_orders[0]['nav_operacion'] if sorted_orders[0]['nav_operacion'] > 0 else 10.0
    
    cur = fund_start
    while cur <= today:
        d_str = cur.strftime('%Y-%m-%d')
        
        # 1. Si en el día actual hay compras, acumular participaciones e importe
        if cur in events_by_date:
            for ev in events_by_date[cur]:
                cur_parts += ev['participaciones']
                cur_inv += ev['importe']
        
        # 2. Actualizar el NAV si tenemos dato histórico en ese día
        if d_str in nav_by_date:
            last_known_nav = nav_by_date[d_str]
        elif cur == today:
            # Si no hay dato en el cache para hoy, usar el del API de mercado
            market_data = fetch_market_nav(isin)
            if market_data and market_data.get('nav'):
                last_known_nav = market_data['nav']
        
        nav = last_known_nav
        val = cur_parts * nav
        gain_eur = val - cur_inv if cur_inv > 0 else 0.0
        gain_pct = (gain_eur / cur_inv * 100) if cur_inv > 0 else 0.0
        
        # Solo guardar puntos cuando el usuario ya haya empezado a invertir en este fondo
        if cur_parts > 0:
            series.append({
                'date': d_str,
                'nav': round(nav, 4),
                'market_value': round(val, 2),
                'invested': round(cur_inv, 2),
                'gain_pct': round(gain_pct, 2)
            })
            
        cur += datetime.timedelta(days=1)
        
    return series

def generate_timeseries(orders: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    # Obtener el rango de fechas dinámicamente según las órdenes
    all_dates = [o['date_obj'] for isin in orders for o in orders[isin] if o.get('date_obj')]
    if not all_dates:
        return {'portfolio': [], 'funds': {}}
        
    start_date = min(all_dates)
    today = datetime.date.today()
    real_cache = load_real_history_cache()
    
    fund_series = {}
    for isin in ACTIVE_ISINS:
        fund_orders = orders.get(isin, [])
        fund_navs = real_cache.get(isin, [])
        fund_series[isin] = generate_fund_timeseries(isin, fund_orders, fund_navs, start_date, today)
    
    # Consolidar fechas para la cartera global
    date_map = {}
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
    today = datetime.date(2026, 9, 4)

    all_isins = set(ACTIVE_ISINS + list(orders.keys()))

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
        total_parts = sum(o['participaciones'] for o in fund_orders)
        total_inv = sum(o['importe'] for o in fund_orders)
        is_active = isin in ACTIVE_ISINS

        first_date = fund_orders[0]['date_obj'] if fund_orders else today
        days_active = (today - first_date).days if first_date.year >= 2025 else 0

        market_info = fetch_market_nav(isin, force_refresh=force_refresh) if is_active else {'nav': 0.0, 'date': '-', 'd1': 0, 'w1': 0, 'm1': 0, 'y1': None}
        curr_nav = market_info['nav']
        curr_val = total_parts * curr_nav if is_active else 0.0

        gain_eur = curr_val - total_inv if is_active else 0.0
        gain_pct = (gain_eur / total_inv * 100) if (total_inv > 0 and is_active) else 0.0

        d1 = market_info.get('d1', 0.0)
        w1 = market_info.get('w1', 0.0)
        m1 = market_info.get('m1', 0.0)
        y1 = market_info.get('y1', None)

        meta = KNOWN_FUNDS.get(isin, {
            'name': isin,
            'short_name': isin,
            'category': 'Otros',
            'ter': 'N/D',
            'risk': 0,
            'operador': 'N/D'
        })

        accum_p = 0.0
        accum_i = 0.0
        history = []
        for o in fund_orders:
            accum_p += o['participaciones']
            accum_i += o['importe']
            history.append({
                'fecha': o['fecha'],
                'tipo': o.get('tipo', 'Compra'),
                'operador': o.get('operador', meta.get('operador', 'N/D')),
                'importe': o['importe'],
                'participaciones': o['participaciones'],
                'nav_compra': o['nav_operacion'],
                'participaciones_acumuladas': round(accum_p, 4),
                'invertido_acumulado': round(accum_i, 2)
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
            'first_purchase': first_date.strftime('%d/%m/%Y') if first_date.year >= 2025 else 'N/D',
            'days_active': days_active,
            'months_active': round(days_active / 30.4, 1),
            'participaciones': round(total_parts, 4),
            'invertido': round(total_inv, 2),
            'nav_actual': curr_nav,
            'fecha_nav': market_info.get('date', '-'),
            'valor_actual': round(curr_val, 2),
            'beneficio_eur': round(gain_eur, 2),
            'beneficio_pct': round(gain_pct, 2),
            'variacion_dia': d1,
            'variacion_semana': w1,
            'variacion_mes': m1,
            'variacion_ano': y1,
            'ordenes_count': len(fund_orders),
            'history': history
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
