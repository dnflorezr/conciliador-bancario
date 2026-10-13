"""Genera los archivos de ejemplo.

Los datos están construidos a mano para que cada pasada del motor tenga al
menos un caso que la active, incluidos los que suelen romper una conciliación
real: desfases de fecha, comisiones bancarias, abonos agrupados y partidas sin
contraparte. Se ejecuta con:

    python datos_ejemplo/generar.py
"""

from __future__ import annotations

import csv
from pathlib import Path

AQUI = Path(__file__).parent

# (fecha, importe, descripcion, referencia)
BANCO = [
    ("2026-09-01", "4250000.00", "ABONO CLIENTE ANDINA SAS", "TRF-99120"),
    ("2026-09-02", "1180500.00", "ABONO CLIENTE MERIDIANO", ""),
    ("2026-09-03", "-2340000.00", "PAGO PROVEEDOR LOGITRANS", "PAG-4471"),
    ("2026-09-05", "7600000.00", "ABONO AGRUPADO CLIENTES", ""),
    ("2026-09-08", "-890000.00", "PAGO NOMINA PARCIAL", ""),
    ("2026-09-09", "2995500.00", "ABONO CLIENTE VERTICE", ""),
    ("2026-09-11", "-45000.00", "COMISION MANEJO", ""),
    ("2026-09-12", "3120000.00", "ABONO CLIENTE PALMAR", "TRF-99188"),
    ("2026-09-15", "-1750000.00", "PAGO ARRENDAMIENTO", ""),
    ("2026-09-18", "560000.00", "ABONO NO IDENTIFICADO", ""),
    ("2026-09-22", "-320000.00", "GMF CUATRO POR MIL", ""),
    ("2026-09-25", "5400000.00", "ABONO CLIENTE NORTE", "TRF-99215"),
]

LIBRO = [
    # Cruce por referencia: la fecha difiere pero la referencia coincide.
    ("2026-08-28", "4250000.00", "FV-10231 Andina SAS", "TRF-99120"),
    # Cruce exacto.
    ("2026-09-02", "1180500.00", "FV-10244 Meridiano", ""),
    # Cruce por referencia con egreso.
    ("2026-09-03", "-2340000.00", "CE-5512 Logitrans", "PAG-4471"),
    # Agrupación: estas tres suman 7.600.000 contra un solo abono del banco.
    ("2026-09-04", "3100000.00", "FV-10250 Cliente A", ""),
    ("2026-09-04", "2500000.00", "FV-10251 Cliente B", ""),
    ("2026-09-05", "2000000.00", "FV-10252 Cliente C", ""),
    # Cruce dentro de la ventana de fechas: el banco lo compensó dos días después.
    ("2026-09-06", "-890000.00", "CE-5520 Nomina quincena", ""),
    # Cruce por tolerancia: el banco descontó 500 de comisión.
    ("2026-09-09", "2996000.00", "FV-10260 Vertice", ""),
    # Cruce exacto.
    ("2026-09-12", "3120000.00", "FV-10265 Palmar", "TRF-99188"),
    # Cruce exacto.
    ("2026-09-15", "-1750000.00", "CE-5533 Arrendamiento", ""),
    # Sin contraparte en el banco: cheque girado y no cobrado.
    ("2026-09-19", "-1200000.00", "CE-5540 Cheque no cobrado", ""),
    # Fuera de ventana: el banco lo registró el 25, el libro el 30.
    ("2026-09-30", "5400000.00", "FV-10280 Cliente Norte", ""),
]

ENCABEZADO = ["fecha", "importe", "descripcion", "referencia"]


def escribir(nombre: str, filas: list[tuple[str, str, str, str]]) -> Path:
    ruta = AQUI / nombre
    with ruta.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(ENCABEZADO)
        w.writerows(filas)
    return ruta


if __name__ == "__main__":
    for nombre, filas in (("extracto_banco.csv", BANCO), ("auxiliar_contable.csv", LIBRO)):
        print(f"Escrito {escribir(nombre, filas)}")
