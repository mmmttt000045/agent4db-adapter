#!/usr/bin/env bash
# 把另外三种模式的数据装入 PostgreSQL 模板库（配对回放的通用性实验，exp/2026-10-11-generality）。
#
# 用法：AGENTDB_URL=postgres://user:pass@host:port/db tools/bench-load.sh KIND DATA_DIR [DBNAME]
#   tpch       DATA_DIR 下没有 *.tbl 时先用 DuckDB 的 tpch 扩展生成 SF1（CALL dbgen(sf=1)），默认库名 tpch_sf1
#   ssb        DATA_DIR 是 ssb-dbgen（github.com/eyalroz/ssb-dbgen）`dbgen -s 1` 的输出（*.tbl，行尾带竖线），默认 ssb_sf1
#   financial  DATA_DIR 含 BIRD dev 的 financial.sqlite（PKDD'99 捷克银行数据），默认库名 financial
#
# 与 tools/tpcds-load.sh 相同的约定，只改表示、不改语义：
#   1. 事实表不建主键，改为粒度与日期列上的普通索引——变化场景（状态流水、重复装载、备份副本）要能写入重复键；
#      维表主键照旧。TPC-H 的 lineitem、orders，SSB 的 lineorder，financial 的 trans、loan 是事实表。
#   2. 事实表金额列一律 numeric(18,2)（TPC-H 原为 numeric(15,2)，SSB 原为 integer，financial 原为 INTEGER / REAL），
#      单位变化（×100）不溢出、撤回（÷100）后逐字节还原；其余 REAL 列为 double precision。
#      作为 SCD2 改写对象的维表属性改为变长文本（TPC-H 的 p_brand、c_mktsegment：char(10) → varchar(20)）。
#   3. 标识符一律小写、不加引号；financial 的表 `order` 是保留字，改名为 orders；district 的 A2–A16 改为小写 a2–a16。
#      表名或列名 date 在 PostgreSQL 中不加引号也能用（已在 PG 18 上验证），SSB 的 date 表与 financial 的 date 列照旧。
#   4. SSB 的 d_date 是文本（“January 1, 1992”），另加 DATE 列 d_fulldate（由 d_datekey 换算）。
set -euo pipefail
kind=$1
dir=$2
case "$kind" in
  tpch) name=${3:-tpch_sf1} ;;
  ssb) name=${3:-ssb_sf1} ;;
  financial) name=${3:-financial} ;;
  *) echo "usage: $0 tpch|ssb|financial DATA_DIR [DBNAME]" >&2; exit 2 ;;
