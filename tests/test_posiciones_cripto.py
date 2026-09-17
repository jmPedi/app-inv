"""Pruebas aisladas: datos sintéticos, sin red ni BBDD de la cartera."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import cripto, update_cripto


CABECERA = 'moneda;exchange;cantidad;capital_referencia_eur;valor_manual_eur\n'
FILAS = 'XRP;Bit2Me;10,5;20;\nXRP;Bitvavo;2;5;\nB2M;Bit2Me;100;3;1,50\n'


class PosicionesCriptoTest(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.bd = self.raiz / 'prueba.db'
        self.parches = patch.multiple(cripto, DB_PATH=str(self.bd), DATA_DIR=str(self.raiz))
        self.parches.start()
        self.addCleanup(self.parches.stop)
        self.csv = self.raiz / 'posiciones_cripto' / 'posiciones_actuales.csv'
        self.csv.parent.mkdir()
        cripto.init_cripto_db()

    def importar(self, filas=FILAS):
        self.csv.write_text(CABECERA + filas, encoding='utf-8-sig')
        return update_cripto.sync_csv_cripto_posiciones(str(self.raiz))

    def filas_bd(self):
        with cripto.closing(sqlite3.connect(str(self.bd))) as conn:
            return conn.execute(
                'SELECT symbol, operador, cantidad, capital_referencia_eur, valor_manual_eur '
                'FROM cripto_posiciones ORDER BY symbol, operador').fetchall()

    def test_contrato_csv_y_resumen(self):
        self.importar()
        cripto.save_cripto_precio('xrp', '2026-09-01', 2)
        resumen = cripto.get_cripto_portfolio_summary()
        self.assertEqual(resumen['modo_posiciones'], 'csv')
        self.assertEqual(len(resumen['activos']), 3)
        self.assertEqual(resumen['totales']['invertido'], 28)
        self.assertEqual(resumen['totales']['valor_mercado'], 26.5)
        xrp = [a for a in resumen['activos'] if a['symbol'] == 'xrp']
        self.assertEqual({a['operador'] for a in xrp}, {'Bit2Me', 'Bitvavo'})
        self.assertEqual(sum(a['cantidad'] for a in xrp), 12.5)
        b2m = next(a for a in resumen['activos'] if a['symbol'] == 'bit2me-coin')
        self.assertEqual(b2m['valor_actual'], 1.5)
        self.assertIsNone(b2m['precio_actual'])
        self.assertEqual(resumen['operaciones'], [])
        self.assertEqual(resumen['timeseries'], [])

    def test_idempotencia_y_sustitucion(self):
        self.assertEqual(self.importar(), 3)
        primera = self.filas_bd()
        self.assertEqual(self.importar(), 0)  # reimportar no duplica ni toca
        self.assertEqual(self.filas_bd(), primera)
        self.assertEqual(self.importar('ETH;Bit2me;1;10;\n'), 1)  # sustituye el conjunto
        self.assertEqual(self.filas_bd(), [('ethereum', 'Bit2Me', 1.0, 10.0, None)])

    def test_archivo_ausente_conserva_fotografia(self):
        self.importar()
        self.csv.unlink()
        self.assertEqual(update_cripto.sync_csv_cripto_posiciones(str(self.raiz)), 0)
        self.assertEqual(len(self.filas_bd()), 3)

    def test_errores_validacion(self):
        casos = {
            'duplicado': 'XRP;Bit2Me;1;5;\nXRP;bit2me;2;6;\n',
            'moneda desconocida': 'ABC;Bit2Me;1;5;\n',
            'manual en moneda cotizada': 'XRP;Bit2Me;1;5;9\n',
            'B2M sin manual': 'B2M;Bit2Me;1;5;\n',
            'no numerico': 'XRP;Bit2Me;abc;5;\n',
            'negativo': 'XRP;Bit2Me;-1;5;\n',
        }
        self.importar()
        for motivo, filas in casos.items():
            with self.subTest(motivo=motivo):
                self.csv.write_text(CABECERA + filas, encoding='utf-8-sig')
                with self.assertRaises(ValueError):
                    update_cripto.sync_csv_cripto_posiciones(str(self.raiz))
        # La fotografía previa sigue intacta tras todos los rechazos.
        self.assertEqual(len(self.filas_bd()), 3)

    def test_archivo_vacio_y_cabecera_invalida(self):
        self.importar()
        for contenido in ('', CABECERA, 'moneda;exchange;cantidad\nXRP;Bit2Me;1\n'):
            with self.subTest(contenido=contenido[:20]):
                self.csv.write_text(contenido, encoding='utf-8-sig')
                with self.assertRaises(ValueError):
                    update_cripto.sync_csv_cripto_posiciones(str(self.raiz))
        self.assertEqual(len(self.filas_bd()), 3)

    def test_get_no_escribe_y_fallback_historico(self):
        self.bd.unlink()  # sin BBDD: la lectura no debe crearla
        resumen = cripto.get_cripto_portfolio_summary()
        self.assertEqual(resumen['modo_posiciones'], 'compras')
        self.assertEqual(resumen['activos'], [])
        self.assertEqual(resumen['totales']['invertido'], 0.0)
        self.assertFalse(self.bd.exists())

    def test_update_all_integra_posiciones_sin_red(self):
        self.importar()
        with patch.object(update_cripto, '_actualiza_precios_cripto',
                          lambda n_dias=400: 0):
            resumen = update_cripto.update_all_cripto(str(self.raiz))
        self.assertEqual(resumen['posiciones_csv'], 0)  # idempotente: ya estaba importado
        self.assertEqual(resumen['operaciones_csv'], 0)
        self.assertEqual(resumen['errores'], [])


if __name__ == '__main__':
    unittest.main()
