# Conciliador bancario

Cruza un extracto bancario contra un auxiliar contable y devuelve los cruces, las partidas que quedan abiertas y el motivo por el que cada una no cruzó.

Nació de hacer conciliaciones a mano en Excel durante varios años y querer automatizar la parte mecánica sin perder el criterio: qué se puede dar por conciliado, qué merece revisión y qué hay que investigar.

```
python -m conciliador extracto_banco.csv auxiliar_contable.csv -o conciliacion.xlsx
```

```
  RESUMEN DE CONCILIACIÓN
  --------------------------------------------
  Movimientos banco            12
  Movimientos libro            12
  Cruces encontrados            8
  Partidas abiertas             6   (banco 4, libro 2)
  Conciliado                75.0%
  Diferencia por explicar 1395000.00
  --------------------------------------------
    agrupacion                1
    exacto                    2
    referencia                3
    tolerancia                1
    ventana_fecha             1
```

## Cómo cruza

El problema no es comparar dos listas. Es que el banco y el libro casi nunca registran lo mismo el mismo día por el mismo valor: hay desfases de compensación, comisiones que el banco descuenta y el libro no previó, y abonos que agrupan varias facturas.

El motor hace cinco pasadas, de la más estricta a la más laxa. Cada una consume lo que logró cruzar y le pasa el resto a la siguiente.

| Pasada | Criterio | Para qué caso |
|---|---|---|
| Referencia | Misma referencia e igual importe | El cruce más confiable: no depende de fechas |
| Exacto | Mismo importe y misma fecha | El caso limpio |
| Ventana de fecha | Mismo importe, fecha dentro de ±N días | Desfase entre registro y compensación |
| Tolerancia | Importe dentro de una tolerancia, fecha en la ventana | Comisiones, GMF, redondeos |
| Agrupación | Varias partidas de un lado que suman una del otro | Un abono que junta facturas; un pago que el banco partió |

**El orden importa.** Si se buscara primero por tolerancia, una partida con contraparte exacta podría quedar emparejada con la aproximada y dejar abierta la que sí era. Hay una prueba que verifica justamente eso.

## Las partidas abiertas llevan motivo

Decir "no cruzó" no sirve para trabajar. El reporte distingue tres situaciones, porque cada una se resuelve distinto:

- **Sin contraparte** — no existe nada parecido al otro lado. Suele ser un cheque girado y no cobrado, o un movimiento bancario no registrado.
- **Fuera de ventana** — existe una partida por el mismo importe, pero con fecha lejana. La nota dice cuál y cuántos días hay de diferencia: casi siempre basta con ampliar la ventana.
- **Fuera de tolerancia** — existe una partida en la fecha, con diferencia pequeña. La nota trae el valor exacto de la diferencia.

Una partida en la misma fecha pero de otro orden de magnitud **no** se reporta como diferencia de tolerancia: es otra transacción, y señalarla mandaría a quien revisa a buscar una comisión que no existe.

## Dos decisiones técnicas

**Los importes son `Decimal`, nunca `float`.** En conciliación, `0.1 + 0.2 != 0.3` no es una curiosidad académica: es un grupo que no cuadra y una partida que queda abierta sin razón. El modelo rechaza en tiempo de construcción cualquier importe que no sea `Decimal`.

**El cruce es determinista.** Los movimientos se ordenan antes de procesarse y, cuando hay varios candidatos, se elige el más cercano en fecha y, a igualdad, el de menor diferencia de importe. La misma entrada produce siempre la misma salida, que es condición para poder auditar el resultado.

## Instalación

```bash
git clone https://github.com/dnflorezr/conciliador-bancario.git
cd conciliador-bancario
pip install -r requirements.txt
```

Requiere Python 3.10 o superior. La única dependencia es `openpyxl`, y solo para leer y escribir Excel: el motor es biblioteca estándar.

## Uso

