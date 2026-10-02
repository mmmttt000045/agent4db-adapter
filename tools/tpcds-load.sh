#!/usr/bin/env bash
# 把 dsdgen 生成的 TPC-DS 数据装入 PostgreSQL 模板库（配对回放的第二个负载，`replay-bench --schema tpcds`）。
#
# 用法：AGENTDB_URL=postgres://user:pass@host:port/db tools/tpcds-load.sh DATA_DIR DDL_FILE [DBNAME]
#   DATA_DIR  dsdgen -scale 1 -dir DATA_DIR 的输出（*.dat，竖线分隔、行尾多一个竖线）
#   DDL_FILE  tpcds-kit 的 tools/tpcds.sql
#   DBNAME    模板库名，默认 tpcds_sf1；已存在则先删除
#
# 与官方 DDL 的两处差别只改表示、不改语义：
#   1. 六张销售/退货事实表不建主键，改为普通索引——变化场景（状态流水、重复装载、备份副本）要能写入重复键，
#      与合成数据的做法相同；维表主键照旧。
#   2. decimal(7,2) 放宽为 numeric(12,2)——单位变化（×100）不溢出。
set -euo pipefail
dir=$1
ddl=$2
name=${3:-tpcds_sf1}
url=${AGENTDB_URL:?AGENTDB_URL not set}
base=${url%/*}
admin="$base/postgres"
db="$base/$name"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

python3 - "$ddl" "$work/ddl.sql" <<'PY'
import re, sys
src, dst = sys.argv[1:3]
text = open(src, encoding="utf-8", errors="replace").read()
text = re.sub(r"--.*", "", text)
text = re.sub(r"decimal\(7,2\)", "numeric(12,2)", text)
facts = "ss_item_sk, ss_ticket_number|sr_item_sk, sr_ticket_number|cs_item_sk, cs_order_number|cr_item_sk, cr_order_number|ws_item_sk, ws_order_number|wr_item_sk, wr_order_number"
text, n = re.subn(r",\s*primary key \((" + facts + r")\)", "", text)
assert n == 6, f"expected 6 fact-table primary keys, removed {n}"
open(dst, "w", encoding="utf-8").write(text)
PY

psql -X -q -v ON_ERROR_STOP=1 "$admin" -c "drop database if exists $name" -c "create database $name"
psql -X -q -v ON_ERROR_STOP=1 "$db" -f "$work/ddl.sql"

for f in "$dir"/*.dat; do
  t=$(basename "$f" .dat)
  if ! psql -X -tA "$db" -c "select 1 from information_schema.tables where table_schema = 'public' and table_name = '$t'" | grep -q 1; then
    echo "skip $t (no table)"; continue
  fi
  echo "load $t"
  psql -X -q -v ON_ERROR_STOP=1 "$db" -c "\\copy $t from program 'sed \"s/|\$//\" \"$f\"' with (format text, delimiter '|', null '')"
done

psql -X -q -v ON_ERROR_STOP=1 "$db" <<'SQL'
create index on store_sales (ss_item_sk, ss_ticket_number);
create index on store_sales (ss_sold_date_sk);
create index on store_returns (sr_item_sk, sr_ticket_number);
create index on store_returns (sr_returned_date_sk);
create index on catalog_sales (cs_item_sk, cs_order_number);
create index on catalog_sales (cs_sold_date_sk);
create index on catalog_returns (cr_item_sk, cr_order_number);
create index on catalog_returns (cr_returned_date_sk);
create index on web_sales (ws_item_sk, ws_order_number);
create index on web_sales (ws_sold_date_sk);
create index on web_returns (wr_item_sk, wr_order_number);
create index on web_returns (wr_returned_date_sk);
analyze;
SQL
psql -X -tA "$db" -c "select relname, n_live_tup from pg_stat_user_tables where n_live_tup > 0 order by n_live_tup desc" | head -30
echo "template database $name ready"
