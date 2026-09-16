"""Flujo de ESCRITURA de criptoactivos: sincroniza CSVs de exchange y descarga precios de Binance (público, sin API key).

Espejo de app/update_navs.py para el dominio cripto.
Se ejecuta al arrancar y a las 18:00 (ver app/main.py), o a mano con:
python -m app.update_cripto
"""
import os
import glob
import csv
import datetime
import re
import requests
from typing import Dict, Any

from app.portfolio import (
    parse_float,
    parse_date,
    get_row_value,
)
from app.cripto import (
    init_cripto_db,
    insert_cripto_operacion,
    get_all_cripto_operaciones,
    save_cripto_precio,
    CRYPTO_COINS,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN_DIR = os.path.join(BASE_DIR, 'IN')

# Binance: velas diarias en EUR (público, sin API key).
BINANCE_KLINES_URL = (
    'https://api.binance.com/api/v3/klines'
    '?symbol={pair}&interval=1d&limit={limit}'
)


# Símbolos cripto soportados: 'BTC' -> 'bitcoin', 'ETH' -> 'ethereum'.
_CRIPTO_SOPORTADA = {cfg['symbol'].upper(): coin_id for coin_id, cfg in CRYPTO_COINS.items()}


def _indice_cabecera(lineas: list, delimiter: str) -> int:
    """Índice de la primera línea que parece una cabecera real.

    Salta las líneas en blanco y las filas 'Unnamed: N' que crea pandas al exportar
    desde Excel (los summary de Bit2Me traen la cabecera real en la fila 2).
    """
    for i, linea in enumerate(lineas):
        if not linea.strip():
            continue
        celdas = [c.strip() for c in linea.split(delimiter)]
        if celdas and all(c == '' or c.startswith('Unnamed:') for c in celdas):
            continue
        return i
    return 0


def _formato_archivo(cabecera: str) -> str:
    """Detecta el formato del CSV por las palabras clave de la cabecera real:
    'bit2me' (summary con 'Tipo de operación'), 'bitvavo' (historial completo) o
    'generico' (CSV propio con columnas symbol, fecha, cantidad...)."""
    cab = cabecera.lower()
    if 'tipo de operación' in cab or 'tipo de operacion' in cab:
        return 'bit2me'
    if 'received / paid amount' in cab or ('timezone' in cab and 'currency' in cab):
        return 'bitvavo'
    return 'generico'


def _busca_fecha(fila: list):
    """Devuelve la primera celda con aspecto de fecha (YYYY-MM-DD[ HH:MM[:SS]])."""
    for celda in fila:
        if celda and re.search(r'\d{4}-\d{2}-\d{2}', celda):
            return celda
    return None


def _fila_compra_bit2me(fila: list):
    """Lee una fila del summary de Bit2Me y devuelve la compra si la hay (o None).

    Solo interesan los trades en que se adquiere cripto soportada (BTC/ETH) pagando
    en EUR. Columnas del summary: 0 Tipo de operación, 1 Cantidad de destino,
    2 Moneda de destino, 3 Cantidad de origen, 4 Moneda de origen, 7 Exchange y una
    columna final con la fecha. Los depósitos, staking y retiradas se ignoran.
    """
    if len(fila) < 5:
        return None
    tipo = fila[0].lower()
    if tipo not in ('trade', 'compra', 'buy'):
        return None
    mon_dest = fila[2].upper()
    mon_origen = fila[4].upper()
    if mon_origen != 'EUR' or mon_dest not in _CRIPTO_SOPORTADA:
        return None
    cantidad = parse_float(fila[1])
    importe = parse_float(fila[3])
    if cantidad <= 0 or importe <= 0:
        return None
    operador = 'bit2me'
    if len(fila) > 7 and fila[7]:
        operador = fila[7]  # p. ej. 'Bit2Me'
    return {
        'symbol': _CRIPTO_SOPORTADA[mon_dest],
        'cantidad': cantidad,
        'importe': importe,
        'precio': importe / cantidad,
        'fecha': _busca_fecha(fila),
        'operador': operador,
        'tipo': 'Compra',
    }


def _fila_compra_bitvavo(fila: list):
    """Lee una fila del historial completo de Bitvavo y devuelve la compra si la hay (o None).

    Solo se importan las filas Type='buy' de cripto soportada. Columnas:
    1 Fecha, 2 Hora, 3 Type, 4 Currency, 5 Amount, 7 Quote Price y 9 Received / Paid
    Amount (EUR desembolsados, negativo). El resto de tipos (withdrawal, staking,
    deposit, sell...) no son compras y se ignoran.
    """
    if len(fila) < 10:
        return None
    if fila[3].strip().lower() != 'buy':
        return None
    moneda = fila[4].strip().upper()
    if moneda not in _CRIPTO_SOPORTADA:
        return None
    cantidad = abs(parse_float(fila[5]))
    precio = parse_float(fila[7])
    importe = abs(parse_float(fila[9]))
    if cantidad <= 0:
        return None
    if precio <= 0 and importe > 0:
        precio = importe / cantidad
    return {
        'symbol': _CRIPTO_SOPORTADA[moneda],
        'cantidad': cantidad,
        'importe': importe if importe > 0 else cantidad * precio,
        'precio': precio,
        'fecha': _busca_fecha(fila),
        'operador': 'Bitvavo',
        'tipo': 'Compra',
    }


def _guarda_compra(op: dict) -> int:
    """Valida y registra una compra en cripto_operaciones. Devuelve 1 si inserta."""
    if op.get('symbol') not in CRYPTO_COINS or op.get('cantidad') is None:
        return 0
    dt = parse_date(op.get('fecha')) if op.get('fecha') else None
    if dt is None or dt.year < 2020:
        return 0
    cantidad = op['cantidad']
    importe = op.get('importe', 0) or 0
    precio = op.get('precio', 0) or 0
    # Si solo viene cantidad+precio, derivar importe; si solo cantidad+importe, derivar precio
    if importe <= 0 and precio > 0:
        importe = cantidad * precio
    if precio <= 0 and importe > 0:
        precio = importe / cantidad
    if importe <= 0 or precio <= 0 or cantidad <= 0:
        return 0
    new_id = insert_cripto_operacion(
        symbol=op['symbol'],
        fecha=dt.strftime('%Y-%m-%d'),
        importe=importe,
        cantidad=cantidad,
        precio_unitario=precio,
        operador=op.get('operador') or CRYPTO_COINS.get(op['symbol'], {}).get('operador_default', ''),
        fuente='csv',
        tipo=op.get('tipo') or 'Compra',
    )
    return 1 if new_id else 0


def sync_csv_cripto_operaciones(in_dir: str) -> int:
    """Lee los CSVs de 'IN/cripto/' y sincroniza sus compras en cripto_operaciones.

    Solo procesa la subcarpeta 'cripto' para no mezclar con los CSVs de fondos.
    Reconocidos los formatos Bit2Me (summary con 'Tipo de operación') y Bitvavo
    (historial completo) y uno genérico por encabezados. Se ignoran los movimientos
    que no son compras de cripto soportada pagadas en EUR (depósitos, staking,
    retiradas...). Idempotente: la clave UNIQUE(fecha, symbol, cantidad, importe)
    evita duplicados. Devuelve el número de operaciones insertadas.
    """
    crypto_dir = os.path.join(in_dir, 'cripto')
    csv_candidates = []
    for ext in ('*.csv', '*.CSV', '*.tsv', '*.TSV'):
        csv_candidates.extend(glob.glob(os.path.join(crypto_dir, ext)))
        csv_candidates.extend(glob.glob(os.path.join(crypto_dir, '**', ext), recursive=True))

    csv_files = sorted(list(set(os.path.abspath(p) for p in csv_candidates)))

    if not csv_files:
        print(f"[CSV Crypto] No se encontraron CSVs en '{crypto_dir}'. Crea la carpeta IN/cripto y añade tus exportaciones.")
        return 0

    print(f"[CSV Crypto] Encontrados {len(csv_files)} archivo(s): {[os.path.basename(f) for f in csv_files]}")

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
                print(f"[CSV Crypto] Error leyendo {path}: {e}")
                continue

        lineas = content.splitlines()
        if not lineas:
            continue
        delimiter = ';' if ';' in content else ','
        # Cabecera real (saltando las filas 'Unnamed' de pandas) y formato del fichero
        idx_cab = _indice_cabecera(lineas, delimiter)
        formato = _formato_archivo(lineas[idx_cab])
        if formato == 'generico':
            filas = csv.DictReader(lineas[idx_cab:], delimiter=delimiter)
        else:
            filas = csv.reader(lineas[idx_cab + 1:], delimiter=delimiter)

        for fila in filas:
            op = None
            if formato == 'generico':
                # Detectar symbol: puede venir como 'symbol', 'divisa', 'moneda', 'activo' o 'BTC'/'ETH'
                symbol = get_row_value(fila, ['symbol', 'divisa', 'moneda', 'activo', 'asset', 'crypto', 'coin'])
                if not symbol:
                    continue
                symbol = symbol.strip().lower()
                if symbol in ('btc', 'bitcoin'):
                    symbol = 'bitcoin'
                elif symbol in ('eth', 'ethereum'):
                    symbol = 'ethereum'
                elif symbol not in CRYPTO_COINS:
                    print(f"[CSV Crypto] Símbolo no configurado, se ignora: {symbol}")
                    continue
                op = {
                    'symbol': symbol,
                    'cantidad': parse_float(get_row_value(fila, ['cantidad', 'qty', 'quantity', 'amount', 'aantal', 'cantidad de la moneda'])),
                    'importe': parse_float(get_row_value(fila, ['importe', 'cost', 'coste', 'monto', 'monto total', 'total'])),
                    'precio': parse_float(get_row_value(fila, ['precio', 'price', 'precio unitario', 'prijs'])),
                    'fecha': get_row_value(fila, ['fecha de la orden', 'fecha de operación', 'fecha', 'date']),
                    'operador': get_row_value(fila, ['exchange', 'plataforma', 'operador', 'broker']),
                    'tipo': get_row_value(fila, ['tipo operación', 'tipo']) or 'Compra',
                }
            elif formato == 'bit2me':
                op = _fila_compra_bit2me(fila)
            else:
                op = _fila_compra_bitvavo(fila)

            if op and _guarda_compra(op):
                inserted += 1

    return inserted


def _actualiza_precios_cripto(n_dias: int = 400) -> int:
    """Descarga de Binance las velas diarias en EUR (p. ej. BTCEUR/ETHEUR) y guarda el histórico en cripto_precios."""
    saved = 0
    for coin_id, coin_cfg in CRYPTO_COINS.items():
        pair = coin_cfg.get('par_binance') or f"{coin_cfg['symbol']}EUR"
        try:
            url = BINANCE_KLINES_URL.format(pair=pair, limit=n_dias)
            resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
            resp.raise_for_status()
            klines = resp.json()

            n = 0
            for candle in klines:
                # candle: [openTime, open, high, low, close, volume, ...]
                ts_ms = candle[0]
                precio_eur = float(candle[4])  # precio de cierre
                fecha = datetime.datetime.utcfromtimestamp(ts_ms / 1000).strftime('%Y-%m-%d')
                save_cripto_precio(coin_id, fecha, round(precio_eur, 4))
                n += 1
            saved += n
            print(f"[{coin_id}] Binance {pair}: +{n} precios guardados en BBDD")
        except Exception as e:
            print(f"[{coin_id}] Aviso (se mantiene el histórico en BBDD): {e}")

    return saved


def update_all_cripto(in_dir: str = DEFAULT_IN_DIR) -> Dict[str, Any]:
    """Sincroniza CSVs de cripto y actualiza los precios desde Binance."""
    init_cripto_db()
    resumen: Dict[str, Any] = {'operaciones_csv': 0, 'precios': 0, 'errores': []}

    try:
        resumen['operaciones_csv'] = sync_csv_cripto_operaciones(in_dir)
    except Exception as e:
        resumen['errores'].append(f'CSV: {e}')
        print(f"[CSV Crypto] Error: {e}")

    try:
        resumen['precios'] = _actualiza_precios_cripto()
    except Exception as e:
        resumen['errores'].append(f'Precios: {e}')
        print(f"[Crypto] Error actualizando precios: {e}")

    print(f"Actualización cripto completada: {resumen['operaciones_csv']} operaciones de CSV, {resumen['precios']} precios.")
    return resumen


if __name__ == '__main__':
    update_all_cripto()