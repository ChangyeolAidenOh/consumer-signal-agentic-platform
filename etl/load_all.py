"""
ETL loader — H&S pipeline CSV files to PostgreSQL.

Usage:
    docker-compose up -d
    python etl/load_all.py --data-dir ~/PycharmProjects/pg_hns_project
"""

import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


DB_URL = "postgresql://hns_user:hns_local_dev_only@localhost:5433/hns_platform"

# (relative CSV path, target table name)
LOAD_MAP = [
    ("voc_pipeline/data/processed/hns_causal_signals.csv",          "voc_documents"),
    ("voc_pipeline/data/processed/hns_temporal_signals.csv",        "temporal_signals"),
    ("voc_pipeline/data/processed/hns_lda_results.csv",             "lda_topics"),
    ("voc_pipeline/data/processed/hns_bertopic_documents.csv",      "bertopic_documents"),
    ("voc_pipeline/data/processed/hns_lda_bertopic_consensus.csv",  "lda_bertopic_consensus"),
    ("trend_pipeline/data/processed/trend_features.csv",            "trend_monthly"),
    ("trend_pipeline/data/processed/chronos_forecast.csv",          "chronos_forecast"),
    ("switching_pipeline/data/switching_prob_regression.csv",        "segment_summary"),
    ("switching_pipeline/data/switching_implications.csv",           "switching_implications"),
    ("switching_pipeline/data/timeline_analysis.csv",                "timeline_analysis"),
]


def load_csv_to_table(engine, csv_path: Path, table_name: str) -> int:
    """Read a CSV and insert rows into the target PostgreSQL table."""
    if not csv_path.exists():
        print(f"  skip (not found): {csv_path.name}")
        return 0

    df = pd.read_csv(csv_path)
    df.to_sql(table_name, engine, if_exists="append", index=False)
    print(f"  {table_name}: {len(df)} rows")
    return len(df)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()

    base = Path(args.data_dir)
    if not base.exists():
        print(f"directory not found: {base}")
        return

    engine = create_engine(DB_URL)

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("connected to PostgreSQL\n")

    total = 0
    for rel_path, table_name in LOAD_MAP:
        total += load_csv_to_table(engine, base / rel_path, table_name)

    print(f"\ntotal: {total} rows loaded")


if __name__ == "__main__":
    main()