esac
url=${AGENTDB_URL:?AGENTDB_URL not set}
base=${url%/*}
admin="$base/postgres"
db="$base/$name"
q() { psql -X -q -v ON_ERROR_STOP=1 "$db" "$@"; }

psql -X -q -v ON_ERROR_STOP=1 "$admin" -c "drop database if exists $name" -c "create database $name"

if [ "$kind" = tpch ]; then
  if ! ls "$dir"/lineitem.tbl >/dev/null 2>&1; then
    mkdir -p "$dir"
    python3 - "$dir" <<'PY'
import sys, duckdb
d = sys.argv[1]
c = duckdb.connect()
c.sql("INSTALL tpch; LOAD tpch; CALL dbgen(sf=1)")
for t in ["region", "nation", "part", "supplier", "partsupp", "customer", "orders", "lineitem"]:
    c.sql(f"COPY {t} TO '{d}/{t}.tbl' (FORMAT csv, DELIMITER '|', HEADER false)")
print("duckdb", duckdb.__version__, "tpch sf=1 ->", d)
PY
  fi
  q <<'SQL'
create table region (r_regionkey integer primary key, r_name char(25) not null, r_comment varchar(152));
create table nation (n_nationkey integer primary key, n_name char(25) not null, n_regionkey integer not null, n_comment varchar(152));
create table part (p_partkey integer primary key, p_name varchar(55) not null, p_mfgr char(25) not null, p_brand varchar(20) not null,
  p_type varchar(25) not null, p_size integer not null, p_container char(10) not null, p_retailprice numeric(18,2) not null,
  p_comment varchar(23) not null);
create table supplier (s_suppkey integer primary key, s_name char(25) not null, s_address varchar(40) not null,
  s_nationkey integer not null, s_phone char(15) not null, s_acctbal numeric(18,2) not null, s_comment varchar(101) not null);
create table partsupp (ps_partkey integer not null, ps_suppkey integer not null, ps_availqty integer not null,
  ps_supplycost numeric(18,2) not null, ps_comment varchar(199) not null, primary key (ps_partkey, ps_suppkey));
create table customer (c_custkey integer primary key, c_name varchar(25) not null, c_address varchar(40) not null,
  c_nationkey integer not null, c_phone char(15) not null, c_acctbal numeric(18,2) not null, c_mktsegment varchar(20) not null,
  c_comment varchar(117) not null);
create table orders (o_orderkey integer not null, o_custkey integer not null, o_orderstatus char(1) not null,
  o_totalprice numeric(18,2) not null, o_orderdate date not null, o_orderpriority char(15) not null, o_clerk char(15) not null,
  o_shippriority integer not null, o_comment varchar(79) not null);
create table lineitem (l_orderkey integer not null, l_partkey integer not null, l_suppkey integer not null,
  l_linenumber integer not null, l_quantity numeric(15,2) not null, l_extendedprice numeric(18,2) not null,
  l_discount numeric(15,2) not null, l_tax numeric(15,2) not null, l_returnflag char(1) not null, l_linestatus char(1) not null,
  l_shipdate date not null, l_commitdate date not null, l_receiptdate date not null, l_shipinstruct char(25) not null,
  l_shipmode char(10) not null, l_comment varchar(44) not null);
SQL
  for t in region nation part supplier partsupp customer orders lineitem; do
    echo "load $t"
    q -c "\\copy $t from '$dir/$t.tbl' with (format csv, delimiter '|')"
  done
  q <<'SQL'
create index on lineitem (l_orderkey, l_linenumber);
create index on lineitem (l_shipdate);
create index on orders (o_orderkey);
create index on orders (o_orderdate);
analyze;
SQL
fi

if [ "$kind" = ssb ]; then
  q <<'SQL'
create table part (p_partkey integer primary key, p_name varchar(22) not null, p_mfgr varchar(6), p_category varchar(7) not null,
  p_brand1 varchar(9) not null, p_color varchar(11) not null, p_type varchar(25) not null, p_size integer not null,
  p_container varchar(10) not null);
create table supplier (s_suppkey integer primary key, s_name varchar(25) not null, s_address varchar(25) not null,
  s_city varchar(10) not null, s_nation varchar(15) not null, s_region varchar(12) not null, s_phone varchar(15) not null);
create table customer (c_custkey integer primary key, c_name varchar(25) not null, c_address varchar(25) not null,
  c_city varchar(10) not null, c_nation varchar(15) not null, c_region varchar(12) not null, c_phone varchar(15) not null,
  c_mktsegment varchar(10) not null);
create table date (d_datekey integer primary key, d_date varchar(19) not null, d_dayofweek varchar(10) not null,
  d_month varchar(10) not null, d_year integer not null, d_yearmonthnum integer not null, d_yearmonth varchar(8) not null,
  d_daynuminweek integer not null, d_daynuminmonth integer not null, d_daynuminyear integer not null,
  d_monthnuminyear integer not null, d_weeknuminyear integer not null, d_sellingseason varchar(13) not null,
  d_lastdayinweekfl varchar(1) not null, d_lastdayinmonthfl varchar(1) not null, d_holidayfl varchar(1) not null,
  d_weekdayfl varchar(1) not null);
create table lineorder (lo_orderkey integer not null, lo_linenumber integer not null, lo_custkey integer not null,
  lo_partkey integer not null, lo_suppkey integer not null, lo_orderdate integer not null, lo_orderpriority varchar(15) not null,
  lo_shippriority varchar(1) not null, lo_quantity integer not null, lo_extendedprice numeric(18,2) not null,
  lo_ordertotalprice numeric(18,2) not null, lo_discount integer not null, lo_revenue numeric(18,2) not null,
  lo_supplycost numeric(18,2) not null,
  lo_tax integer not null, lo_commitdate integer not null, lo_shipmode varchar(10) not null);
SQL
  for t in part supplier customer date lineorder; do
    echo "load $t"
    # ssb-dbgen（EOL_HANDLING=OFF）在每行末尾多写一个竖线
    sed 's/|$//' "$dir/$t.tbl" | q -c "\\copy $t from stdin with (format text, delimiter '|', null '')"
  done
  q <<'SQL'
alter table date add column d_fulldate date;
update date set d_fulldate = to_date(d_datekey::text, 'YYYYMMDD');
alter table date alter column d_fulldate set not null;
comment on column date.d_fulldate is '日期（由 d_datekey 换算；d_date 是文本）';
create index on lineorder (lo_orderkey, lo_linenumber);
create index on lineorder (lo_orderdate);
vacuum analyze;
SQL
fi

if [ "$kind" = financial ]; then
  q <<'SQL'
create table district (district_id integer primary key, a2 text not null, a3 text not null, a4 text not null, a5 text not null,
  a6 text not null, a7 text not null, a8 integer not null, a9 integer not null, a10 double precision not null,
  a11 integer not null, a12 double precision, a13 double precision not null, a14 integer not null, a15 integer,
  a16 integer not null);
create table account (account_id integer primary key, district_id integer not null, frequency text not null, date date not null);
create table client (client_id integer primary key, gender text not null, birth_date date not null, district_id integer not null);
create table disp (disp_id integer primary key, client_id integer not null, account_id integer not null, type text not null);
create table card (card_id integer primary key, disp_id integer not null, type text not null, issued date not null);
create table orders (order_id integer primary key, account_id integer not null, bank_to text not null, account_to integer not null,
  amount double precision not null, k_symbol text not null);
create table loan (loan_id integer not null, account_id integer not null, date date not null, amount numeric(18,2) not null,
  duration integer not null, payments numeric(18,2) not null, status text not null);
create table trans (trans_id integer not null, account_id integer not null, date date not null, type text not null,
  operation text, amount numeric(18,2) not null, balance numeric(18,2) not null, k_symbol text, bank text, account integer);
SQL
  for t in district account client disp card order loan trans; do
    dst=$t; [ "$t" = order ] && dst=orders
    echo "load $t -> $dst"
    python3 - "$dir/financial.sqlite" "$t" <<'PY' | q -c "\\copy $dst from stdin with (format text)"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
esc = lambda v: "\\N" if v is None else str(v).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
out = sys.stdout
for row in c.execute(f'select * from "{sys.argv[2]}"'):
    out.write("\t".join(esc(v) for v in row) + "\n")
PY
  done
  q <<'SQL'
create index on trans (trans_id);
create index on trans (date);
create index on loan (loan_id);
create index on loan (date);
analyze;
SQL
fi

psql -X -tA "$db" -c "select relname, n_live_tup from pg_stat_user_tables order by n_live_tup desc" | head -20
echo "template database $name ready"
