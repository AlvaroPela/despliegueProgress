"""Utilidades de red y diagnóstico del entorno."""
import os
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor

from config import COMPILAR_P_PATH, CONFIG_PATH, SERVIDORES_PATH, load_config
from services import credentials

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
IP_RE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})")


def extraer_ip(texto):
    m = IP_RE.search(texto or "")
    return m.group(1) if m else None


def extraer_host(entrada):
    """Host de una entrada de servidores: '\\\\host\\recurso' -> 'host'; 'host' o IP -> igual."""
    entrada = (entrada or "").strip()
    if entrada.startswith("\\\\"):
        return entrada[2:].split("\\")[0]
    return entrada


def resolver_ip(host):
    """IP de un host (o la misma IP). None si el nombre no se puede resolver."""
    ip = extraer_ip(host)
    if ip and ip == host:
        return ip
    try:
        return socket.gethostbyname(host)
    except OSError:
        return None


def nombre_de(ip):
    """Hostname (DNS inverso) de una IP, sin el dominio. Vacío si no tiene registro."""
    try:
        return socket.gethostbyaddr(ip)[0].split(".")[0].upper()
    except OSError:
        return ""


def info_servidor(entrada, timeout_ms=800):
    """Resuelve IP y hostname de una entrada (IP, hostname o ruta UNC) y comprueba si responde al ping."""
    host = extraer_host(entrada)
    ip = resolver_ip(host) if host else None
    es_ip = bool(extraer_ip(host)) and extraer_ip(host) == host
    hostname = (nombre_de(ip) if ip else "") if es_ip else host.split(".")[0].upper()
    return {"entrada": entrada, "host": host, "ip": ip or "", "hostname": hostname,
            "resuelto": bool(ip), "ping": bool(ip) and ping(ip, timeout_ms)}


def info_servidores(entradas, hilos=32):
    entradas = [e for e in entradas if (e or "").strip()]
    if not entradas:
        return []
    with ThreadPoolExecutor(max_workers=min(hilos, len(entradas))) as pool:
        return list(pool.map(info_servidor, entradas))


def ping(host, timeout_ms=1000):
    try:
        return subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout_ms), host] if os.name == "nt"
            else ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW, timeout=10,
        ).returncode == 0
    except Exception:
        return False


def _check(id_, etiqueta, nivel, detalle=""):
    return {"id": id_, "label": etiqueta, "nivel": nivel, "detalle": detalle}


def revisar_entorno(con_red=True):
    """Lista de verificaciones. nivel: ok | warn | error. 'listo' es False si hay algún error."""
    checks = []
    try:
        cfg = load_config()
    except ValueError as exc:
        return {"checks": [_check("config", "config.json", "error", str(exc))], "listo": False}

    checks.append(_check("config", "config.json", "ok" if os.path.exists(CONFIG_PATH) else "error",
                         CONFIG_PATH))
    checks.append(_check("servidores", "servidores.json",
                         "ok" if os.path.exists(SERVIDORES_PATH) else "error", SERVIDORES_PATH))
    checks.append(_check("compilar", "compilar.p", "ok" if os.path.exists(COMPILAR_P_PATH) else "error",
                         COMPILAR_P_PATH))
    checks.append(_check("prowin", "OpenEdge (prowin.exe)",
                         "ok" if os.path.exists(cfg["ProgressExe"]) else "error", cfg["ProgressExe"]))
    for base in credentials.BASES_BD:
        ok = credentials.existe(base)
        checks.append(_check(f"creds_{base.lower()}", f"Credenciales BD «{base.lower()}»", "ok" if ok else "error",
                             "Configuradas" if ok else "Faltan: Mi perfil > Bases de datos"))
    checks.append(_check("ini", "Archivo INI de Progress",
                         "ok" if os.path.exists(cfg["ProgressIni"]) else "warn", cfg["ProgressIni"]))
    checks.append(_check("rutan", "Unidad de fuentes en red",
                         "ok" if os.path.isdir(os.path.dirname(cfg["RutaBaseN"]) or cfg["RutaBaseN"]) else "warn",
                         cfg["RutaBaseN"]))
    smtp_ok = bool(cfg["Auth_ClientID"] and cfg["Auth_Tenant"] and cfg["UsuarioSmtp"] and credentials.existe("Smtp"))
    checks.append(_check("smtp", "Correo (Microsoft Graph)", "ok" if smtp_ok else "warn",
                         "Listo" if smtp_ok else "Sin configurar: no se enviarán notificaciones"))
    if con_red:
        up = ping(cfg["DbHost"], 700)
        checks.append(_check("db", "Servidor de base de datos", "ok" if up else "warn",
                             f"{cfg['DbHost']} " + ("responde" if up else "no responde al ping")))
    return {"checks": checks, "listo": not any(c["nivel"] == "error" for c in checks)}