```bash
# Básico
python -m conciliador banco.csv libro.csv

# Ventana de 5 días y tolerancia de 1.000 para comisiones
python -m conciliador banco.xlsx libro.xlsx -o salida.xlsx --ventana 5 --tolerancia 1000

# Cuando las columnas se llaman distinto
python -m conciliador banco.csv libro.csv --col-fecha "Fecha Mov" --col-importe "Valor"

# Cuando el extracto trae los abonos con signo contrario al libro
python -m conciliador banco.csv libro.csv --invertir-libro

# Salida en CSV en vez de Excel
python -m conciliador banco.csv libro.csv --csv
```

| Opción | Por defecto | Qué hace |
|---|---|---|
| `--ventana N` | 3 | Días de desfase admitidos |
| `--tolerancia X` | 0 | Diferencia de importe admitida |
| `--max-grupo N` | 4 | Máximo de partidas a agrupar |
| `--sin-referencia` | — | Omite la pasada por referencia |
| `--invertir-libro` | — | Invierte el signo de los importes del libro |
| `--csv` | — | Escribe CSV en lugar de Excel |

La CLI devuelve **1** si quedaron partidas abiertas y **0** si todo cuadró, para poder encadenarla en un flujo que avise cuando la conciliación no cierra.

### Formato de entrada

CSV (con coma, punto y coma o tabulación) o Excel. Columnas mínimas: `fecha` e `importe`; opcionales `descripcion`, `referencia` e `id`.

El cargador tolera lo que llega en la práctica: `1.234.567,89` y `1,234,567.89`, el símbolo de moneda, los paréntesis contables para negativos, y las fechas en `dd/mm/aaaa`, `aaaa-mm-dd` y cuatro formatos más. Si una fila no se puede interpretar, el error dice cuál es y en qué número de fila está.

## El reporte

Tres hojas, en el orden en que se revisa una conciliación:

1. **Resumen** — cuánto cuadró, cuánto falta por explicar y cuántos cruces de cada tipo.
2. **Partidas abiertas** — lo que hay que trabajar, con motivo y nota.
3. **Cruces** — el detalle para auditar el resultado si algo se ve raro.

## Uso como biblioteca

```python
from decimal import Decimal
from conciliador import Conciliador, ConfigConciliacion, Origen, cargar

banco = cargar("extracto.csv", Origen.BANCO)
libro = cargar("auxiliar.csv", Origen.LIBRO)

config = ConfigConciliacion(ventana_dias=5, tolerancia=Decimal("1000"))
resultado = Conciliador(config).conciliar(banco, libro)

print(resultado.resumen())

for p in resultado.pendientes:
    print(p.movimiento.id, p.motivo.value, p.nota)
```

## Pruebas

```bash
pip install pytest
python -m pytest tests/ -q
```

70 pruebas que cubren los formatos de entrada, cada pasada del motor, el orden entre pasadas, la clasificación de partidas abiertas y los casos límite (archivos vacíos, un solo lado, centavos que con `float` se perderían).

## Datos de ejemplo

`datos_ejemplo/` trae un extracto y un auxiliar construidos para que cada pasada tenga al menos un caso que la active, incluidos un cheque no cobrado, una comisión bancaria y un abono que agrupa tres facturas. Se regeneran con `python datos_ejemplo/generar.py`.

## Estructura

```
conciliador/
  modelos.py    Movimiento, Cruce, Pendiente, Resultado
  cargador.py   Lectura de CSV/Excel y normalización de fechas e importes
  motor.py      Las cinco pasadas y la clasificación de pendientes
  reporte.py    Salida en Excel y CSV
  cli.py        Línea de comandos
```

## Qué falta

- Conciliación de varios contra varios (N del banco contra M del libro).
- Memoria de cruces manuales, para que lo resuelto a mano una vez no vuelva a aparecer.
- Lectura directa de extractos en formatos propios de cada banco.

## Licencia

MIT.
