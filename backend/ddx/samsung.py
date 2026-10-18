"""Samsung Health export (Settings > Download personal data) -> ClinicQuick observations.
Best effort: Samsung's export is a zip of CSVs whose first line is metadata and second line the header.
Rows land in the same `observations` table and codes as Apple Health (steps, rhr, spo2, sleep_min, weight, temp)."""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timedelta, timezone

from app import db

# file-name fragment -> (our code, value column suffixes, unit)
FILES = [
    ("pedometer_day_summary", "steps", ("step_count", "count"), "count"),
    ("step_daily_trend", "steps", ("count", "step_count"), "count"),
    ("tracker.heart_rate", "rhr", ("heart_rate",), "bpm"),
    ("oxygen_saturation", "spo2", ("spo2", "oxygen_saturation"), "%"),
    ("body_temperature", "temp", ("temperature",), "C"),
    ("weight", "weight", ("weight",), "kg"),
    ("sleep", "sleep_min", (), "min"),
]
TIME_COLS = ("start_time", "day_time", "create_time", "update_time")


def _parse_time(v: str) -> datetime | None:
    v = (v or "").strip()
    if not v:
        return None
    if v.isdigit():  # epoch milliseconds
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
        try:
            d = datetime.strptime(v, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _col(header: list[str], suffixes: tuple[str, ...]) -> int | None:
    for s in suffixes:
        for i, h in enumerate(header):
            if h.split(".")[-1] == s:
                return i
    return None


def import_export(patient_id: str, data: bytes, days: int = 90) -> dict:
    if data[:2] != b"PK":
        raise ValueError("Upload the Samsung Health export as a .zip")
    z = zipfile.ZipFile(io.BytesIO(data))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows, counts = [], {}
    for name in z.namelist():
        if not name.endswith(".csv"):
            continue
        spec = next((f for f in FILES if f[0] in name), None)
        if not spec:
            continue
        frag, code, vcols, unit = spec
        lines = z.read(name).decode("utf-8-sig", errors="ignore").splitlines()
        if len(lines) < 3:
            continue
        reader = csv.reader(lines[1:])  # line 0 is Samsung's metadata line
        header = next(reader)
        ti = next((i for t in TIME_COLS for i, h in enumerate(header) if h.split(".")[-1] == t), None)
        if ti is None:
            continue
        if code == "sleep_min":
            ei = next((i for i, h in enumerate(header) if h.split(".")[-1] == "end_time"), None)
            if ei is None:
                continue
        else:
            vi = _col(header, vcols)
            if vi is None:
                continue
        for r in reader:
            if len(r) <= ti:
                continue
            ts = _parse_time(r[ti])
            if not ts or ts < cutoff:
                continue
            try:
                if code == "sleep_min":
                    end = _parse_time(r[ei])
                    v = (end - ts).total_seconds() / 60 if end else None
                else:
                    v = float(r[vi])
            except (ValueError, IndexError, TypeError):
                continue
            if v is None or v <= 0:
                continue
            rows.append((patient_id, ts, code, v, unit, "samsung-health"))
            counts[code] = counts.get(code, 0) + 1
    if rows:
        with db.conn() as c:
            with c.cursor().copy("COPY observations (patient_id, ts, code, value, unit, source) FROM STDIN") as cp:
                for r in rows:
                    cp.write_row(r)
        db.refresh_daily_obs()
    return {"imported": len(rows), "by_type": counts}
