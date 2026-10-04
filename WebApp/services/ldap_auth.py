"""Autenticación contra Active Directory (LDAP)."""
import logging

import ldap3

from config import load_config

log = logging.getLogger(__name__)


class AuthError(Exception):
    pass


def normalizar_usuario(usuario):
    return usuario.strip().split("\\")[-1].split("@")[0]


def autenticar(usuario, clave):
    """Valida las credenciales en AD. Devuelve dict {usuario, nombre, correo}. Lanza AuthError."""
    cfg = load_config()
    if not usuario or not clave:
        raise AuthError("Ingresa usuario y contraseña.")

    # Modo pruebas: solo si está habilitado explícitamente en config.json
    if cfg.get("ModoPruebas") and usuario == "admin" and clave == "admin":
        return {"usuario": "admin.pruebas", "nombre": "Administrador (pruebas)", "correo": ""}

    servidor = cfg["LdapServer"]
    login = usuario if ("\\" in usuario or "@" in usuario) else f"{cfg['LdapDominio']}\\{usuario}"
    corto = normalizar_usuario(usuario)
    try:
        server = ldap3.Server(servidor, get_info=ldap3.ALL, connect_timeout=4)
        conn = ldap3.Connection(server, user=login, password=clave, auto_bind=True, receive_timeout=6)
    except ldap3.core.exceptions.LDAPBindError:
        raise AuthError("Usuario o contraseña incorrectos.")
    except Exception as exc:
        log.exception("Fallo conectando con LDAP %s", servidor)
        raise AuthError(f"No fue posible conectar con el directorio ({servidor}): {exc}")

    nombre, correo = corto, ""
    try:
        base = server.info.other["defaultNamingContext"][0]
        conn.search(base, f"(sAMAccountName={ldap3.utils.conv.escape_filter_chars(corto)})",
                    attributes=["displayName", "mail"])
        if conn.entries:
            nombre = str(conn.entries[0].displayName) if conn.entries[0].displayName else corto
            correo = str(conn.entries[0].mail) if conn.entries[0].mail else ""
    except Exception:
        log.warning("No se pudo leer el nombre del usuario %s en AD", corto)
    finally:
        conn.unbind()
    return {"usuario": corto, "nombre": nombre, "correo": correo}
