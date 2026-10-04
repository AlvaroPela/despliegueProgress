"""Administración: usuarios, configuración y perfil."""
import logging

from flask import Blueprint, jsonify, render_template, request, session

import config
from routes.helpers import login_required, rol_requerido
from services import credentials, mailer, users

log = logging.getLogger(__name__)
bp = Blueprint("admin", __name__)

ADMIN = ("Administrador",)


def _ok(**extra):
    return jsonify({"status": "success", **extra})


def _error(mensaje, codigo=400):
    return jsonify({"status": "error", "message": mensaje}), codigo


# ---------------------------------------------------------------- Usuarios
@bp.route("/usuarios")
@rol_requerido(*ADMIN)
def usuarios():
    return render_template("usuarios.html", lista=users.listar(), roles=users.ROLES)


@bp.route("/api/usuarios", methods=["POST"])
@rol_requerido(*ADMIN)
def agregar_usuario():
    d = request.get_json(silent=True) or {}
    try:
        users.agregar(d.get("usuario"), d.get("nombre"), d.get("rol", "Operador"), d.get("estado", "Activo"))
    except ValueError as exc:
        return _error(str(exc))
    return _ok()


@bp.route("/api/usuarios/<int:user_id>", methods=["PUT", "DELETE"])
@rol_requerido(*ADMIN)
def modificar_usuario(user_id):
    try:
        if request.method == "DELETE":
            users.eliminar(user_id)
        else:
            d = request.get_json(silent=True) or {}
            users.actualizar(user_id, rol=d.get("rol"), estado=d.get("estado"))
    except ValueError as exc:
        return _error(str(exc), 404)
    return _ok()


# ----------------------------------------------------------- Configuración
@bp.route("/configuracion")
@rol_requerido(*ADMIN)
def configuracion():
    try:
        cfg = config.load_config()
        servidores = config.load_servidores()
    except ValueError as exc:
        return render_template("error.html", titulo="Error de configuración", mensaje=str(exc)), 500
    return render_template("configuracion.html", cfg=cfg, servidores=servidores,
                           smtp_secret=credentials.existe("Smtp"))


def _lineas(texto):
    return [l.strip() for l in (texto or "").replace(",", "\n").splitlines() if l.strip()]


@bp.route("/api/configuracion", methods=["POST"])
@rol_requerido(*ADMIN)
def guardar_configuracion():
    d = request.get_json(silent=True) or {}
    try:
        cambios = {
            "RutaOrigen": d["ruta_origen"].strip(), "RutaBaseY": d["ruta_base_y"].strip(),
            "RutaBaseN": d["ruta_base_n"].strip(), "RutaRutinasN": d["ruta_rutinas_n"].strip(),
            "RutaCompilados": d["ruta_compilados"].strip(), "RutaBackup": d["ruta_backup"].strip(),
            "ProgressExe": d["progress_exe"].strip(), "ProgressIni": d["progress_ini"].strip(),
            "DbHost": d["db_host"].strip(),
            "DbPuertoDatos": int(d["db_puerto_datos"]), "DbPuertoSeguimiento": int(d["db_puerto_seguimiento"]),
            "TimeoutCompilacion": int(d["timeout_compilacion"]),
            "UsuarioSmtp": d["usuario_smtp"].strip(), "ServidorSmtp": d["servidor_smtp"].strip(),
            "PuertoSmtp": int(d["puerto_smtp"]), "Destinatario": _lineas(d.get("destinatarios")),
            "Auth_ClientID": d["auth_client_id"].strip(), "Auth_Tenant": d["auth_tenant"].strip(),
            "LdapServer": d["ldap_server"].strip(), "LdapDominio": d["ldap_dominio"].strip(),
            "RestringirAUsuarios": bool(d.get("restringir_usuarios")),
            "RutinasEspeciales": _lineas(d.get("rutinas_especiales")),
        }
        if not cambios["RutaOrigen"] or not cambios["ProgressExe"]:
            return _error("La ruta de origen y el ejecutable de Progress son obligatorios.")
        config.save_config(cambios)
        config.save_servidores(_lineas(d.get("servidores_dg")), _lineas(d.get("servidores_oficinas")))
    except (KeyError, ValueError) as exc:
        return _error(f"Datos inválidos: {exc}")
    log.info("Configuración actualizada por %s", session["usuario"])
    return _ok()


@bp.route("/api/smtp/secret", methods=["POST"])
@rol_requerido(*ADMIN)
def guardar_secret_smtp():
    secreto = (request.get_json(silent=True) or {}).get("secret", "").strip()
    client_id = config.load_config()["Auth_ClientID"]
    if not secreto:
        return _error("Ingresa el Client Secret.")
    if not client_id:
        return _error("Primero guarda el Client ID en la configuración de correo.")
    try:
        credentials.guardar("Smtp", client_id, secreto)
    except RuntimeError as exc:
        return _error(str(exc), 500)
    return _ok()


@bp.route("/api/smtp/probar", methods=["POST"])
@rol_requerido(*ADMIN)
def probar_smtp():
    try:
        mailer.probar_conexion()
    except mailer.MailError as exc:
        return _error(str(exc))
    return _ok(message="Autenticación OAuth 2.0 correcta con Office 365.")


# ------------------------------------------------------------------ Perfil
@bp.route("/perfil")
@login_required
def perfil():
    bases = [{"id": b, "usuario": credentials.usuario_de(b), "configurada": credentials.existe(b)}
             for b in credentials.BASES_BD]
    return render_template("perfil.html", bases=bases, db_configurada=credentials.bd_configurada(),
                           carpeta=credentials.CRED_DIR)


@bp.route("/api/credenciales/bd", methods=["POST"])
@login_required
def guardar_credenciales_bd():
    d = request.get_json(silent=True) or {}
    base = d.get("base") or ""
    usuario, clave = (d.get("db_user") or "").strip(), d.get("db_pass") or ""
    if base not in credentials.BASES_BD:
        return _error("Base de datos no válida.")
    if not usuario or not clave:
        return _error("Usuario y contraseña son obligatorios.")
    try:
        credentials.guardar_bd(base, usuario, clave)
    except RuntimeError as exc:
        return _error(str(exc), 500)
    log.info("Credenciales de la BD %s actualizadas por %s", base, session["usuario"])
    return _ok()
