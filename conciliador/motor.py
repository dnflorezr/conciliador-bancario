"""Motor de conciliación.

El cruce se hace en pasadas sucesivas, de la más estricta a la más laxa. Cada
pasada consume los movimientos que logró cruzar y le entrega el remanente a la
siguiente. El orden importa: si se buscara primero por tolerancia, una partida
que tenía contraparte exacta podría quedar emparejada con la equivocada.

Las pasadas son:

1. **Referencia** — misma referencia e igual importe. Es el cruce más confiable
   porque no depende de fechas.
2. **Exacto** — mismo importe y misma fecha.
3. **Ventana de fecha** — mismo importe, fecha dentro de ±N días. Cubre el
   desfase normal entre la fecha de registro y la de compensación bancaria.
4. **Tolerancia** — importe dentro de una tolerancia, fecha dentro de la
   ventana. Cubre diferencias por comisiones o redondeos.
5. **Agrupación** — varias partidas de un lado que suman una del otro. Es el
   caso de un abono bancario que agrupa varias facturas, o de un pago que el
   banco partió.

Lo que sobra queda como partida abierta, con el motivo por el que no cruzó.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations

from .modelos import (
    Cruce,
    Movimiento,
    MotivoPendiente,
    Origen,
    Pendiente,
    Resultado,
    TipoCruce,
)


@dataclass
class ConfigConciliacion:
    """Parámetros del cruce.

    Attributes:
        ventana_dias: Días de desfase admitidos entre las dos fechas.
        tolerancia: Diferencia absoluta admitida entre importes.
        max_grupo: Máximo de partidas que se intentan agrupar de un lado.
        usar_referencia: Si se intenta la pasada por referencia.
        invertir_signo_libro: Multiplica por -1 los importes del libro. Útil
            cuando el extracto trae los abonos en positivo y el auxiliar los
            registra en negativo (o al revés).
    """

    ventana_dias: int = 3
    tolerancia: Decimal = Decimal("0")
    max_grupo: int = 4
    usar_referencia: bool = True
    invertir_signo_libro: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.tolerancia, Decimal):
            self.tolerancia = Decimal(str(self.tolerancia))
        if self.ventana_dias < 0:
            raise ValueError("ventana_dias no puede ser negativa.")
        if self.tolerancia < 0:
            raise ValueError("La tolerancia no puede ser negativa.")
        if self.max_grupo < 1:
            raise ValueError("max_grupo debe ser al menos 1.")


def _dias(a: Movimiento, b: Movimiento) -> int:
    return abs((a.fecha - b.fecha).days)


def _orden(movs: list[Movimiento]) -> list[Movimiento]:
    """Orden estable para que una misma entrada produzca siempre la misma salida."""
    return sorted(movs, key=lambda m: (m.fecha, m.importe, m.id))


class Conciliador:
    """Cruza un extracto bancario contra un auxiliar contable."""

    def __init__(self, config: ConfigConciliacion | None = None) -> None:
        self.config = config or ConfigConciliacion()

    def conciliar(
        self, banco: list[Movimiento], libro: list[Movimiento]
    ) -> Resultado:
        """Ejecuta todas las pasadas y devuelve cruces y partidas abiertas."""
        pend_banco = _orden(list(banco))
        pend_libro = _orden([self._ajustar(m) for m in libro])

        resultado = Resultado()

        pasadas = []
        if self.config.usar_referencia:
            pasadas.append(self._pasada_referencia)
        pasadas += [
            self._pasada_exacta,
            self._pasada_ventana,
            self._pasada_tolerancia,
            self._pasada_agrupacion,
        ]

        for pasada in pasadas:
            cruces, pend_banco, pend_libro = pasada(pend_banco, pend_libro)
            resultado.cruces.extend(cruces)

        for m in pend_banco:
            resultado.pendientes.append(self._clasificar(m, pend_libro))
        for m in pend_libro:
            resultado.pendientes.append(self._clasificar(m, pend_banco))

        return resultado

    # ---------- preparación ----------

    def _ajustar(self, m: Movimiento) -> Movimiento:
        """Normaliza un movimiento del libro antes de cruzarlo."""
        importe = -m.importe if self.config.invertir_signo_libro else m.importe
        return Movimiento(
            id=m.id,
            fecha=m.fecha,
            importe=importe,
            descripcion=m.descripcion,
            referencia=m.referencia,
            origen=Origen.LIBRO,
        )

    # ---------- pasadas ----------

    def _pasada_referencia(
        self, banco: list[Movimiento], libro: list[Movimiento]
    ) -> tuple[list[Cruce], list[Movimiento], list[Movimiento]]:
        por_ref: dict[str, list[Movimiento]] = {}
        for m in libro:
            if m.referencia:
                por_ref.setdefault(m.referencia.strip().upper(), []).append(m)

        cruces: list[Cruce] = []
        usados_libro: set[str] = set()
        resto_banco: list[Movimiento] = []

        for b in banco:
            clave = b.referencia.strip().upper() if b.referencia else None
            candidato = None
            if clave:
                for l in por_ref.get(clave, []):
                    if l.id in usados_libro:
                        continue
                    if l.importe == b.importe:
                        candidato = l
                        break
            if candidato is None:
                resto_banco.append(b)
            else:
                usados_libro.add(candidato.id)
                cruces.append(
                    Cruce(TipoCruce.REFERENCIA, [b], [candidato], _dias(b, candidato))
                )

        resto_libro = [l for l in libro if l.id not in usados_libro]
        return cruces, resto_banco, resto_libro

    def _pasada_exacta(self, banco, libro):
        return self._emparejar_uno_a_uno(
            banco, libro, TipoCruce.EXACTO, ventana=0, tolerancia=Decimal("0")
        )

    def _pasada_ventana(self, banco, libro):
        return self._emparejar_uno_a_uno(
            banco,
            libro,
            TipoCruce.VENTANA_FECHA,
            ventana=self.config.ventana_dias,
            tolerancia=Decimal("0"),
        )

    def _pasada_tolerancia(self, banco, libro):
        if self.config.tolerancia == 0:
            return [], banco, libro
        return self._emparejar_uno_a_uno(
            banco,
            libro,
            TipoCruce.TOLERANCIA,
            ventana=self.config.ventana_dias,
            tolerancia=self.config.tolerancia,
        )

    def _emparejar_uno_a_uno(
        self,
        banco: list[Movimiento],
        libro: list[Movimiento],
        tipo: TipoCruce,
        ventana: int,
        tolerancia: Decimal,
    ) -> tuple[list[Cruce], list[Movimiento], list[Movimiento]]:
        """Empareja de a uno, eligiendo siempre el candidato de fecha más cercana."""
        cruces: list[Cruce] = []
        usados: set[str] = set()
        resto_banco: list[Movimiento] = []

        for b in banco:
            candidatos = [
                l
                for l in libro
                if l.id not in usados
                and abs(b.importe - l.importe) <= tolerancia
                and _dias(b, l) <= ventana
            ]
            if not candidatos:
                resto_banco.append(b)
                continue
            # Más cercano en fecha; a igualdad, la diferencia de importe menor.
            elegido = min(candidatos, key=lambda l: (_dias(b, l), abs(b.importe - l.importe), l.id))
            usados.add(elegido.id)
            cruces.append(Cruce(tipo, [b], [elegido], _dias(b, elegido)))

        resto_libro = [l for l in libro if l.id not in usados]
        return cruces, resto_banco, resto_libro

    def _pasada_agrupacion(
        self, banco: list[Movimiento], libro: list[Movimiento]
    ) -> tuple[list[Cruce], list[Movimiento], list[Movimiento]]:
        """Busca N partidas de un lado que sumen una del otro.

        Se prueba primero agrupando el libro contra cada movimiento del banco
        (el caso común: un abono que junta varias facturas) y luego al revés.
        La búsqueda se acota por tamaño de grupo y por ventana de fechas, de
        modo que el costo no explota con archivos grandes.
        """
        cruces: list[Cruce] = []
        usados_libro: set[str] = set()
        usados_banco: set[str] = set()

        cruces += self._agrupar(
            objetivos=banco,
            partes=libro,
            usados_objetivo=usados_banco,
            usados_parte=usados_libro,
            objetivo_es_banco=True,
        )
        cruces += self._agrupar(
            objetivos=[m for m in libro if m.id not in usados_libro],
            partes=[m for m in banco if m.id not in usados_banco],
            usados_objetivo=usados_libro,
            usados_parte=usados_banco,
            objetivo_es_banco=False,
        )

        resto_banco = [m for m in banco if m.id not in usados_banco]
        resto_libro = [m for m in libro if m.id not in usados_libro]
        return cruces, resto_banco, resto_libro

    def _agrupar(
        self,
        objetivos: list[Movimiento],
        partes: list[Movimiento],
        usados_objetivo: set[str],
        usados_parte: set[str],
        objetivo_es_banco: bool,
    ) -> list[Cruce]:
        cruces: list[Cruce] = []
        tol = self.config.tolerancia

        for obj in objetivos:
            if obj.id in usados_objetivo:
                continue
            vecinos = [
                p
                for p in partes
                if p.id not in usados_parte and _dias(obj, p) <= self.config.ventana_dias
            ]
            if len(vecinos) < 2:
                continue

            encontrado: tuple[Movimiento, ...] | None = None
            for tam in range(2, min(self.config.max_grupo, len(vecinos)) + 1):
                for combo in combinations(vecinos, tam):
                    suma = sum((m.importe for m in combo), Decimal("0"))
                    if abs(suma - obj.importe) <= tol:
                        encontrado = combo
                        break
                if encontrado:
                    break

            if not encontrado:
                continue

            usados_objetivo.add(obj.id)
            for m in encontrado:
                usados_parte.add(m.id)
            desfase = max(_dias(obj, m) for m in encontrado)
            lado_banco = [obj] if objetivo_es_banco else list(encontrado)
            lado_libro = list(encontrado) if objetivo_es_banco else [obj]
            cruces.append(Cruce(TipoCruce.AGRUPACION, lado_banco, lado_libro, desfase))

        return cruces

    # ---------- clasificación de lo que sobró ----------

    def _clasificar(self, m: Movimiento, contraparte: list[Movimiento]) -> Pendiente:
        """Explica por qué una partida quedó abierta.

        No basta con decir que no cruzó: al revisar la conciliación hay que
        saber si no existe contraparte, si existe pero con fecha lejana, o si
        existe en la fecha pero con un importe distinto. Cada caso se resuelve
        de forma diferente.
        """
        mismo_importe = [o for o in contraparte if o.importe == m.importe]
        if mismo_importe:
            cercano = min(mismo_importe, key=lambda o: _dias(m, o))
            return Pendiente(
                m,
                MotivoPendiente.FUERA_DE_VENTANA,
                f"Existe {cercano.id} por el mismo importe, con {_dias(m, cercano)} días de diferencia.",
            )

        misma_fecha = [o for o in contraparte if _dias(m, o) <= self.config.ventana_dias]
        if misma_fecha:
            cercano = min(misma_fecha, key=lambda o: abs(o.importe - m.importe))
            delta = m.importe - cercano.importe
            # Que haya una partida en la misma fecha no la convierte en la
            # contraparte: si el importe es de otro orden de magnitud, es otra
            # transacción y reportarla como diferencia de tolerancia manda a
            # quien revisa por un camino equivocado. Solo se señala cuando la
            # diferencia es del tamaño que tendría una comisión o un redondeo.
            margen = max(self.config.tolerancia * 10, abs(m.importe) * Decimal("0.05"))
            if abs(delta) <= margen:
                return Pendiente(
                    m,
                    MotivoPendiente.FUERA_DE_TOLERANCIA,
                    f"Existe {cercano.id} en la ventana de fechas, con diferencia de {delta}.",
                )

        return Pendiente(m, MotivoPendiente.SIN_CONTRAPARTE, "Sin contraparte en el otro extracto.")
