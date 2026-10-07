"""
amedas.duckdb に SQL を投げる小さなヘルパー。

使い方:
  python scripts/query.py "select * from marts.rankings_latest_day limit 5"
  python scripts/query.py            # 引数なしで対話モード(exit で終了)
"""
import sys
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "amedas.duckdb"


def main() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    if len(sys.argv) > 1:
        print(con.sql(" ".join(sys.argv[1:])))
        return
    print(f"connected: {DB_PATH} (read_only)  -- 'exit' で終了")
    while True:
        try:
            sql = input("duckdb> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if sql.lower() in ("exit", "quit", ""):
            if sql:
                break
            continue
        try:
            print(con.sql(sql))
        except Exception as e:  # noqa: BLE001
            print(f"error: {e}")


if __name__ == "__main__":
    main()
