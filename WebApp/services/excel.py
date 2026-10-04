"""Lectura/escritura segura de los archivos .xlsx (historial y usuarios).

En Windows, si el archivo está abierto en Excel o lo bloquea OneDrive/antivirus, os.replace
lanza PermissionError. Antes eso se convertía en un "Error interno" en cualquier acción;
ahora se reintenta unos segundos y, si persiste, se informa con un mensaje claro.
"""
import os
import time

import pandas as pd

REINTENTOS = 6
ESPERA_S = 0.5


class ArchivoBloqueado(RuntimeError):
    pass


def _reparar(texto):
    """Corrige textos guardados con doble codificación (p. ej. 'reiniciÃ³' -> 'reinició')."""
    if isinstance(texto, str) and ("Ã" in texto or "Â" in texto):
        try:
            return texto.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return texto
    return texto


def leer(ruta, columnas, dtype=None):
    if not os.path.exists(ruta):
        return pd.DataFrame(columns=columnas)
    df = pd.read_excel(ruta, dtype=dtype)
    for col in columnas:
        if col not in df.columns:
            df[col] = ""
    df = df[columnas].astype(object)
    df = df.where(df.notna(), "")
    return df.apply(lambda col: col.map(_reparar))


def escribir(df, ruta):
    tmp = os.path.splitext(ruta)[0] + ".tmp.xlsx"  # la extensión .xlsx le indica a pandas el motor
    df.to_excel(tmp, index=False, engine="openpyxl")
    for intento in range(REINTENTOS):
        try:
            os.replace(tmp, ruta)
            return
        except PermissionError:
            if intento == REINTENTOS - 1:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise ArchivoBloqueado(
                    f"No se pudo guardar {os.path.basename(ruta)}: el archivo está abierto en otro programa "
                    "(¿Excel?). Ciérralo e inténtalo de nuevo.")
            time.sleep(ESPERA_S)


def siguiente_id(df):
    ids = pd.to_numeric(df["ID"], errors="coerce").dropna()
    return int(ids.max()) + 1 if len(ids) else 1
