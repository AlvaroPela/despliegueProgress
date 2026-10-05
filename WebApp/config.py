"""Configuración central: rutas, valores por defecto y acceso a config.json / servidores.json."""
import json
import os
import secrets
import threading

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)  # carpeta que contiene config.json, servidores.json y compilar.p

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SERVIDORES_PATH = os.path.join(BASE_DIR, "servidores.json")
COMPILAR_P_PATH = os.path.join(BASE_DIR, "compilar.p")
USUARIOS_PATH = os.path.join(BASE_DIR, "usuarios.xlsx")

HISTORIAL_PATH = os.path.join(APP_DIR, "historial.xlsx")
LOG_DIR = os.path.join(APP_DIR, "logs")
EVIDENCIAS_DIR = os.path.join(APP_DIR, "evidencias")  # pantallazos de versiones en Escala
SECRET_KEY_PATH = os.path.join(APP_DIR, "secret.key")

DEFAULTS = {
    "RutaOrigen": r"C:\tempo\Programas",
    "RutaBaseY": r"C:\Compilacion",
    "RutaBaseN": r"N:\Escala\Fuentes",
    "RutaRutinasN": r"N:\Escala\Rutinas",
    "RutaCompilados": r"C:\tempo\Compilados",
    "RutaBackup": r"C:\tempo\Backup",
    "ProgressExe": r"C:\Progress12\bin\prowin.exe",
    "ProgressIni": r"H:\escala12.ini",
    "DbHost": "10.100.4.10",
    "DbPuertoDatos": 2700,
    "DbPuertoSeguimiento": 5150,
    "TimeoutCompilacion": 300,
    "UsuarioSmtp": "",
    "Destinatario": [],
    "Auth_ClientID": "",
    "Auth_Tenant": "",
    "LdapServer": "HOSTNEPTUNO",
    "LdapDominio": "CONFIAR",
    "ModoPruebas": False,
    "RestringirAUsuarios": False,
    "RutinasEspeciales": [
        "P-ConsultarWM.p", "P-EvaluacionExterna.p", "P-IntegrarWM.p", "p-rutdis.p",
        "p-RutDisCupo.p", "P-RutinasCierre.p", "P-RutSagem.p", "rutfinan.p", "ruticon.p",
        "rutinas.p", "RutinaVivienda.p", "Rutitaq.p", "RutPinPad.p", "RutTaqNew.p", "W-RutSagem.w",
    ],
}

# Claves que NUNCA deben vivir en config.json (se guardan cifradas con DPAPI)
CLAVES_PROHIBIDAS = ("DB_User", "DB_Pass")

_io_lock = threading.Lock()


def _leer_json(path, defecto):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        return defecto
    except json.JSONDecodeError as exc:
        raise ValueError(f"{os.path.basename(path)} no es un JSON válido: {exc}") from exc


def _escribir_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp, path)


def load_config():
    """Devuelve la configuración combinada con los valores por defecto."""
    with _io_lock:
        cfg = dict(DEFAULTS)
        cfg.update(_leer_json(CONFIG_PATH, {}))
    for clave in CLAVES_PROHIBIDAS:
        cfg.pop(clave, None)
    if isinstance(cfg.get("Destinatario"), str):
        cfg["Destinatario"] = [d.strip() for d in cfg["Destinatario"].split(",") if d.strip()]
    return cfg


def save_config(cambios):
    """Actualiza config.json conservando las claves no enviadas."""
    with _io_lock:
        actual = _leer_json(CONFIG_PATH, {})
        actual.update(cambios)
        for clave in CLAVES_PROHIBIDAS:
            actual.pop(clave, None)
        _escribir_json(CONFIG_PATH, actual)


def load_servidores():
    data = _leer_json(SERVIDORES_PATH, {})
    return {"DG": list(data.get("DG", [])), "Oficinas": list(data.get("Oficinas", []))}


def save_servidores(dg, oficinas):
    with _io_lock:
        _escribir_json(SERVIDORES_PATH, {"DG": dg, "Oficinas": oficinas})


def limpiar_secretos_en_config():
    """Elimina credenciales en texto plano que hayan quedado en config.json de versiones previas."""
    with _io_lock:
        actual = _leer_json(CONFIG_PATH, None)
        if actual and any(k in actual for k in CLAVES_PROHIBIDAS):
            for clave in CLAVES_PROHIBIDAS:
                actual.pop(clave, None)
            _escribir_json(CONFIG_PATH, actual)


def get_secret_key():
    """Clave de sesión persistente, generada en el primer arranque (no está en el código)."""
    if os.path.exists(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, "r", encoding="utf-8") as f:
            valor = f.read().strip()
            if valor:
                return valor
    valor = secrets.token_hex(32)
    with open(SECRET_KEY_PATH, "w", encoding="utf-8") as f:
        f.write(valor)
    return valor
