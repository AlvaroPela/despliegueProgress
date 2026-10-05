"""Dashboard, historial e informes."""
import io

import pandas as pd
from flask import Blueprint, Response, jsonify, render_template

from routes.helpers import login_required
from services import credentials, history, reports
from services.system import revisar_entorno

bp = Blueprint("main", __name__)


@bp.route("/menu")
@login_required
def menu():
    registros = history.listar()
    return render_template(
        "dashboard.html",
        stats=history.estadisticas(registros),
        ultimos=registros[:6],
        serie=reports.serie_diaria(registros),
        db_configured=credentials.bd_configurada(),
    )


@bp.route("/historial")
@login_required
def historial():
    registros = history.listar()
    return render_template("historial.html", registros=registros, stats=history.estadisticas(registros))


@bp.route("/informes")
@login_required
def informes():
    registros = history.listar()
    return render_template(
        "informes.html",
        stats=history.estadisticas(registros),
        promedio=reports.duracion_promedio(registros),
        mensual=reports.por_mes(registros),
        usuarios=reports.por_usuario(registros)[:10],
        estados=reports.por_estado(registros),
    )


@bp.route("/informes/exportar.csv")
@login_required
def exportar_csv():
    df = pd.DataFrame(history.listar()).drop(columns=["Clase"], errors="ignore")
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return Response(
        "\ufeff" + buffer.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=historial_despliegues.csv"},
    )


@bp.route("/api/entorno")
@login_required
def api_entorno():
    return jsonify(revisar_entorno())
