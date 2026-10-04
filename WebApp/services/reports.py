"""Estadísticas para el dashboard y los informes."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta


def _fecha(registro):
    try:
        return datetime.strptime(str(registro["Fecha"])[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _segundos(texto):
    try:
        m, s = str(texto).split(":")
        return int(m) * 60 + int(s)
    except ValueError:
        return None


def serie_diaria(registros, dias=14):
    hoy = date.today()
    fechas = [hoy - timedelta(days=d) for d in reversed(range(dias))]
    acum = {f: Counter() for f in fechas}
    for r in registros:
        f = _fecha(r)
        if f in acum and r["Clase"] in ("exito", "fallo"):
            acum[f][r["Clase"]] += 1
    return {
        "labels": [f.strftime("%d/%m") for f in fechas],
        "exito": [acum[f]["exito"] for f in fechas],
        "fallo": [acum[f]["fallo"] for f in fechas],
    }


def por_mes(registros, meses=6):
    acum = defaultdict(Counter)
    for r in registros:
        f = _fecha(r)
        if f:
            acum[f.strftime("%Y-%m")][r["Clase"]] += 1
    claves = sorted(acum)[-meses:]
    return {
        "labels": claves,
        "exito": [acum[k]["exito"] for k in claves],
        "fallo": [acum[k]["fallo"] for k in claves],
    }


def por_usuario(registros):
    acum = defaultdict(Counter)
    for r in registros:
        acum[str(r["Usuario"])][r["Clase"]] += 1
    filas = [{"usuario": u, "total": sum(c.values()), "exito": c["exito"], "fallo": c["fallo"]}
             for u, c in acum.items()]
    return sorted(filas, key=lambda x: x["total"], reverse=True)


def por_estado(registros):
    return Counter(str(r["Estado"]) for r in registros).most_common()


def duracion_promedio(registros):
    valores = [s for s in (_segundos(r["Duracion"]) for r in registros) if s is not None]
    if not valores:
        return "—"
    promedio = sum(valores) // len(valores)
    return f"{promedio // 60:02d}:{promedio % 60:02d}"
