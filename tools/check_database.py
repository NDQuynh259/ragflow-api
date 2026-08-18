import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.storage.database.postgres import check_database_ready, engine


def main():
    check_database_ready()

    with engine.connect() as connection:
        extension = connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar()
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        indexes = connection.execute(text("""
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename IN ('documents', 'document_nodes')
            ORDER BY tablename, indexname
        """)).fetchall()

    print(f"extension: {extension}")
    print(f"revision: {revision}")
    print("indexes:")
    for row in indexes:
        print(f"  {row.tablename}: {row.indexname}")

    actual_indexes = {row.indexname for row in indexes}
    required_indexes = {
        "ix_document_nodes_document_id",
        "ix_document_nodes_embedding_hnsw",
        "ix_document_nodes_fts_simple",
    }
    missing_indexes = required_indexes - actual_indexes
    if missing_indexes:
        raise RuntimeError(
            f"Database is missing required indexes: {sorted(missing_indexes)}"
        )
    print("database readiness: OK")


if __name__ == "__main__":
    main()
