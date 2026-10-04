"""Sistema de Despliegues Progress - Confiar Coop (fábrica de la aplicación Flask)."""
import logging
import os
import secrets
from datetime import timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify, render_template, request, session

import config
from services import history

APP_VERSION = "2.0"


def _configurar_logging():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    handler = RotatingFileHandler(os.path.join(config.LOG_DIR, "app.log"), maxBytes=2_000_000,
                                  backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in raiz.handlers):
        raiz.addHandler(handler)
        raiz.addHandler(logging.StreamHandler())


def create_app():
    _configurar_logging()
    app = Flask(__name__)
    app.secret_key = config.get_secret_key()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=300 * 1024 * 1024,
    )

    try:
        config.limpiar_secretos_en_config()
        history.marcar_interrumpidos()
    except Exception:
        logging.getLogger(__name__).exception("Fallo en la inicialización")

    from routes import admin, auth, deploy, main
    for modulo in (auth, main, deploy, admin):
        app.register_blueprint(modulo.bp)

    @app.before_request
    def _preparar_sesion():
        if "embed" in request.args:  # ?embed=1 oculta la barra superior (iframe de ServiceDesk Plus)
            session["embed"] = request.args.get("embed") == "1"
        if request.method in ("POST", "PUT", "DELETE", "PATCH") and "usuario" in session:
            esperado = session.get("csrf")
            if not esperado or request.headers.get("X-CSRF-Token") != esperado:
                return jsonify({"status": "error", "message": "Token de seguridad inválido. Recarga la página."}), 400

    @app.context_processor
    def _contexto():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return {
            "sesion_usuario": session.get("usuario"),
            "sesion_nombre": session.get("nombre") or session.get("usuario"),
            "sesion_rol": session.get("rol"),
            "embed": session.get("embed", False),
            "csrf_token": session["csrf"],
            "app_version": APP_VERSION,
        }

    @app.errorhandler(404)
    def _no_encontrado(_):
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "Recurso no encontrado."}), 404
        return render_template("error.html", titulo="Página no encontrada",
                               mensaje="La dirección solicitada no existe."), 404

    @app.errorhandler(Exception)
    def _error_interno(exc):
        logging.getLogger(__name__).exception("Error no controlado en %s", request.path)
        if request.path.startswith("/api/") or request.method != "GET":
            return jsonify({"status": "error", "message": f"Error interno: {exc}"}), 500
        return render_template("error.html", titulo="Error interno",
                               mensaje="Ocurrió un error inesperado. Revisa logs/app.log."), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
