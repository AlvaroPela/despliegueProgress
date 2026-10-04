"""Inicio y cierre de sesión."""
import logging
import time

from flask import Blueprint, redirect, render_template, request, session, url_for

from config import load_config
from services import ldap_auth, users

log = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)

_intentos = {}  # ip -> [timestamps]
MAX_INTENTOS = 6
VENTANA_S = 300


def _bloqueado(ip):
    ahora = time.time()
    recientes = [t for t in _intentos.get(ip, []) if ahora - t < VENTANA_S]
    _intentos[ip] = recientes
    return len(recientes) >= MAX_INTENTOS


def _rol_y_acceso(usuario, cfg):
    """Devuelve el rol del usuario o None si no tiene acceso."""
    lista = users.listar()
    registro = next((u for u in lista if str(u["Usuario"]).lower() == usuario.lower()), None)
    if registro:
        return registro["Rol"] if str(registro["Estado"]).lower() == "activo" else None
    return None if cfg.get("RestringirAUsuarios") else "Administrador"


@bp.route("/", methods=["GET", "POST"])
def login():
    if "usuario" in session and request.method == "GET":
        return redirect(url_for("main.menu"))
    if request.method == "GET":
        return render_template("login.html")

    ip = request.remote_addr or "?"
    if _bloqueado(ip):
        return render_template("login.html", error="Demasiados intentos fallidos. Espera unos minutos."), 429
    try:
        cfg = load_config()
        info = ldap_auth.autenticar(request.form.get("username", "").strip(), request.form.get("password", ""))
        rol = _rol_y_acceso(info["usuario"], cfg)
        if rol is None:
            raise ldap_auth.AuthError("Tu usuario no está autorizado. Solicita acceso a un administrador.")
    except ldap_auth.AuthError as exc:
        _intentos.setdefault(ip, []).append(time.time())
        log.warning("Login fallido de %s desde %s: %s", request.form.get("username"), ip, exc)
        return render_template("login.html", error=str(exc)), 401

    _intentos.pop(ip, None)
    session.clear()
    session.permanent = True
    session.update(usuario=info["usuario"], nombre=info["nombre"], rol=rol)
    log.info("Login: %s (%s)", info["usuario"], rol)
    destino = request.args.get("next", "")
    return redirect(destino if destino.startswith("/") and not destino.startswith("//") else url_for("main.menu"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
