-- Minimal synthetic data for integration tests; load only into a fresh test database.
create table date_dim (d_date_sk int, d_date date);
insert into date_dim values (1, date '2001-09-01'), (2, date '2001-11-01');

create table item (i_item_sk int, i_category text);
insert into item select g, 'category-' || (g % 3) from generate_series(1,10) g;
create table customer (c_customer_sk int, c_name text);
insert into customer select g, 'customer-' || g from generate_series(1,10) g;
create table warehouse (w_warehouse_sk int, w_name text);
insert into warehouse select g, 'warehouse-' || g from generate_series(1,10) g;

create table store_sales (
  ss_ticket_number int, ss_item_sk int, ss_customer_sk int,
  ss_warehouse_sk int, ss_sold_date_sk int, ss_net_paid numeric(12,2)
);
insert into store_sales
select (g+1)/2, g, g, g, case when g <= 8 then 1 else 2 end, 100
from generate_series(1,10) g;

create table store_returns (
  sr_ticket_number int, sr_item_sk int, sr_returned_date_sk int,
  sr_return_amt numeric(12,2)
);
insert into store_returns
select ss_ticket_number, ss_item_sk, ss_sold_date_sk, 10 from store_sales;
analyze date_dim;
analyze item;
analyze customer;
analyze warehouse;
analyze store_sales;
analyze store_returns;
