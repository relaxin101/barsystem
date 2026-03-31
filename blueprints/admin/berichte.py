"""export/report blueprint in admin panel"""

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required
from sqlalchemy import text

from models import db, Bericht
from utils.admin import *

export_bp = Blueprint("export", __name__, url_prefix="/export")

# --------------------------------
# 📦 Admin-Seite: Export Auswahl
# --------------------------------
@export_bp.route("/", methods=["GET", "POST"])
@login_required
def admin_export():
    """
    Admin-Interface für eigene SQL Queries.
    Query wird readonly ausgeführt, Ergebnis als Tabelle angezeigt und kann als Excel exportiert werden.
    """
    results = None
    query = ""
    error = None

    bericht_id = request.args.get("id", "").strip()
    if bericht_id:
        query = Bericht.query.get_or_404(bericht_id).sql

    if request.method == "POST":
        query = request.form.get("query", "").strip()

    if query:
        try:
            # Reine Lese-Verbindung
            readonly_engine = db.get_engine()
            with readonly_engine.connect() as conn:
                conn = conn.execution_options(
                    isolation_level="AUTOCOMMIT",  # SQL-injection as a Service (SaaS)
                )
                result_proxy = conn.execute(text(query))
                # Spalten + Daten für Template
                columns = result_proxy.keys()
                results = [dict(zip(columns, row)) for row in result_proxy.fetchall()]

        except Exception as e:
            error = str(e.args)

    berichte = [
        {
            "id": bericht.id,
            "name": bericht.name,
            "sql": bericht.sql,
        }
        for bericht in Bericht.query.all()
    ]
    return render_template(
        "admin/admin_export.html",
        id=bericht_id,
        query=query,
        results=results,
        error=error,
        berichte=berichte,
    )


@login_required
@export_bp.route("/export/berichte", methods=["POST"])
def create_berichte():
    query = request.form.get("query", "").strip()
    if not query:
        flash("Es muss eine Query angegeben werden", "error")
        return redirect(url_for("admin.export.admin_export"))

    name = request.form.get("name", "").strip()

    if not name:
        flash("Es muss ein Name angegeben werden", "error")
        return redirect(url_for("admin.export.admin_export"))
    bericht = Bericht(sql=query, name=name)
    db.session.add(bericht)
    db.session.commit()
    return redirect(url_for("admin.export.admin_export"))


@export_bp.route("/berichte/<int:bericht_id>", methods=["POST"])
@login_required
def delete_berichte(bericht_id):
    if request.form.get("_method") == "DELETE":
        bericht = Bericht.query.get_or_404(bericht_id)
        db.session.delete(bericht)
        db.session.commit()
        flash(f"Bericht '{bericht.name}' wurde gelöscht.", "success")
    return redirect(url_for("admin.export.admin_export"))

@export_bp.route("/download", methods=["POST"])
@login_required
def download():
    query = request.form.get("query", "").strip()

    readonly_engine = db.get_engine()
    with readonly_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT", readonly=True)
        result_proxy = conn.execute(text(query))
        df = pd.DataFrame(result_proxy.fetchall(), columns=result_proxy.keys())

    return export_df_to_excel(df, "export.xlsx")

