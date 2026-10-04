"""Extracción de la versión declarada dentro de un programa Progress (.p / .w)."""
import re

_PATRONES = (
    re.compile(r"""(?i)P-ValidarVersion\b[^"']*["']v?(\d+\.\d+(?:\.\d+)?)\b"""),
    re.compile(r"""(?i)(?:version|versión|ver|v)\s*[:=,]?\s*["']?v?(\d+\.\d+(?:\.\d+)?)\b"""),
    re.compile(r"\b(\d+\.\d+\.\d+)\b"),
)
NO_ESPECIFICADA = "No especificada"
_MAX_BYTES = 200_000


def extraer(contenido):
    for patron in _PATRONES:
        m = patron.search(contenido)
        if m:
            return m.group(1)
    return NO_ESPECIFICADA


def desde_bytes(datos):
    return extraer(datos[:_MAX_BYTES].decode("latin-1", errors="ignore"))


def desde_archivo(ruta):
    try:
        with open(ruta, "rb") as f:
            return desde_bytes(f.read(_MAX_BYTES))
    except OSError:
        return "Desconocida"
