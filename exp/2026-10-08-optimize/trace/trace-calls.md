## A · M1-L1  （7 次工具调用，工具侧共 322 ms；session r1-metric-global-opt-named-learn）
   1. list_tables      {}  → ok 0ms
   2. find_metric      {"query": "门店营业额"}  → ok 0ms
      ↳ {"ambiguous":false,"metrics":[],"note":"没有匹配的已验证指标口径"}
   1. describe_table   {"table": "store_sales"}  → ok 133ms
      ↳ {"profile":{"columns":[{"comment":"销售日期键（关联 date_dim.d_date_sk）","distinct_est":1096,"name":"ss_sold_date_sk","null_ratio":0.010305000000000009,"type":"integer…
   2. describe_table   {"table": "date_dim"}  → ok 3ms
      ↳ {"profile":{"columns":[{"comment":"日期键","distinct_est":1096,"name":"d_date_sk","null_ratio":0.0,"type":"integer"},{"comment":"日期","distinct_est":1096,"name":"d…
   1. join_path        {"table_a": "store_sales", "table_b": "date_dim"}  → ok 155ms
      ↳ {"known_bad":[],"note":null,"paths":[{"evidence":["store_sales 1000000 行中 989695 行关联得上（1.0% 关联不上）"],"filters":{},"left":"store_sales","left_unique":false,"loss…
   1. run_sql          sql=SELECT ROUND(SUM(ss.ss_net_paid), 2) AS store_revenue FROM store_sales ss JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk WHERE d.d_year = 2001 AND d.d_moy = 3  → ok rows=1 ref=r1 31ms
   1. final_answer     {"answer": "13570368.70", "used": ["r1"], "derivation": "r1"}  → final 0ms

## A · M1-L2  （5 次工具调用，工具侧共 32 ms；session r1-metric-global-opt-named-learn）
   1. list_tables      {}  → ok 0ms
   2. find_metric      {"query": "门店营业额"}  → ok 3ms
      ↳ {"ambiguous":false,"metrics":[{"aliases":["store revenue","门店销售额","门店营收"],"basis":{"kind":"explicit_question","task":"M1-L1"},"caveats":["口径使用净支付额 ss_net_paid，…
   1. join_path        {"table_a": "store_sales", "table_b": "date_dim"}  → ok 3ms
      ↳ {"known_bad":[],"paths":[{"evidence":["store_sales 1000000 行中 989695 行关联得上（1.0% 关联不上）"],"filters":{},"left":"store_sales","left_unique":false,"loss_ratio":0.01…
   1. run_sql          sql=SELECT ROUND(SUM(ss.ss_net_paid), 2) AS store_revenue FROM store_sales ss JOIN date_dim d ON ss.ss_sold_date_sk = d.d_date_sk WHERE d.d_year = 2000 AND d.d_moy = 11  metrics=[{"key": "metric:门店营业额", "revision": 0}]  → ok rows=1 ref=r1 26ms
   1. final_answer     {"answer": "13085788.40", "used": ["r1"], "derivation": "r1"}  → final 0ms

## B · M1-P1  （6 次工具调用，工具侧共 31 ms；session r1-metric-global-opt-named-holdout）
   1. list_tables      {}  → ok 0ms
   2. find_metric      {"query": "门店营业额"}  → ok 4ms
      ↳ {"ambiguous":true,"metrics":[{"aliases":["store revenue","门店销售额","门店营收"],"basis":{"kind":"explicit_question","task":"M1-L1"},"caveats":["口径使用净支付额 ss_net_paid，不…
   1. describe_table   {"table": "store_sales"}  → ok 3ms
      ↳ {"profile":{"columns":[{"comment":"销售日期键（关联 date_dim.d_date_sk）","distinct_est":1096,"name":"ss_sold_date_sk","null_ratio":0.010305000000000009,"type":"integer…
   2. describe_table   {"table": "date_dim"}  → ok 0ms
      ↳ {"profile":{"columns":[{"comment":"日期键","distinct_est":1096,"name":"d_date_sk","null_ratio":0.0,"type":"integer"},{"comment":"日期","distinct_est":1096,"name":"d…
   1. run_sql          sql=select round(sum(ss_net_paid), 2) as value from store_sales where ss_sold_date_sk between (select min(d_date_sk) from date_dim where d_year = 2002 and d_moy = 9) and (se…  metrics=[{"key": "metric:门店营业额", "revision": 1}]  → ok rows=1 ref=r1 24ms
   1. final_answer     {"answer": "13069651.80", "used": ["r1"], "derivation": "r1"}  → final 0ms

## B · M1-T1  （7 次工具调用，工具侧共 69 ms；session r1-metric-global-opt-named-holdout）
   1. list_tables      {}  → ok 0ms
   2. find_metric      {"query": "门店营业额"}  → ok 3ms
      ↳ {"ambiguous":true,"metrics":[{"aliases":["store revenue","门店销售额","门店营收"],"basis":{"kind":"explicit_question","task":"M1-L1"},"caveats":["口径使用净支付额 ss_net_paid，不…
   1. describe_table   {"table": "store_sales"}  → ok 4ms
      ↳ {"profile":{"columns":[{"comment":"销售日期键（关联 date_dim.d_date_sk）","distinct_est":1096,"name":"ss_sold_date_sk","null_ratio":0.010305000000000009,"type":"integer…
   2. describe_table   {"table": "date_dim"}  → ok 0ms
      ↳ {"profile":{"columns":[{"comment":"日期键","distinct_est":1096,"name":"d_date_sk","null_ratio":0.0,"type":"integer"},{"comment":"日期","distinct_est":1096,"name":"d…
   1. run_sql          sql=select round(sum(ss_net_paid),2) as value from store_sales where ss_sold_date_sk between (select min(d_date_sk) from date_dim where d_year = 2002 and d_moy = 9) and (sel…  metrics=[{"key": "metric:门店营业额", "revision": 1}]  → ok rows=1 ref=r1 32ms
   2. run_sql          sql=select round(sum(ss_net_paid),2) as value from store_sales where ss_sold_date_sk between (select min(d_date_sk) from date_dim where d_year = 2001 and d_moy = 6) and (sel…  metrics=[{"key": "metric:门店营业额", "revision": 1}]  → ok rows=1 ref=r2 30ms
   1. final_answer     {"answer": "-12007.70", "used": ["r1", "r2"], "derivation": "r1 - r2"}  → final 0ms

## B · M1-T2  （5 次工具调用，工具侧共 135 ms；session r1-metric-global-opt-named-holdout）
   1. list_tables      {}  → ok 0ms
   2. find_metric      {"query": "门店营业额"}  → ok 3ms
      ↳ {"ambiguous":true,"metrics":[{"aliases":["store revenue","门店销售额","门店营收"],"basis":{"kind":"explicit_question","task":"M1-L1"},"caveats":["口径使用净支付额 ss_net_paid，不…
   1. join_path        {"table_a": "store_sales", "table_b": "date_dim"}  → ok 3ms
      ↳ {"known_bad":[],"paths":[{"evidence":["store_sales 1000000 行中 989695 行关联得上（1.0% 关联不上）"],"filters":{},"left":"store_sales","left_unique":false,"loss_ratio":0.01…
   1. run_sql          sql=select d.d_moy as month, sum(s.ss_net_paid) as revenue from store_sales s join date_dim d on s.ss_sold_date_sk = d.d_date_sk where d.d_year = 2002 group by d.d_moy order…  metrics=[{"key": "metric:门店营业额", "revision": 1}]  → ok rows=12 ref=r1 129ms
   1. final_answer     {"answer": "12", "used": ["r1"], "derivation": "r1"}  → final 0ms

## B · M1-P1  （9 次工具调用，工具侧共 64156 ms；session r1-metric-global-opt-named-revision）
   1. list_tables      {}  → ok 0ms
   2. find_metric      {"query": "门店营业额"}  → ok 54492ms
      ↳ {"ambiguous":true,"metrics":[{"aliases":["store revenue","门店销售额","门店营收"],"basis":{"kind":"explicit_question","task":"M1-L1"},"caveats":["口径使用净支付额 ss_net_paid，不…
   1. describe_table   {"table": "store_sales"}  → ok 166ms
      ↳ {"profile":{"columns":[{"comment":"销售日期键（关联 date_dim.d_date_sk）","distinct_est":1096,"name":"ss_sold_date_sk","null_ratio":0.00966775024274924,"type":"integer"…
   2. describe_table   {"table": "date_dim"}  → ok 0ms
      ↳ {"profile":{"columns":[{"comment":"日期键","distinct_est":1096,"name":"d_date_sk","null_ratio":0.0,"type":"integer"},{"comment":"日期","distinct_est":1096,"name":"d…
   1. run_sql          sql=select ss_is_current, count(*) as rows, count(distinct (ss_sold_date_sk, ss_ticket_number, ss_item_sk)) as distinct_key, count(distinct ss_sold_date_sk) as distinct_date…  → rejected 5ms
      ↳ {"reason":"表 store_sales 现在每个键有多行（状态流水）；统计前需要加过滤 ss_is_current = '1'，否则会重复计算","rejected":true,"required_filter":{"filter":"ss_is_current = '1'","table":"store_…
   2. run_sql          sql=select count(*) as total_rows, count(*) filter (where ss_sold_date_sk is null) as null_date, count(distinct (ss_sold_date_sk, ss_ticket_number, ss_item_sk)) as distinct_…  → rejected 1ms
      ↳ {"reason":"表 store_sales 现在每个键有多行（状态流水）；统计前需要加过滤 ss_is_current = '1'，否则会重复计算","rejected":true,"required_filter":{"filter":"ss_is_current = '1'","table":"store_…
   1. run_sql          sql=select count(*) as rows, count(distinct (ss_sold_date_sk, ss_ticket_number, ss_item_sk)) as distinct_key, count(distinct (ss_ticket_number, ss_item_sk)) as distinct_tick…  → ok rows=1 ref=r1 9466ms
   1. run_sql          sql=select round(sum(ss_net_paid), 2) as value from store_sales where ss_is_current = '1' and ss_sold_date_sk between (select min(d_date_sk) from date_dim where d_year = 200…  → ok rows=1 ref=r2 26ms
   1. final_answer     {"answer": "12932888.04", "used": ["r2"], "derivation": "r2"}  → final 0ms

## B · M1-T1  （4 次工具调用，工具侧共 51 ms；session r1-metric-global-opt-named-revision）
   1. list_tables      {}  → ok 0ms
   2. find_metric      {"query": "门店营业额"}  → ok 3ms
      ↳ {"ambiguous":true,"metrics":[{"aliases":["store revenue","门店销售额","门店营收"],"basis":{"kind":"explicit_question","task":"M1-L1"},"caveats":["口径使用净支付额 ss_net_paid，不…
   1. run_sql          sql=select (select sum(ss_net_paid) from store_sales where ss_is_current = '1' and ss_sold_date_sk between (select min(d_date_sk) from date_dim where d_year = 2002 and d_moy…  metrics=[{"key": "metric:门店营业额", "revision": 2}]  → ok rows=1 ref=r1 47ms
   1. final_answer     {"answer": "-9803.47", "used": ["r1"], "derivation": "r1: v_2002_09 - v_2001_06 = 12932888.04 - 12942691.51"}  → final 0ms

## B · M1-T2  （4 次工具调用，工具侧共 162 ms；session r1-metric-global-opt-named-revision）
   1. list_tables      {}  → ok 0ms
   2. find_metric      {"query": "门店营业额"}  → ok 3ms
      ↳ {"ambiguous":true,"metrics":[{"aliases":["store revenue","门店销售额","门店营收"],"basis":{"kind":"explicit_question","task":"M1-L1"},"caveats":["口径使用净支付额 ss_net_paid，不…
   1. run_sql          sql=select d_moy as month, sum(ss_net_paid) as revenue from store_sales join date_dim on ss_sold_date_sk = d_date_sk where ss_is_current = '1' and d_year = 2002 group by d_m…  metrics=[{"key": "metric:门店营业额", "revision": 2}]  → ok rows=12 ref=r1 159ms
   1. final_answer     {"answer": "12", "used": ["r1"], "derivation": "r1"}  → final 0ms

