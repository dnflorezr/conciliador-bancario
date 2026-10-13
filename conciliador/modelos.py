"""Estructuras de datos del conciliador.

Los importes se manejan con ``Decimal`` y nunca con ``float``: en conciliación
una diferencia de centavos es una partida abierta, y la aritmética de punto
flotante introduce errores que se acumulan en los agrupamientos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


class Origen(str, Enum):
    """De qué lado de la conciliación viene un movimiento."""

    BANCO = "banco"
    LIBRO = "libro"


class TipoCruce(str, Enum):
    """Cómo se encontró un cruce. El orden refleja la calidad del match."""

    REFERENCIA = "referencia"
    EXACTO = "exacto"
    VENTANA_FECHA = "ventana_fecha"
    TOLERANCIA = "tolerancia"
    AGRUPACION = "agrupacion"


class MotivoPendiente(str, Enum):
    """Por qué una partida quedó sin conciliar."""

    SIN_CONTRAPARTE = "sin_contraparte"
    FUERA_DE_VENTANA = "fuera_de_ventana"
    FUERA_DE_TOLERANCIA = "fuera_de_tolerancia"


@dataclass(frozen=True)
class Movimiento:
    """Una línea del extracto bancario o del auxiliar contable."""

    id: str
    fecha: date
    importe: Decimal
    descripcion: str = ""
    referencia: Optional[str] = None
    origen: Origen = Origen.BANCO

    def __post_init__(self) -> None:
        if not isinstance(self.importe, Decimal):
            raise TypeError(
                f"El importe de {self.id} debe ser Decimal, no {type(self.importe).__name__}."
            )


@dataclass
class Cruce:
    """Un grupo conciliado: uno o varios movimientos de cada lado.

    La mayoría de los cruces son 1 a 1, pero los casos interesantes no lo son:
    un abono bancario que agrupa varias facturas, o un pago del libro que el
    banco partió en dos. Por eso ambos lados son listas.
    """

    tipo: TipoCruce
    banco: list[Movimiento]
    libro: list[Movimiento]
    dias_diferencia: int = 0

    @property
    def importe_banco(self) -> Decimal:
        return sum((m.importe for m in self.banco), Decimal("0"))

    @property
    def importe_libro(self) -> Decimal:
        return sum((m.importe for m in self.libro), Decimal("0"))

    @property
    def diferencia(self) -> Decimal:
        """Banco menos libro. Cero en los cruces exactos."""
        return self.importe_banco - self.importe_libro

    @property
    def es_uno_a_uno(self) -> bool:
        return len(self.banco) == 1 and len(self.libro) == 1


@dataclass
class Pendiente:
    """Una partida que quedó abierta, con el motivo por el que no cruzó."""

    movimiento: Movimiento
    motivo: MotivoPendiente
    nota: str = ""


@dataclass
class Resultado:
    """Salida completa de una corrida de conciliación."""

    cruces: list[Cruce] = field(default_factory=list)
    pendientes: list[Pendiente] = field(default_factory=list)

    @property
    def pendientes_banco(self) -> list[Pendiente]:
        return [p for p in self.pendientes if p.movimiento.origen is Origen.BANCO]

    @property
    def pendientes_libro(self) -> list[Pendiente]:
        return [p for p in self.pendientes if p.movimiento.origen is Origen.LIBRO]

    @property
    def diferencia_total(self) -> Decimal:
        """Suma de las partidas abiertas: lo que falta por explicar."""
        banco = sum((p.movimiento.importe for p in self.pendientes_banco), Decimal("0"))
        libro = sum((p.movimiento.importe for p in self.pendientes_libro), Decimal("0"))
        return banco - libro

    def resumen(self) -> dict[str, object]:
        conciliados_banco = sum(len(c.banco) for c in self.cruces)
        conciliados_libro = sum(len(c.libro) for c in self.cruces)
        total_banco = conciliados_banco + len(self.pendientes_banco)
        total_libro = conciliados_libro + len(self.pendientes_libro)
        por_tipo: dict[str, int] = {}
        for c in self.cruces:
            por_tipo[c.tipo.value] = por_tipo.get(c.tipo.value, 0) + 1
        return {
            "cruces": len(self.cruces),
            "cruces_por_tipo": por_tipo,
            "movimientos_banco": total_banco,
            "movimientos_libro": total_libro,
            "conciliados_banco": conciliados_banco,
            "conciliados_libro": conciliados_libro,
            "pendientes_banco": len(self.pendientes_banco),
            "pendientes_libro": len(self.pendientes_libro),
            "diferencia_total": self.diferencia_total,
            "porcentaje_conciliado": (
                round(100 * (conciliados_banco + conciliados_libro) / (total_banco + total_libro), 2)
                if (total_banco + total_libro)
                else 0.0
            ),
        }
