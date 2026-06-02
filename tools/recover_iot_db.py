import os
import sqlite3
import sys
from datetime import datetime


SOURCE = "iot_data.db"


def quote_name(name):
    return '"' + name.replace('"', '""') + '"'


TABLES = [
    "sensor_data",
    "mqtt_experiment_log",
    "unknown_payload_data",
    "unknown_schema_profile",
    "apr_policy_log",
    "voice_experiment_results",
]


def fetch_tables(conn):
    placeholders = ", ".join("?" for _ in TABLES)
    return conn.execute(
        "SELECT name, sql FROM sqlite_master "
        f"WHERE type='table' AND name IN ({placeholders}) "
        "ORDER BY name",
        TABLES,
    ).fetchall()


def copy_table(src, dst, table_name, batch_size=500):
    qname = quote_name(table_name)
    columns = [row[1] for row in src.execute(f"PRAGMA table_info({qname})")]
    if not columns:
        return 0, 0

    col_list = ", ".join(quote_name(c) for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert_sql = f"INSERT OR IGNORE INTO {qname} ({col_list}) VALUES ({placeholders})"

    try:
        max_rowid = src.execute(f"SELECT MAX(rowid) FROM {qname}").fetchone()[0]
    except sqlite3.DatabaseError:
        max_rowid = None

    copied = 0
    skipped = 0

    if max_rowid is None:
        try:
            cur = src.execute(f"SELECT {col_list} FROM {qname}")
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                dst.executemany(insert_sql, rows)
                copied += len(rows)
        except sqlite3.DatabaseError as exc:
            print(f"[WARN] {table_name}: bulk copy stopped: {exc}")
            skipped += 1
        return copied, skipped

    rowid = 1
    while rowid <= max_rowid:
        end = min(rowid + batch_size - 1, max_rowid)
        try:
            rows = src.execute(
                f"SELECT {col_list} FROM {qname} WHERE rowid BETWEEN ? AND ? ORDER BY rowid",
                (rowid, end),
            ).fetchall()
            if rows:
                dst.executemany(insert_sql, rows)
                copied += len(rows)
        except sqlite3.DatabaseError:
            for rid in range(rowid, end + 1):
                try:
                    one = src.execute(
                        f"SELECT {col_list} FROM {qname} WHERE rowid=?",
                        (rid,),
                    ).fetchone()
                    if one:
                        dst.execute(insert_sql, one)
                        copied += 1
                except sqlite3.DatabaseError:
                    skipped += 1
        rowid = end + 1

    return copied, skipped


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else SOURCE
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    recovered = f"{os.path.splitext(source)[0]}.recovered_{stamp}.db"

    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(recovered)

    tables = fetch_tables(src)
    print(f"[INFO] tables={len(tables)} target={recovered}")

    for table_name, create_sql in tables:
        try:
            dst.execute(create_sql)
            dst.commit()
        except sqlite3.DatabaseError as exc:
            print(f"[WARN] {table_name}: create failed: {exc}")
            continue

        copied, skipped = copy_table(src, dst, table_name)
        dst.commit()
        print(f"[INFO] {table_name}: copied={copied} skipped={skipped}")

    src.close()
    dst.execute("PRAGMA journal_mode=WAL")
    dst.execute("PRAGMA synchronous=NORMAL")
    integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
    dst.close()
    print(f"[INFO] recovered_integrity={integrity}")
    print(recovered)


if __name__ == "__main__":
    main()
