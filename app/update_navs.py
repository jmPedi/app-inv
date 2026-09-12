"""Flujo de ESCRITURA: actualiza la BBDD con las operaciones de los CSVs y los NAVs de Financial Times.

La web (app/portfolio.py) es de solo lectura; este módulo es quien consulta Financial Times
y escribe en SQLite. Se ejecuta al arrancar el contenedor y a las 18:00 (ver app/main.py),
o a mano con: python -m app.update_navs
"""
import os
import glob
import csv
import datetime
from typing import List, Dict, Any

from app.portfolio import (
    parse_float,
    parse_date,
    get_row_value,
    init_db,
    insert_operacion,
    get_all_operaciones,
    get_stored_nav_map,
    save_nav_to_db,
    fetch_nav_history_ft,
    FT_SYMBOLS,
    ACTIVE_ISINS,
    KNOWN_FUNDS,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN_DIR = os.path.join(BASE_DIR, 'IN')


def sync_csv_operaciones(in_dir: str) -> int:
    """Lee los CSVs de in_dir y sincroniza sus órdenes en la tabla `operaciones`.

    Idempotente: la clave UNIQUE(fecha, isin, participaciones, importe) evita duplicados
    en cada re-sincronización. Devuelve el número de operaciones insertadas (0 si todas ya existían).
    """
    csv_candidates = []
    # Buscar en in_dir (*.csv, *.CSV) y subcarpetas
    for ext in ('*.csv', '*.CSV', '*.tsv', '*.TSV'):
        csv_candidates.extend(glob.glob(os.path.join(in_dir, ext)))
        csv_candidates.extend(glob.glob(os.path.join(in_dir, '**', ext), recursive=True))

    if not csv_candidates:
        parent = os.path.dirname(in_dir)
        for ext in ('*.csv', '*.CSV'):
            csv_candidates.extend(glob.glob(os.path.join(parent, ext)))

    # Deduplicar rutas normalizadas
    csv_files = sorted(list(set(os.path.abspath(p) for p in csv_candidates)))

    if not csv_files:
        print(f"[CSV Sync] No se encontraron archivos CSV en '{in_dir}' ni en su carpeta padre.")
        return 0

    print(f"[CSV Sync] Encontrados {len(csv_files)} archivo(s) CSV para procesar: {[os.path.basename(f) for f in csv_files]}")

    inserted = 0
    for path in csv_files:
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(path, 'r', encoding='latin-1') as f:
                    content = f.read()
            except Exception as e:
                print(f"[CSV Sync] Error leyendo {path}: {e}")
                continue

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

            dt = parse_date(fecha)
            if dt.year < 2020:
                continue  # ignora órdenes de prueba/viejas

            operator = (get_row_value(row, ['operador'])
                        or KNOWN_FUNDS.get(isin, {}).get('operador', 'myInvestor'))
            tipo = get_row_value(row, ['tipo operación', 'tipo']) or 'Compra'

            new_id = insert_operacion(
                isin=isin,
                fecha=dt.strftime('%Y-%m-%d'),
                importe=importe,
                participaciones=participaciones,
                precio_titulo=precio_unit,
                operador=operator,
                fuente='csv',
                tipo=tipo,
            )
            if new_id:
                inserted += 1

    return inserted


def _guarda_navs_de_operaciones(isin: str, ops: List[Dict[str, Any]]) -> int:
    """Guarda el precio de cada operación como NAV histórico (fuente para fondos sin mercado público)."""
    n = 0
    for o in ops:
        if o['isin'] != isin:
            continue
        if o['precio_titulo'] > 0:
            save_nav_to_db(isin, o['fecha'], o['precio_titulo'])
            n += 1
    return n


def _actualiza_navs_ft(isin: str, ops: List[Dict[str, Any]]) -> int:
    """Descarga de Financial Times el histórico de NAVs del ISIN y lo guarda en SQLite."""
    existing = get_stored_nav_map(isin)
    today = datetime.date.today()

    if existing:
        last_date = max(datetime.datetime.strptime(d, '%Y-%m-%d').date() for d in existing)
        days = max(30, (today - last_date).days + 10)
    else:
        fechas_ops = [datetime.datetime.strptime(o['fecha'], '%Y-%m-%d').date() for o in ops if o['isin'] == isin]
        first_date = min(fechas_ops) if fechas_ops else today - datetime.timedelta(days=400)
        days = max(60, (today - first_date).days + 30)

    navs = fetch_nav_history_ft(isin, days=days)
    saved = 0
    for item in navs:
        save_nav_to_db(isin, item['date'], item['nav'])
        saved += 1
    return saved


def update_all_navs(in_dir: str = DEFAULT_IN_DIR) -> Dict[str, Any]:
    """Sincroniza los CSVs y actualiza los NAVs de todos los fondos de la cartera."""
    init_db()
    resumen: Dict[str, Any] = {'operaciones_csv': 0, 'fondos': {}, 'errores': []}

    # 1. Sincronizar CSVs -> tabla operaciones
    resumen['operaciones_csv'] = sync_csv_operaciones(in_dir)

    # 2. ISINs a procesar: los activos + los que ya tienen operaciones (CSV o manuales)
    ops = get_all_operaciones()
    isins = set(ACTIVE_ISINS) | {o['isin'] for o in ops}

    for isin in sorted(isins):
        resumen['fondos'][isin] = {'nombre': KNOWN_FUNDS.get(isin, {}).get('short_name', isin), 'n_ops': 0, 'n_navs': 0}

        # 2a. NAVs históricos de las operaciones de este fondo (fallback base)
        resumen['fondos'][isin]['n_ops'] = _guarda_navs_de_operaciones(isin, ops)

        # 2b. NAVs diarios desde Financial Times
        try:
            n = _actualiza_navs_ft(isin, ops)
            resumen['fondos'][isin]['n_navs'] = n
            print(f"[{isin}] Financial Times: +{n} NAVs guardados en BBDD")
        except Exception as e:
            resumen['errores'].append(str(e))
            print(f"[{isin}] Aviso (se mantiene el histórico en BBDD): {e}")

    total_navs = sum(r['n_navs'] for r in resumen['fondos'].values())
    print(f"Actualización completada: {resumen['operaciones_csv']} operaciones de CSV, {total_navs} NAVs descargados.")
    return resumen


if __name__ == '__main__':
    update_all_navs()
