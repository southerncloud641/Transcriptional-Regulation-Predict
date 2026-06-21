import os
from typing import Dict, List

from flask import Flask, flash, redirect, render_template, request, url_for

from json_sqlite_store import (
    DB_PATH, JSON_PATH, connect_db, ensure_database, init_db, rebuild_database,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "foodie-flask-secret-key")
app.config["JSON_PATH"] = JSON_PATH
app.config["DB_PATH"] = DB_PATH
app.config["PAGE_SIZE"] = 20



def build_filters(args: Dict[str, str]) -> tuple[str, List[str]]:
    conditions = []
    params: List[str] = []

    mapping = {
        "transcription_factor": "transcription_factor",
        "target_gene": "target_gene",
        "pdf_file": "pdf_file",
        "confidence": "confidence",
        "regulation_type": "regulation_type",
    }

    for key, column in mapping.items():
        value = (args.get(key) or "").strip()
        if value:
            if key in {"transcription_factor", "target_gene", "pdf_file"}:
                conditions.append(f"LOWER({column}) LIKE LOWER(?)")
                params.append(f"%{value}%")
            else:
                conditions.append(f"LOWER({column}) = LOWER(?)")
                params.append(value)

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    return where_clause, params


@app.route("/")
def index():
    ensure_database()
    query_args = {
        "transcription_factor": request.args.get("transcription_factor", ""),
        "target_gene": request.args.get("target_gene", ""),
        "pdf_file": request.args.get("pdf_file", ""),
        "confidence": request.args.get("confidence", ""),
        "regulation_type": request.args.get("regulation_type", ""),
    }

    if not DB_PATH.exists():
        return render_template(
            "index.html",
            rows=[],
            stats={"documents": 0, "relations": 0, "unique_tfs": 0, "unique_targets": 0},
            query_args=query_args,
            db_ready=False,
            message="尚未生成数据库，请先运行 JSON 提取流程。",
        )

    where_clause, params = build_filters(query_args)
    page = max(int(request.args.get("page", 1)), 1)
    page_size = app.config["PAGE_SIZE"]
    offset = (page - 1) * page_size

    conn = connect_db()
    try:
        init_db(conn)
        stats = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM documents) AS documents,
                (SELECT COUNT(*) FROM relations) AS relations,
                (SELECT COUNT(DISTINCT transcription_factor) FROM relations
                 WHERE transcription_factor IS NOT NULL AND transcription_factor != '' AND LOWER(transcription_factor) != 'unknown') AS unique_tfs,
                (SELECT COUNT(DISTINCT target_gene) FROM relations
                 WHERE target_gene IS NOT NULL AND target_gene != '' AND LOWER(target_gene) != 'unknown') AS unique_targets
            """
        ).fetchone()

        total_rows = conn.execute(
            f"SELECT COUNT(*) AS count FROM relations WHERE {where_clause}",
            params,
        ).fetchone()["count"]

        rows = conn.execute(
            f"""
            SELECT
                pdf_file,
                transcription_factor,
                target_gene,
                regulation_type,
                evidence_type,
                biological_context,
                auxiliary_proteins,
                confidence,
                location
            FROM relations
            WHERE {where_clause}
            ORDER BY pdf_file ASC, relation_index ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

        total_pages = max((total_rows + page_size - 1) // page_size, 1) if total_rows else 1
        return render_template(
            "index.html",
            rows=rows,
            stats={
                "documents": stats["documents"],
                "relations": stats["relations"],
                "unique_tfs": stats["unique_tfs"],
                "unique_targets": stats["unique_targets"],
            },
            query_args=query_args,
            db_ready=True,
            total_rows=total_rows,
            page=page,
            total_pages=total_pages,
            has_prev=page > 1,
            has_next=page < total_pages,
            prev_page=page - 1,
            next_page=page + 1,
            message=next((msg for msg in get_flashed_messages()), ""),
        )
    finally:
        conn.close()


@app.post("/reload")
def reload_database():
    if not JSON_PATH.exists():
        flash(f"找不到 JSON 文件：{JSON_PATH}")
        return redirect(url_for("index"))

    counts = rebuild_database()
    flash(f"数据库已重建：{counts['documents']} 篇文献，{counts['relations']} 条关系。")
    return redirect(url_for("index"))


from flask import get_flashed_messages  # noqa: E402


if __name__ == "__main__":
    ensure_database()
    app.run(host="0.0.0.0", port=5000, debug=True)
