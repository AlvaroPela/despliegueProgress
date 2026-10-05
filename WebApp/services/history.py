"""Bitácora de despliegues en historial.xlsx (única capa de acceso al archivo)."""
import logging
import threading
from datetime import datetime

import pandas as pd

from config import HISTORIAL_PATH
from services import excel

log = logging.getLogger(__name__)

COLUMNAS = ["ID", "Caso", "Usuario", "Fecha", "Destino", "Estado", "Detalle", "Duracion", "Log_File",
            "Versiones", "Version_Escala", "Version_Confirmada_Por", "Version_Confirmada_En"]
_lock = threading.RLock()

EN_PROCESO = "En Proceso"

# Las versiones de Escala se actualizan a mano: cada despliegue exitoso queda "Pendiente"
# hasta que alguien confirma en la app que ya registró las versiones.
VERSION_PENDIENTE = "Pendiente"
VERSION_CONFIRMADA = "Confirmada"


def versiones_texto(versiones):
    return "; ".join(f"{n}={v}" for n, v in versiones.items())


def versiones_dict(texto):
    pares = (p.split("=", 1) for p in str(texto or "").split(";") if "=" in p)
    return [{"programa": n.strip(), "version": v.strip()} for n, v in pares]


def obtener(registro_id):
    return next((r for r in listar() if str(r["ID"]) == str(registro_id)), None)


def confirmar_version(registro_id, usuario):
    """Marca que las versiones del despliegue ya se actualizaron en Escala. Devuelve el registro."""
    with _lock:
        registro = obtener(registro_id)
        if not registro:
            raise ValueError("Despliegue no encontrado.")
        if registro["Version_Escala"] == VERSION_CONFIRMADA:
            raise ValueError(f"Ya fue confirmado por {registro['Version_Confirmada_Por']} el {registro['Version_Confirmada_En']}.")
        if registro["Version_Escala"] != VERSION_PENDIENTE:
            raise ValueError("Este despliegue no tiene versiones pendientes de actualizar en Escala.")
        actualizar(int(registro_id), Version_Escala=VERSION_CONFIRMADA, Version_Confirmada_Por=usuario,
                   Version_Confirmada_En=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return obtener(registro_id)


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
        r["ListaVersiones"] = versiones_dict(r["Versiones"])
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
        "versiones_pendientes": sum(1 for r in registros if r["Version_Escala"] == VERSION_PENDIENTE),
        "tasa_exito": round(exitosos * 100 / terminados) if terminados else 0,
    }

