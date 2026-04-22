"""
CSV column inspector — prints column names, types, and sample values
for each H&S pipeline output file.

Usage:
    python etl/check_columns.py --data-dir /path/to/pg-hns-consumer-signal-pipeline
"""

import argparse
from pathlib import Path

import pandas as pd


FILES_TO_CHECK = [
    ("voc_pipeline/data/processed/hns_causal_signals.csv",    "voc_documents"),
    ("voc_pipeline/data/processed/hns_temporal_signals.csv",  "temporal_signals"),
    ("voc_pipeline/data/processed/hns_lda_results.csv",       "lda_topics"),
    ("voc_pipeline/data/processed/hns_bertopic_documents.csv","bertopic_documents"),
    ("voc_pipeline/data/processed/hns_lda_bertopic_consensus.csv", "lda_bertopic_consensus"),
    ("trend_pipeline/data/processed/trend_features.csv",      "trend_monthly"),
    ("trend_pipeline/data/processed/chronos_forecast.csv",    "chronos_forecast"),
    ("switching_pipeline/data/switching_prob_regression.csv",  "segment_summary / voc_documents"),
    ("switching_pipeline/data/switching_implications.csv",     "switching_implications"),
    ("switching_pipeline/data/timeline_analysis.csv",          "timeline_analysis"),
]


def check_file(filepath: Path, table_name: str) -> None:
    print(f"\n{'='*70}")
    print(f"file: {filepath.name}")
    print(f"table: {table_name}")
    print(f"path: {filepath}")
    print(f"{'='*70}")

    if not filepath.exists():
        print("  not found")
        return

    try:
        df = pd.read_csv(filepath, nrows=5)
    except Exception as e:
        print(f"  read error: {e}")
        return

    total_rows = len(pd.read_csv(filepath))

    print(f"  rows: {total_rows}")
    print(f"  columns: {len(df.columns)}")
    print()
    print(f"  {'column':<35} {'dtype':<15} {'sample'}")
    print(f"  {'-'*35} {'-'*15} {'-'*30}")

    for col in df.columns:
        sample = str(df[col].iloc[0]) if not df[col].isna().all() else "NaN"
        if len(sample) > 30:
            sample = sample[:27] + "..."
        print(f"  {col:<35} {str(df[col].dtype):<15} {sample}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, required=True)
    args = parser.parse_args()

    base = Path(args.data_dir)
    if not base.exists():
        print(f"directory not found: {base}")
        return

    print("H&S Consumer Signal Pipeline - CSV column check")
    print(f"base directory: {base}")

    for rel_path, table_name in FILES_TO_CHECK:
        check_file(base / rel_path, table_name)


if __name__ == "__main__":
    main()
