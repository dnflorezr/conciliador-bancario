"""Conciliador bancario: cruza un extracto contra un auxiliar contable."""

from .cargador import ErrorDeCarga, MapeoColumnas, cargar
from .modelos import (
    Cruce,
    Movimiento,
    MotivoPendiente,
    Origen,
    Pendiente,
    Resultado,
    TipoCruce,
)
from .motor import Conciliador, ConfigConciliacion
from .reporte import escribir_csv, escribir_excel, imprimir_resumen

__version__ = "1.0.0"

__all__ = [
    "Conciliador",
    "ConfigConciliacion",
    "Cruce",
    "ErrorDeCarga",
    "MapeoColumnas",
    "Movimiento",
    "MotivoPendiente",
    "Origen",
    "Pendiente",
    "Resultado",
    "TipoCruce",
    "cargar",
    "escribir_csv",
    "escribir_excel",
    "imprimir_resumen",
]
