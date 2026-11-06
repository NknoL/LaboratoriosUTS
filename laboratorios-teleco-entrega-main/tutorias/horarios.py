"""Franjas semanales de prestamo de 45 minutos."""

from datetime import date, datetime, time, timedelta

JORNADAS = (("09:00", "18:00"),)


def dentro_jornada(inicio, fin):
    return time(9) <= inicio < fin <= time(18)


def intervalo_45(inicio, fin):
    cursor = datetime.combine(date.min, time.fromisoformat(inicio))
    limite = datetime.combine(date.min, time.fromisoformat(fin))
    while cursor + timedelta(minutes=45) <= limite:
        siguiente = cursor + timedelta(minutes=45)
        yield cursor.time(), siguiente.time()
        cursor = siguiente


def franjas_45():
    for inicio, fin in JORNADAS:
        yield from intervalo_45(inicio, fin)
