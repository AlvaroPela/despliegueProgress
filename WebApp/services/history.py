"""Bitácora de despliegues en historial.xlsx (única capa de acceso al archivo)."""
import logging
import threading
from datetime import datetime

import pandas as pd

from config import HISTORIAL_PATH
from services import excel

log = logging.getLogger(__name__)

COLUMNAS = ["ID", "Caso", "Usuario", "Fecha", "Destino", "Estado", "Detalle", "Duracion", "Log_File"]
_lock = threading.RLock()

EN_PROCESO = "En Proceso"


def clasificar(estado):
    """exito | proceso | fallo"""
    e = str(estado or "").lower()
    if e.startswith("exitoso"):
        return "exito"
    if "proceso" in e:
        return "proceso"
    return "fallo"


def _leer():
    return excel.leer(HISTORIAL_PATH, COLUMNAS, dtype={"Caso": str})


def _escribir(df):
    excel.escribir(df, HISTORIAL_PATH)


def crear(caso, usuario, destino):
    with _lock:
        df = _leer()
        nuevo_id = excel.siguiente_id(df)
        fila = {
            "ID": nuevo_id, "Caso": str(caso), "Usuario": usuario,
            "Fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Destino": destino, "Estado": EN_PROCESO, "Detalle": "", "Duracion": "", "Log_File": "",
        }
        df = pd.concat([df, pd.DataFrame([fila])], ignore_index=True)
        _escribir(df)
        return nuevo_id


def actualizar(registro_id, **campos):
    with _lock:
        df = _leer()
        idx = df.index[pd.to_numeric(df["ID"], errors="coerce") == registro_id]
        if len(idx) == 0:
            log.warning("Registro %s no encontrado en el historial", registro_id)
            return
        for campo, valor in campos.items():
            if campo in COLUMNAS:
                df.loc[idx, campo] = valor
        _escribir(df)


def listar():
    with _lock:
        try:
            df = _leer()
        except Exception:
            log.exception("No se pudo leer el historial")
            return []
    df["_id"] = pd.to_numeric(df["ID"], errors="coerce")
    df = df.sort_values("_id", ascending=False).drop(columns="_id")
    registros = df.to_dict("records")
    for r in registros:
        r["Clase"] = clasificar(r["Estado"])
    return registros


def marcar_interrumpidos():
    """Si el servidor se reinició a mitad de un despliegue, el registro quedaría 'En Proceso' para siempre."""
    with _lock:
        try:
            df = _leer()
        except Exception:
            return
        mask = df["Estado"].astype(str).str.lower().str.contains("proceso")
        if mask.any():
            df.loc[mask, "Estado"] = "Interrumpido"
            df.loc[mask, "Detalle"] = "El servicio se reinició durante la ejecución."
            try:
                _escribir(df)
            except Exception:
                log.exception("No se pudieron marcar los despliegues interrumpidos")


def estadisticas(registros=None):
    registros = listar() if registros is None else registros
    total = len(registros)
    exitosos = sum(1 for r in registros if r["Clase"] == "exito")
    fallidos = sum(1 for r in registros if r["Clase"] == "fallo")
    proceso = sum(1 for r in registros if r["Clase"] == "proceso")
    terminados = exitosos + fallidos
    return {
        "total": total, "exitosos": exitosos, "fallidos": fallidos, "en_proceso": proceso,
        "tasa_exito": round(exitosos * 100 / terminados) if terminados else 0,
    }

