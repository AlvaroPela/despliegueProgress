"""Decoradores de autenticación y autorización."""
from functools import wraps

from flask import jsonify, redirect, request, session, url_for


def _es_api():
    return request.path.startswith("/api/") or request.method != "GET"


def login_required(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if "usuario" not in session:
            if _es_api():
                return jsonify({"status": "error", "message": "Sesión expirada. Vuelve a iniciar sesión."}), 401
            return redirect(url_for("auth.login", next=request.path))
        return vista(*args, **kwargs)
    return envoltura


def rol_requerido(*roles):
    def decorador(vista):
        @wraps(vista)
        @login_required
        def envoltura(*args, **kwargs):
            if session.get("rol") not in roles:
                if _es_api():
                    return jsonify({"status": "error", "message": "No tienes permisos para esta acción."}), 403
                return redirect(url_for("main.menu"))
            return vista(*args, **kwargs)
        return envoltura
    return decorador
