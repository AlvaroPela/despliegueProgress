"""Autenticación contra Active Directory (LDAP)."""
import logging
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturoVencido

import ldap3
from ldap3.utils.conv import escape_filter_chars

from config import load_config

log = logging.getLogger(__name__)


class AuthError(Exception):
    pass


# Límite total para hablar con AD: si el directorio no responde, el login no puede quedarse colgado.
LIMITE_AD_S = 20
_pool_ad = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ldap")


def _con_limite(funcion, *args):
    futuro = _pool_ad.submit(funcion, *args)
    try:
        return futuro.result(timeout=LIMITE_AD_S)
    except FuturoVencido:
        log.error("El directorio activo no respondió en %s s (%s)", LIMITE_AD_S, funcion.__name__)
        raise AuthError(f"El directorio activo ({load_config()['LdapServer']}) no respondió en {LIMITE_AD_S} segundos. "
                        "Verifica en Ajustes > Acceso el servidor LDAP o inténtalo de nuevo.")


# Credenciales de AD de los administradores con sesión abierta, SOLO en memoria (nunca en disco):
# permiten consultar el directorio al agregar usuarios. Se borran al cerrar sesión o reiniciar el servicio.
_SESION_AD_S = 8 * 3600
_sesiones_ad = {}
_lock_ad = threading.Lock()

ATRIBUTOS = ["sAMAccountName", "displayName", "mail", "title", "department", "userAccountControl"]
_DEMO = [
    {"usuario": "alvaro.pelaez", "nombre": "Álvaro Peláez", "correo": "alvaro.pelaez@confiar.coop",
     "cargo": "Analista de Infraestructura", "area": "Tecnología", "activo": True},
    {"usuario": "sandra.sanchez", "nombre": "Sandra Sánchez", "correo": "sandra.sanchez@confiar.coop",
     "cargo": "Coordinadora de Desarrollo", "area": "Tecnología", "activo": True},
    {"usuario": "op.pruebas", "nombre": "Operador de Pruebas", "correo": "", "cargo": "", "area": "", "activo": False},
]


def recordar_sesion(login, clave):
    token = secrets.token_hex(16)
    with _lock_ad:
        ahora = time.time()
        for t in [t for t, v in _sesiones_ad.items() if v[2] < ahora]:
            del _sesiones_ad[t]
        _sesiones_ad[token] = (login, clave, ahora + _SESION_AD_S)
    return token


def olvidar_sesion(token):
    with _lock_ad:
        _sesiones_ad.pop(token, None)


def normalizar_usuario(usuario):
    return usuario.strip().split("\\")[-1].split("@")[0]


def autenticar(usuario, clave):
    """Valida las credenciales en AD. Devuelve dict {usuario, nombre, correo}. Lanza AuthError."""
    cfg = load_config()
    if not usuario or not clave:
        raise AuthError("Ingresa usuario y contraseña.")

    # Modo pruebas: solo si está habilitado explícitamente en config.json
    if cfg.get("ModoPruebas") and usuario == "admin" and clave == "admin":
        return {"usuario": "admin.pruebas", "nombre": "Administrador (pruebas)", "correo": "", "login": None}

    login = usuario if ("\\" in usuario or "@" in usuario) else f"{cfg['LdapDominio']}\\{usuario}"
    return _con_limite(_autenticar_ad, cfg, login, clave)


def _autenticar_ad(cfg, login, clave):
    corto = normalizar_usuario(login)
    server, conn = _conectar(cfg, login, clave)

    nombre, correo = corto, ""
    try:
        base = server.info.other["defaultNamingContext"][0]
        conn.search(base, f"(sAMAccountName={escape_filter_chars(corto)})",
                    attributes=["displayName", "mail"])
        if conn.entries:
            nombre = str(conn.entries[0].displayName) if conn.entries[0].displayName else corto
            correo = str(conn.entries[0].mail) if conn.entries[0].mail else ""
    except Exception:
        log.warning("No se pudo leer el nombre del usuario %s en AD", corto)
    finally:
        conn.unbind()
    log.info("Login AD de %s completado", corto)
    return {"usuario": corto, "nombre": nombre, "correo": correo, "login": login}


def _conectar(cfg, login, clave):
    servidor = cfg["LdapServer"]
    inicio = time.monotonic()
    log.info("Conectando con LDAP %s como %s...", servidor, login)
    try:
        # get_info=DSA lee solo el rootDSE (defaultNamingContext). ALL descargaba el esquema completo de AD,
        # que en redes lentas puede tardar muchísimo.
        server = ldap3.Server(servidor, get_info=ldap3.DSA, connect_timeout=5)
        conn = ldap3.Connection(server, user=login, password=clave, auto_bind=True, receive_timeout=10)
        log.info("LDAP %s: autenticado en %.1f s", servidor, time.monotonic() - inicio)
        return server, conn
    except ldap3.core.exceptions.LDAPBindError:
        log.info("LDAP %s: credenciales rechazadas para %s (%.1f s)", servidor, login, time.monotonic() - inicio)
        raise AuthError("Usuario o contraseña incorrectos.")
    except Exception as exc:
        log.exception("Fallo conectando con LDAP %s tras %.1f s", servidor, time.monotonic() - inicio)
        raise AuthError(f"No fue posible conectar con el directorio ({servidor}): {exc}")


def _texto(entrada, atributo):
    valor = getattr(entrada, atributo, None)
    return str(valor) if valor is not None and valor.value is not None else ""


def buscar(termino, token, demo=False, limite=10):
    """Busca usuarios en AD por usuario de red, nombre o correo. Devuelve lista de dicts. Lanza AuthError."""
    termino = normalizar_usuario(termino or "")
    if len(termino) < 2:
        return []
    cfg = load_config()
    if demo and cfg.get("ModoPruebas"):  # usuario de pruebas: datos de ejemplo, sin conectarse a AD
        t = termino.lower()
        return [u for u in _DEMO if t in u["usuario"] or t in u["nombre"].lower()][:limite]

    with _lock_ad:
        sesion = _sesiones_ad.get(token)
    if not sesion or sesion[2] < time.time():
        raise AuthError("Para consultar el Directorio Activo vuelve a iniciar sesión (la sesión del servicio se reinició).")
    return _con_limite(_buscar_ad, cfg, sesion, termino, limite)


def _buscar_ad(cfg, sesion, termino, limite):
    server, conn = _conectar(cfg, sesion[0], sesion[1])
    t = escape_filter_chars(termino)
    filtro = (f"(&(objectCategory=person)(objectClass=user)"
              f"(|(sAMAccountName={t}*)(displayName=*{t}*)(mail={t}*)))")
    try:
        base = server.info.other["defaultNamingContext"][0]
        conn.search(base, filtro, attributes=ATRIBUTOS, size_limit=limite)
        resultado = []
        for e in conn.entries:
            uac = e.userAccountControl.value if e.userAccountControl.value is not None else 0
            resultado.append({
                "usuario": _texto(e, "sAMAccountName"), "nombre": _texto(e, "displayName") or _texto(e, "sAMAccountName"),
                "correo": _texto(e, "mail"), "cargo": _texto(e, "title"), "area": _texto(e, "department"),
                "activo": not (int(uac) & 2),  # bit ACCOUNTDISABLE
            })
        return sorted(resultado, key=lambda u: u["usuario"].lower())
    except Exception as exc:
        log.exception("Fallo buscando '%s' en AD", termino)
        raise AuthError(f"No se pudo consultar el Directorio Activo: {exc}")
    finally:
        conn.unbind()
