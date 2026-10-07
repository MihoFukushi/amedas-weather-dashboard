"""気象庁 AMeDAS のオープンデータを取得して JSONL(gzip) に保存する抽出スクリプト。

- 観測地点マスタ: https://www.jma.go.jp/bosai/amedas/const/amedastable.json
- 時別観測値(全地点): https://www.jma.go.jp/bosai/amedas/data/map/YYYYMMDDHH0000.json

標準ライブラリのみで動く。すでに保存済みの時刻はスキップするので何度実行しても安全(冪等)。

使い方:
    python scripts/extract_amedas.py --days 3
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE_URL = "https://www.jma.go.jp/bosai/amedas"
USER_AGENT = "amedas-weather-dashboard (https://github.com/)"

# 取り込む観測要素。map JSON の値は [値, 品質フラグ] の配列で入っている。
ELEMENTS = {
    "temp": "temp",
    "humidity": "humidity",
    "precipitation1h": "precipitation1h",
    "precipitation24h": "precipitation24h",
    "wind": "wind",
    "windDirection": "wind_direction",
    "pressure": "pressure",
    "sun1h": "sun1h",
    "snow": "snow",
}


def fetch_json(url: str, retries: int = 3) -> dict | None:
    """URL から JSON を取得する。404 は None を返し、それ以外はリトライする。"""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(2 * (attempt + 1))
    return None


def dms_to_decimal(parts: list[float]) -> float:
    """[度, 分] 形式を十進度に変換する。"""
    return round(parts[0] + parts[1] / 60, 5)


def write_jsonl_gz(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def extract_stations(out_dir: Path) -> int:
    data = fetch_json(f"{BASE_URL}/const/amedastable.json")
    if data is None:
        raise RuntimeError("amedastable.json を取得できませんでした")
    rows = []
    for station_id, s in data.items():
        rows.append(
            {
                "station_id": station_id,
                "pref_code": station_id[:2],
                "station_type": s.get("type"),
                "name_kanji": s.get("kjName"),
                "name_kana": s.get("knName"),
                "name_en": s.get("enName"),
                "latitude": dms_to_decimal(s["lat"]),
                "longitude": dms_to_decimal(s["lon"]),
                "altitude_m": s.get("alt"),
                "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    write_jsonl_gz(out_dir / "stations.jsonl.gz", rows)
    return len(rows)


def flatten_observation(observed_at: str, station_id: str, obs: dict) -> dict:
    row: dict = {"observed_at": observed_at, "station_id": station_id}
    for src_key, dst_key in ELEMENTS.items():
        pair = obs.get(src_key)
        if isinstance(pair, list) and len(pair) == 2:
            row[dst_key] = pair[0]
            row[f"{dst_key}_qc"] = pair[1]
        else:
            row[dst_key] = None
            row[f"{dst_key}_qc"] = None
    return row


def latest_hour() -> datetime:
    req = urllib.request.Request(
        f"{BASE_URL}/data/latest_time.txt", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        text = res.read().decode("utf-8").strip()
    # 例: 2026-10-07T06:30:00+09:00 -> JST の naive datetime にして正時に丸める
    dt = datetime.fromisoformat(text).replace(tzinfo=None)
    return dt.replace(minute=0, second=0, microsecond=0)


def extract_observations(out_dir: Path, days: int, sleep_sec: float) -> tuple[int, int]:
    end = latest_hour()
    start = (end - timedelta(days=days)).replace(hour=0)
    fetched = skipped = 0
    current = start
    while current <= end:
        stamp = current.strftime("%Y%m%d%H%M%S")
        path = out_dir / "observations" / current.strftime("%Y%m%d") / f"{stamp}.jsonl.gz"
        if path.exists():
            skipped += 1
        else:
            data = fetch_json(f"{BASE_URL}/data/map/{stamp}.json")
            if data is None:
                print(f"  skip (not available): {stamp}")
            else:
                observed_at = current.strftime("%Y-%m-%d %H:%M:%S")
                rows = [
                    flatten_observation(observed_at, sid, obs) for sid, obs in data.items()
                ]
                write_jsonl_gz(path, rows)
                fetched += 1
                print(f"  fetched {stamp}: {len(rows)} stations")
            time.sleep(sleep_sec)
        current += timedelta(hours=1)
    return fetched, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=3, help="何日前から取得するか(最大10日程度)")
    parser.add_argument("--out", default="data/raw/amedas", help="出力ディレクトリ")
    parser.add_argument("--sleep", type=float, default=0.3, help="リクエスト間隔(秒)")
    args = parser.parse_args()

    out_dir = Path(args.out)
    print(f"[stations] -> {out_dir / 'stations.jsonl.gz'}")
    n = extract_stations(out_dir)
    print(f"  {n} stations")

    print(f"[observations] last {args.days} days -> {out_dir / 'observations'}")
    fetched, skipped = extract_observations(out_dir, args.days, args.sleep)
    print(f"  fetched={fetched} skipped(existing)={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
