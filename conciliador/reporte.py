"""Generación del reporte de conciliación.

El archivo de salida tiene tres hojas, pensadas para que quien revisa la
conciliación encuentre primero lo que le importa: el resumen para saber si
cuadra, las partidas abiertas para trabajar, y los cruces para auditar el
resultado si algo se ve raro.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .modelos import Resultado

ENCABEZADO_PENDIENTES = [
    "Origen",
    "ID",
    "Fecha",
    "Importe",
    "Descripción",
    "Referencia",
    "Motivo",
    "Nota",
]

ENCABEZADO_CRUCES = [
    "Tipo",
    "IDs banco",
    "IDs libro",
    "Importe banco",
    "Importe libro",
    "Diferencia",
    "Días desfase",
]


def _fila_pendiente(p) -> list[object]:
    m = p.movimiento
    return [
        m.origen.value,
        m.id,
        m.fecha,
        m.importe,
        m.descripcion,
        m.referencia or "",
        p.motivo.value,
        p.nota,
    ]


def _fila_cruce(c) -> list[object]:
    return [
        c.tipo.value,
        ", ".join(m.id for m in c.banco),
        ", ".join(m.id for m in c.libro),
        c.importe_banco,
        c.importe_libro,
        c.diferencia,
        c.dias_diferencia,
    ]


def escribir_excel(resultado: Resultado, ruta: str | Path) -> Path:
    """Escribe el reporte en un .xlsx con tres hojas."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    ruta = Path(ruta)
    libro = Workbook()

    azul = PatternFill("solid", fgColor="1F3864")
    blanco_negrita = Font(bold=True, color="FFFFFF")

    def encabezar(hoja, columnas: list[str]) -> None:
        hoja.append(columnas)
        for celda in hoja[1]:
            celda.fill = azul
            celda.font = blanco_negrita
            celda.alignment = Alignment(horizontal="center")
        hoja.freeze_panes = "A2"

    def ajustar(hoja) -> None:
        for i, col in enumerate(hoja.columns, start=1):
            largo = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            hoja.column_dimensions[get_column_letter(i)].width = min(max(largo + 2, 10), 48)

    resumen = resultado.resumen()
    hoja = libro.active
    hoja.title = "Resumen"
    encabezar(hoja, ["Concepto", "Valor"])
    etiquetas = {
        "movimientos_banco": "Movimientos del banco",
        "movimientos_libro": "Movimientos del libro",
        "conciliados_banco": "Conciliados del banco",
        "conciliados_libro": "Conciliados del libro",
        "pendientes_banco": "Partidas abiertas del banco",
        "pendientes_libro": "Partidas abiertas del libro",
        "cruces": "Cruces encontrados",
        "porcentaje_conciliado": "% conciliado",
        "diferencia_total": "Diferencia por explicar",
    }
    for clave, etiqueta in etiquetas.items():
        hoja.append([etiqueta, resumen[clave]])
    hoja.append([])
    hoja.append(["Cruces por tipo", ""])
    for tipo, n in sorted(resumen["cruces_por_tipo"].items()):
        hoja.append([f"  {tipo}", n])
    ajustar(hoja)

    hoja_p = libro.create_sheet("Partidas abiertas")
    encabezar(hoja_p, ENCABEZADO_PENDIENTES)
    for p in sorted(resultado.pendientes, key=lambda x: (x.movimiento.fecha, x.movimiento.id)):
        hoja_p.append(_fila_pendiente(p))
    ajustar(hoja_p)

    hoja_c = libro.create_sheet("Cruces")
    encabezar(hoja_c, ENCABEZADO_CRUCES)
    for c in resultado.cruces:
        hoja_c.append(_fila_cruce(c))
    ajustar(hoja_c)

    for h in (hoja_p, hoja_c):
        for fila in h.iter_rows(min_row=2):
            for celda in fila:
                if isinstance(celda.value, Decimal):
                    celda.value = float(celda.value)
                    celda.number_format = "#,##0.00"
                elif hasattr(celda.value, "isoformat"):
                    celda.number_format = "yyyy-mm-dd"

    libro.save(ruta)
    return ruta


def escribir_csv(resultado: Resultado, carpeta: str | Path) -> list[Path]:
    """Alternativa sin Excel: un CSV por hoja."""
    import csv

    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    salidas: list[Path] = []

    ruta_p = carpeta / "partidas_abiertas.csv"
    with ruta_p.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(ENCABEZADO_PENDIENTES)
        for p in sorted(resultado.pendientes, key=lambda x: (x.movimiento.fecha, x.movimiento.id)):
            w.writerow(_fila_pendiente(p))
    salidas.append(ruta_p)

    ruta_c = carpeta / "cruces.csv"
    with ruta_c.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(ENCABEZADO_CRUCES)
        for c in resultado.cruces:
            w.writerow(_fila_cruce(c))
    salidas.append(ruta_c)

    return salidas


def imprimir_resumen(resultado: Resultado) -> str:
    """Resumen en texto para la consola."""
    r = resultado.resumen()
    lineas = [
        "",
        "  RESUMEN DE CONCILIACIÓN",
        "  " + "-" * 44,
        f"  Movimientos banco      {r['movimientos_banco']:>8}",
        f"  Movimientos libro      {r['movimientos_libro']:>8}",
        f"  Cruces encontrados     {r['cruces']:>8}",
        f"  Partidas abiertas      {r['pendientes_banco'] + r['pendientes_libro']:>8}"
        f"   (banco {r['pendientes_banco']}, libro {r['pendientes_libro']})",
        f"  Conciliado             {r['porcentaje_conciliado']:>7}%",
        f"  Diferencia por explicar {r['diferencia_total']:>7}",
    ]
    if r["cruces_por_tipo"]:
        lineas.append("  " + "-" * 44)
        for tipo, n in sorted(r["cruces_por_tipo"].items()):
            lineas.append(f"    {tipo:<20} {n:>6}")
    lineas.append("")
    return "\n".join(lineas)
