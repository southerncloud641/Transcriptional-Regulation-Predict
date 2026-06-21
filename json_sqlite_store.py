import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
PDF_DIR = BASE_DIR / "实例文献"
JSON_PATH = PDF_DIR / "extraction_results_v4.json"
DB_PATH = BASE_DIR / "extraction.sqlite3"


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def to_text(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    return text if text else "unknown"


def normalize_auxiliary_proteins(value: Any) -> str:
    if value in (None, "", [], {}):
        return "unknown"
    return to_text(value)


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_file TEXT NOT NULL UNIQUE,
            pdf_path TEXT,
            status TEXT,
            relation_count INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            pdf_file TEXT NOT NULL,
            pdf_path TEXT,
            status TEXT,
            relation_index INTEGER,
            transcription_factor TEXT,
            target_gene TEXT,
            regulation_type TEXT,
            evidence_type TEXT,
            biological_context TEXT,
            auxiliary_proteins TEXT,
            confidence TEXT,
            location TEXT,
            raw_json TEXT,
            FOREIGN KEY(document_id) REFERENCES documents(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_tf ON relations(transcription_factor)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_target ON relations(target_gene)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_pdf ON relations(pdf_file)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rel_confidence ON relations(confidence)")


def load_json_payload(json_path: Path = JSON_PATH) -> List[Dict[str, Any]]:
    if not json_path.exists():
        raise FileNotFoundError(f"找不到JSON文件: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("JSON 根节点必须是列表")
    return data


def rebuild_database(json_path: Path = JSON_PATH, db_path: Path = DB_PATH) -> Dict[str, int]:
    payload = load_json_payload(json_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        init_db(conn)
        conn.execute("DELETE FROM relations")
        conn.execute("DELETE FROM documents")

        total_docs = 0
        total_relations = 0

        for item in payload:
            if not isinstance(item, dict):
                continue
            pdf_file = to_text(item.get("pdf_file"))
            pdf_path = to_text(item.get("pdf_path"))
            status = to_text(item.get("status"))
            relation_count = int(item.get("relation_count") or 0)

            cur = conn.execute(
                """
                INSERT INTO documents (pdf_file, pdf_path, status, relation_count)
                VALUES (?, ?, ?, ?)
                """,
                (pdf_file, pdf_path, status, relation_count),
            )
            document_id = cur.lastrowid
            total_docs += 1

            relations = item.get("relations") or []
            if not isinstance(relations, list):
                relations = []

            for index, rel in enumerate(relations, start=1):
                if not isinstance(rel, dict):
                    continue
                conn.execute(
                    """
                    INSERT INTO relations (
                        document_id, pdf_file, pdf_path, status, relation_index,
                        transcription_factor, target_gene, regulation_type, evidence_type,
                        biological_context, auxiliary_proteins, confidence, location, raw_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        pdf_file,
                        pdf_path,
                        status,
                        index,
                        to_text(rel.get("transcription_factor")),
                        to_text(rel.get("target_gene")),
                        to_text(rel.get("regulation_type")),
                        to_text(rel.get("evidence_type")),
                        to_text(rel.get("biological_context")),
                        normalize_auxiliary_proteins(rel.get("auxiliary_proteins")),
                        to_text(rel.get("confidence")),
                        to_text(rel.get("location")),
                        json.dumps(rel, ensure_ascii=False),
                    ),
                )
                total_relations += 1

        conn.commit()
        return {"documents": total_docs, "relations": total_relations}
    finally:
        conn.close()


def database_needs_refresh(json_path: Path = JSON_PATH, db_path: Path = DB_PATH) -> bool:
    if not db_path.exists():
        return True
    if not json_path.exists():
        return False
    return json_path.stat().st_mtime > db_path.stat().st_mtime


def ensure_database(json_path: Path = JSON_PATH, db_path: Path = DB_PATH) -> None:
    if not json_path.exists():
        return
    if database_needs_refresh(json_path=json_path, db_path=db_path):
        rebuild_database(json_path=json_path, db_path=db_path)
