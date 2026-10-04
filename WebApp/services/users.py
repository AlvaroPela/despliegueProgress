"""Gestión de usuarios autorizados (usuarios.xlsx)."""
import threading

import pandas as pd

from config import USUARIOS_PATH
from services import excel

COLUMNAS = ["ID", "Usuario", "Nombre", "Rol", "Estado"]
ROLES = ("Administrador", "Operador", "Consulta")
_lock = threading.RLock()


def _leer():
    return excel.leer(USUARIOS_PATH, COLUMNAS)


def _escribir(df):
    excel.escribir(df, USUARIOS_PATH)


def listar():
    with _lock:
        try:
            return _leer().to_dict("records")
        except Exception:
            return []


def agregar(usuario, nombre, rol="Operador", estado="Activo"):
    usuario = (usuario or "").strip()
    if not usuario:
        raise ValueError("El usuario es obligatorio.")
    if rol not in ROLES:
        raise ValueError("Rol no válido.")
    with _lock:
        df = _leer()
        if (df["Usuario"].astype(str).str.lower() == usuario.lower()).any():
            raise ValueError("El usuario ya existe.")
        nuevo_id = excel.siguiente_id(df)
        fila = {"ID": nuevo_id, "Usuario": usuario, "Nombre": (nombre or "").strip() or usuario,
                "Rol": rol, "Estado": estado}
        _escribir(pd.concat([df, pd.DataFrame([fila])], ignore_index=True))


def actualizar(user_id, rol=None, estado=None):
    with _lock:
        df = _leer()
        idx = df.index[pd.to_numeric(df["ID"], errors="coerce") == user_id]
        if len(idx) == 0:
            raise ValueError("Usuario no encontrado.")
        if rol:
            if rol not in ROLES:
                raise ValueError("Rol no válido.")
            df.loc[idx, "Rol"] = rol
        if estado:
            df.loc[idx, "Estado"] = estado
        _escribir(df)


def eliminar(user_id):
    with _lock:
        df = _leer()
        mask = pd.to_numeric(df["ID"], errors="coerce") == user_id
        if not mask.any():
            raise ValueError("Usuario no encontrado.")
        _escribir(df[~mask])

