"""Interfaz de línea de comandos.

    python -m conciliador extracto.csv auxiliar.csv -o conciliacion.xlsx
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from .cargador import ErrorDeCarga, MapeoColumnas, cargar
from .modelos import Origen
from .motor import Conciliador, ConfigConciliacion
from .reporte import escribir_csv, escribir_excel, imprimir_resumen


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="conciliador",
        description="Concilia un extracto bancario contra un auxiliar contable.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python -m conciliador banco.csv libro.csv\n"
            "  python -m conciliador banco.xlsx libro.xlsx -o salida.xlsx --ventana 5 --tolerancia 100\n"
            "  python -m conciliador banco.csv libro.csv --col-fecha Fecha --col-importe Valor\n"
        ),
    )
    p.add_argument("banco", help="Extracto bancario (.csv o .xlsx)")
    p.add_argument("libro", help="Auxiliar contable (.csv o .xlsx)")
    p.add_argument("-o", "--salida", default="conciliacion.xlsx", help="Archivo de reporte")
    p.add_argument("--csv", action="store_true", help="Escribe CSV en vez de Excel")

    g = p.add_argument_group("criterios de cruce")
    g.add_argument("--ventana", type=int, default=3, metavar="N", help="Días de desfase admitidos (3)")
    g.add_argument("--tolerancia", type=str, default="0", metavar="X", help="Diferencia de importe admitida (0)")
    g.add_argument("--max-grupo", type=int, default=4, metavar="N", help="Máximo de partidas a agrupar (4)")
    g.add_argument("--sin-referencia", action="store_true", help="Omite la pasada por referencia")
    g.add_argument("--invertir-libro", action="store_true", help="Invierte el signo de los importes del libro")

    c = p.add_argument_group("nombres de columna")
    c.add_argument("--col-fecha", default="fecha")
    c.add_argument("--col-importe", default="importe")
    c.add_argument("--col-descripcion", default="descripcion")
    c.add_argument("--col-referencia", default="referencia")
    c.add_argument("--col-id", default=None)

    p.add_argument("-q", "--silencioso", action="store_true", help="No imprime el resumen")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)

    mapeo = MapeoColumnas(
        fecha=args.col_fecha,
        importe=args.col_importe,
        descripcion=args.col_descripcion,
        referencia=args.col_referencia,
        id=args.col_id,
    )

    try:
        banco = cargar(args.banco, Origen.BANCO, mapeo)
        libro = cargar(args.libro, Origen.LIBRO, mapeo)
    except ErrorDeCarga as exc:
        print(f"Error al leer los archivos: {exc}", file=sys.stderr)
        return 2

    try:
        config = ConfigConciliacion(
            ventana_dias=args.ventana,
            tolerancia=Decimal(args.tolerancia),
            max_grupo=args.max_grupo,
            usar_referencia=not args.sin_referencia,
            invertir_signo_libro=args.invertir_libro,
        )
    except (ValueError, ArithmeticError) as exc:
        print(f"Parámetros inválidos: {exc}", file=sys.stderr)
        return 2

    resultado = Conciliador(config).conciliar(banco, libro)

    if args.csv:
        salidas = escribir_csv(resultado, Path(args.salida).with_suffix(""))
        destino = ", ".join(str(s) for s in salidas)
    else:
        destino = str(escribir_excel(resultado, args.salida))

    if not args.silencioso:
        print(imprimir_resumen(resultado))
        print(f"  Reporte: {destino}\n")

    # Código 1 si quedaron partidas abiertas: sirve para encadenar en un flujo
    # automatizado que deba avisar cuando la conciliación no cuadra.
    return 1 if resultado.pendientes else 0


if __name__ == "__main__":
    raise SystemExit(main())
