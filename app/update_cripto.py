"""Flujo de ESCRITURA de criptoactivos: sincroniza CSVs de exchange y descarga precios de Binance (público, sin API key).

Espejo de app/update_navs.py para el dominio cripto.
Se ejecuta al arrancar y a las 18:00 (ver app/main.py), o a mano con:
python -m app.update_cripto
"""
import os
import glob
import csv
import datetime
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


def sync_csv_cripto_operaciones(in_dir: str) -> int:
    """Lee los CSVs de 'IN/crypto/' y sincroniza sus órdenes en cripto_operaciones.

    Solo procesa la subcarpeta 'crypto' para no mezclar con los CSVs de fondos.
    Idempotente: la clave UNIQUE(fecha, symbol, cantidad, importe) evita duplicados.
    Devuelve el número de operaciones insertadas.
    """
    crypto_dir = os.path.join(in_dir, 'crypto')
    csv_candidates = []
    for ext in ('*.csv', '*.CSV', '*.tsv', '*.TSV'):
        csv_candidates.extend(glob.glob(os.path.join(crypto_dir, ext)))
        csv_candidates.extend(glob.glob(os.path.join(crypto_dir, '**', ext), recursive=True))

    csv_files = sorted(list(set(os.path.abspath(p) for p in csv_candidates)))

    if not csv_files:
        print(f"[CSV Crypto] No se encontraron CSVs en '{crypto_dir}'. Crea la carpeta IN/crypto y añade tus exportaciones.")
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

        delimiter = ';' if ';' in content else ','
        reader = csv.DictReader(content.splitlines(), delimiter=delimiter)

        for row in reader:
            # Detectar symbol: puede venir como 'symbol', 'divisa', 'moneda', 'activo' o 'BTC'/'ETH'
            symbol = get_row_value(row, ['symbol', 'divisa', 'moneda', 'activo', 'asset', 'crypto', 'coin'])
            if not symbol:
                continue
            symbol = symbol.strip().lower()
            # Acepta 'BTC'/'ETH' o 'bitcoin'/'ethereum'
            if symbol in ('btc', 'bitcoin'):
                symbol = 'bitcoin'
            elif symbol in ('eth', 'ethereum'):
                symbol = 'ethereum'
            elif symbol not in CRYPTO_COINS:
                print(f"[CSV Crypto] Símbolo no configurado, se ignora: {symbol}")
                continue

            fecha = get_row_value(row, ['fecha de la orden', 'fecha de operación', 'fecha', 'date'])
            cantidad = parse_float(get_row_value(row, ['cantidad', 'qty', 'quantity', 'amount', 'aantal', 'cantidad de la moneda']))
            importe = parse_float(get_row_value(row, ['importe', 'cost', 'coste', 'monto', 'monto total', 'total']))
            precio = parse_float(get_row_value(row, ['precio', 'price', 'precio unitario', 'prijs']))

            if cantidad <= 0 and importe <= 0:
                continue

            dt = parse_date(fecha)
            if dt.year < 2020:
                continue

            # Si solo viene cantidad+precio, derivar importe; si solo cantidad+importe, derivar precio
            if importe <= 0 and precio > 0 and cantidad > 0:
                importe = cantidad * precio
            if precio <= 0 and importe > 0 and cantidad > 0:
                precio = importe / cantidad

            operador = (get_row_value(row, ['exchange', 'plataforma', 'operador', 'broker'])
                        or CRYPTO_COINS.get(symbol, {}).get('operador_default', ''))
            tipo = get_row_value(row, ['tipo operación', 'tipo']) or 'Compra'

            new_id = insert_cripto_operacion(
                symbol=symbol,
                fecha=dt.strftime('%Y-%m-%d'),
                importe=importe,
                cantidad=cantidad,
                precio_unitario=precio,
                operador=operador,
                fuente='csv',
                tipo=tipo,
            )
            if new_id:
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
    """Sincroniza CSVs de cripto y actualiza los precios desde CoinGecko."""
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