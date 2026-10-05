"""Nuevo despliegue, progreso y logs."""
import html
import json
import logging
import os
import threading

from flask import Blueprint, Response, jsonify, render_template, request, session

from config import LOG_DIR
from routes.helpers import login_required, rol_requerido
from services import credentials, deployer, history, mailer, versions
from services.excel import ArchivoBloqueado

log = logging.getLogger(__name__)
bp = Blueprint("deploy", __name__)


@bp.route("/nuevo_despliegue")
@rol_requerido("Administrador", "Operador")
def nuevo_despliegue():
    return render_template("deploy.html", db_configured=credentials.bd_configurada(),
                           en_curso=deployer.despliegue_en_curso())


@bp.route("/api/check_versions", methods=["POST"])
@rol_requerido("Administrador", "Operador")
def check_versions():
    resultado = []
    for f in request.files.getlist("archivos_prin"):
        if f and f.filename:
            resultado.append({"archivo": os.path.basename(f.filename), "version": versions.desde_bytes(f.read())})
    return jsonify({"status": "success", "versiones": resultado})


@bp.route("/desplegar", methods=["POST"])
@rol_requerido("Administrador", "Operador")
def desplegar():
    form = request.form
    if not credentials.bd_configurada():
        return jsonify({"status": "error", "message": "Configura primero las credenciales de la base de datos (Perfil)."}), 400
    try:
        reg_id = deployer.iniciar(
            usuario=session["usuario"],  # nunca se confía en el usuario enviado por el formulario
            caso=form.get("caso", ""), destino=form.get("destino", ""), ips=form.get("ips", ""),
            actualizar=form.get("actualizar", "N"), ruta_mb=form.get("ruta_mb", "").strip(),
            archivos_prin=request.files.getlist("archivos_prin"),
            archivos_inc=request.files.getlist("archivos_inc"),
        )
    except deployer.DeployBusy as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except ArchivoBloqueado as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503
    except Exception as exc:
        log.exception("No se pudo iniciar el despliegue")
        return jsonify({"status": "error", "message": f"No se pudo iniciar: {exc}"}), 500
    return jsonify({"status": "success", "id": reg_id})


@bp.route("/api/progreso/<int:reg_id>")
@login_required
def progreso(reg_id):
    ruta = os.path.join(LOG_DIR, f"progreso_{reg_id}.json")
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except (OSError, json.JSONDecodeError):
        return jsonify({"step": 0, "step_name": "Esperando...", "details": "", "status": "running"})


@bp.route("/api/log/<int:reg_id>")
@login_required
def ver_log(reg_id):
    """El nombre del archivo se obtiene del historial: el cliente nunca envía rutas."""
    registro = next((r for r in history.listar() if str(r["ID"]) == str(reg_id)), None)
    nombre = os.path.basename(str(registro["Log_File"])) if registro else ""
    ruta = os.path.join(LOG_DIR, nombre) if nombre else ""
    if not ruta or not os.path.isfile(ruta):
        return Response("No hay log disponible para este despliegue.", mimetype="text/plain; charset=utf-8", status=404)
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        return Response(f.read(), mimetype="text/plain; charset=utf-8")


@bp.route("/api/despliegues/<int:reg_id>/version-escala", methods=["POST"])
@rol_requerido("Administrador", "Operador")
def confirmar_version_escala(reg_id):
    """Confirma que las versiones del despliegue ya se actualizaron a mano en Escala."""
    try:
        registro = history.confirmar_version(reg_id, session["usuario"])
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    log.info("Versiones del caso %s confirmadas en Escala por %s", registro["Caso"], session["usuario"])
    threading.Thread(target=_avisar_confirmacion, args=(registro,), daemon=True).start()
    return jsonify({"status": "success", "por": registro["Version_Confirmada_Por"], "en": registro["Version_Confirmada_En"]})


def _avisar_confirmacion(registro):
    filas = "".join(f"<li>{html.escape(v['programa'])} &mdash; v{html.escape(v['version'])}</li>"
                    for v in registro["ListaVersiones"])
    cuerpo = (f"<div style='font-family:Segoe UI,Arial,sans-serif'><h3 style='color:#2e7d32'>Versiones actualizadas en Escala</h3>"
              f"<p>Caso <b>{html.escape(str(registro['Caso']))}</b> ({html.escape(str(registro['Destino']))}). "
              f"Confirmado por <b>{html.escape(str(registro['Version_Confirmada_Por']))}</b> el {registro['Version_Confirmada_En']}.</p>"
              f"<ul>{filas}</ul></div>")
    try:
        mailer.enviar(f"[Versión confirmada] Despliegue caso {registro['Caso']}", cuerpo)
    except Exception as exc:
        log.warning("No se envió el correo de confirmación de versión: %s", exc)
