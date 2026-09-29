"""Download unmodified official TLC data and load an isolated PostgreSQL database.

Dependencies: duckdb, psycopg[binary]. Raw data and credentials stay under results/.
Never loads fixtures into the configured source database.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "target/realdata-deps"))
import duckdb
import psycopg
from psycopg import sql


def configured_url():
    values = dict(os.environ)
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                values.setdefault(k.strip(), v.strip().strip("\"'"))
    return values.get("AGENTDB_TEST_URL") or values["AGENTDB_URL"]


def prepare(directory):
    directory.mkdir(parents=True, exist_ok=True)
    sources = []
    for name, url in [
        *[(f"yellow_tripdata_2024-{m:02d}.parquet", f"https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-{m:02d}.parquet") for m in (1, 2)],
        ("taxi_zone_lookup.csv", "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"),
    ]:
        path = directory / name
        if not path.exists():
            print(f"Downloading {name}", flush=True)
            part = path.with_suffix(path.suffix + ".part")
            urllib.request.urlretrieve(url, part)
            part.replace(path)
        sources.append(dict(file=name, url=url, bytes=path.stat().st_size, sha256=hashlib.file_digest(path.open("rb"), "sha256").hexdigest()))
    conn = duckdb.connect()
    conn.execute("set threads=4")
    parquet = str(directory / "yellow_tripdata_2024-*.parquet").replace("\\", "/")
    csv = directory / "trips.csv"
    # Preserve every row. file month is provenance, not a claim that timestamps are in that month.
    query = f"""select row_number() over ()::bigint as t_id, VendorID::integer as t_vendor,
    tpep_pickup_datetime as t_pickup, tpep_dropoff_datetime as t_dropoff,
    PULocationID::integer as t_pu, DOLocationID::integer as t_do,
    passenger_count as t_passengers, trip_distance as t_distance,
    fare_amount::decimal(18,2) as t_fare, tip_amount::decimal(18,2) as t_tip,
    total_amount::decimal(18,2) as t_total, payment_type::integer as t_payment,
    case when filename like '%2024-01%' then 1 else 2 end as t_file_month
    from read_parquet('{parquet}', filename=true)"""
    print("Converting actual records, preserving nulls and anomalies", flush=True)
    conn.execute(f"copy ({query}) to '{csv.as_posix()}' (header, delimiter ',')")
    root_url = configured_url()
    dbname = f"agentdb_tlc_{int(time.time())}"
    parts = urlsplit(root_url)
    isolated_url = urlunsplit((parts.scheme, parts.netloc, "/" + dbname, parts.query, parts.fragment))
    with psycopg.connect(root_url, autocommit=True) as root:
        root.execute(sql.SQL("create database {}").format(sql.Identifier(dbname)))
    # Local-only connection file, never print credentials.
    (directory / "connection.txt").write_text(isolated_url, encoding="utf-8")
    with psycopg.connect(isolated_url, autocommit=True) as pg:
        pg.execute("""create table trips(t_id bigint primary key,t_vendor int,t_pickup timestamp,t_dropoff timestamp,
        t_pu int,t_do int,t_passengers double precision,t_distance double precision,t_fare numeric(18,2),
        t_tip numeric(18,2),t_total numeric(18,2),t_payment int,t_file_month int);
        create table zones(z_id int primary key,z_borough text,z_name text,z_service text);
        create table etl_batch_log(table_name text,batch_id int);""")
        for table, path in [("trips", csv), ("zones", directory / "taxi_zone_lookup.csv")]:
            print(f"Loading {table}", flush=True)
            with pg.cursor().copy(f"copy {table} from stdin with (format csv, header true)") as cp:
                with path.open("rb") as f:
                    while chunk := f.read(4 * 1024 * 1024):
                        cp.write(chunk)
        pg.execute("create index on trips(t_pu,t_pickup); create index on trips(t_do); create index on trips(t_file_month,t_pu)")
        pg.execute("""create table zone_day as select t_pu as a_zone,t_pickup::date as a_day,
        count(*)::bigint as a_trips,sum(t_total) as a_total from trips group by t_pu,t_pickup::date;
        create index on zone_day(a_zone,a_day); analyze trips; analyze zones; analyze zone_day;""")
        counts = {t: pg.execute(f"select count(*) from {t}").fetchone()[0] for t in ["trips", "zones", "zone_day"]}
        quality = pg.execute("""select count(*) filter(where t_total<0),count(*) filter(where t_passengers is null),
        count(*) filter(where t_pickup < timestamp '2024-01-01' or t_pickup>=timestamp '2024-03-01') from trips""").fetchone()
        size = pg.execute("select sum(pg_total_relation_size(relid))::bigint from pg_stat_user_tables").fetchone()[0]
        version = pg.execute("select version()").fetchone()[0]
    manifest = dict(source="NYC TLC official yellow taxi January/February 2024 and taxi zone lookup",
        source_page="https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page", files=sources,
        counts=counts, relation_bytes=size, postgres=version, database=dbname,
        transformations="All source rows retained; selected columns renamed; money cast to decimal(18,2); generated row id; zone_day is a real-data aggregation.",
        quality=dict(negative_total=quality[0],null_passengers=quality[1],pickup_outside_two_months=quality[2]),
        retrieved_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
    (directory / "manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    print(json.dumps(dict(counts=counts,relation_bytes=size,database=dbname)),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "results/tlc-real-data")
    args=parser.parse_args()
    prepare(args.out.resolve())
