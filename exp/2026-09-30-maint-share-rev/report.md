# 维护方式对照（不调用 LLM）

口径数随共享度 k 变化（k = 6 为全部 19 条），8 个 Agent；每次变化后每个 Agent 把全部口径各用一次。组名 r轮次-k共享度-维护方式-到达方式。本报告是描述性结果，不作显著性声明。协议见 docs/metric-experience-protocol.md。

## 1. 准入（各组相同）

| 组 | 晋升 | 耗时 s | DB 查询 | DB ms |
|---|---|---|---|---|
| r1-k1-condition-staggered | 4 | 45.6 | 32 | 19224 |
| r1-k1-condition-burst | 4 | 48.1 | 32 | 19007 |
| r1-k1-condition-scope-staggered | 4 | 71.0 | 32 | 19314 |
| r1-k1-condition-scope-burst | 4 | 53.3 | 32 | 18815 |
| r1-k1-definition-staggered | 4 | 78.9 | 32 | 18835 |
| r1-k1-definition-burst | 4 | 58.3 | 32 | 18846 |
| r1-k1-schema-staggered | 4 | 25.4 | 32 | 18771 |
| r1-k1-schema-burst | 4 | 25.6 | 32 | 18936 |
| r1-k1-revoke-staggered | 4 | 61.3 | 32 | 18816 |
| r1-k1-revoke-burst | 4 | 61.8 | 32 | 19026 |
| r1-k2-condition-staggered | 8 | 64.0 | 49 | 33411 |
| r1-k2-condition-burst | 8 | 66.2 | 49 | 33891 |
| r1-k2-condition-scope-staggered | 8 | 118.4 | 49 | 33827 |
| r1-k2-condition-scope-burst | 8 | 71.8 | 49 | 33711 |
| r1-k2-definition-staggered | 8 | 150.4 | 49 | 37372 |
| r1-k2-definition-burst | 8 | 79.7 | 49 | 34882 |
| r1-k2-schema-staggered | 8 | 45.6 | 49 | 34222 |
| r1-k2-schema-burst | 8 | 45.9 | 49 | 34546 |
| r1-k2-revoke-staggered | 8 | 99.9 | 49 | 34466 |
| r1-k2-revoke-burst | 8 | 100.6 | 49 | 34650 |
| r1-k4-condition-staggered | 15 | 102.1 | 78 | 59803 |
| r1-k4-condition-burst | 15 | 99.5 | 78 | 60535 |
| r1-k4-condition-scope-staggered | 15 | 209.2 | 78 | 59989 |
| r1-k4-condition-scope-burst | 15 | 117.2 | 78 | 61191 |
| r1-k4-definition-staggered | 15 | 231.5 | 78 | 59788 |
| r1-k4-definition-burst | 15 | 128.7 | 78 | 59574 |
| r1-k4-schema-staggered | 15 | 78.7 | 78 | 60552 |
| r1-k4-schema-burst | 15 | 77.1 | 78 | 59492 |
| r1-k4-revoke-staggered | 15 | 160.8 | 78 | 58824 |
| r1-k4-revoke-burst | 15 | 161.4 | 78 | 59536 |
| r1-k6-condition-staggered | 19 | 112.9 | 94 | 73082 |
| r1-k6-condition-burst | 19 | 112.5 | 94 | 73646 |
| r1-k6-condition-scope-staggered | 19 | 234.4 | 94 | 73754 |
| r1-k6-condition-scope-burst | 19 | 150.4 | 94 | 73789 |
| r1-k6-definition-staggered | 19 | 272.2 | 94 | 74202 |
| r1-k6-definition-burst | 19 | 166.6 | 94 | 73472 |
| r1-k6-schema-staggered | 19 | 91.4 | 94 | 73516 |
| r1-k6-schema-burst | 19 | 90.8 | 94 | 73469 |
| r1-k6-revoke-staggered | 19 | 187.7 | 94 | 73270 |
| r1-k6-revoke-burst | 19 | 187.9 | 94 | 73217 |

## 2. 每次变化后的维护、可用性与正确性

维护结果：刷新＝待验证后重查通过；修复＝条件不成立、正式撤销后受限修复并通过回归；未恢复＝撤销后修复失败或不在修复范围；重提＝逐写入撤销，只能重新提炼。条件（跳过/复用/执行/强制/交给关联经验）：跳过＝读到的表未变化；复用＝同一版本上已有同一条件或蕴含它的结论；执行＝本次访问数据库（含在途合并）；强制＝定义级重跑关联守卫；交给关联经验＝由关联经验按其守卫涉及的表决定是否重跑。DB 为中间层在该次变化后全部使用期间的查询（维护之外只有版本读取）。等待＝本次使用执行了维护或合并进了别人的维护。过期使用＝返回为有效但答错探测题；误撤销＝变化前的修订仍然正确却被撤销；不可用＝返回撤销或候选状态。

### 到达方式：burst

| 组 | 变化 | 维护次数 | 刷新/修复/未恢复/重提 | 合并的并发维护 | 条件：跳过/复用/执行/强制/交给关联经验 | 修复复用 | DB 查询 | DB ms | 其中 守卫与关联检查/指标检查/修复 ms | 等待维护的使用 | 等待总时长 s | p95 ms | 最大 ms | 过期使用 | 误撤销 | 不可用 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1-k1-condition-burst | sales-append | 2 | 2/0/0/0 | 9 | 2/1/1/0/1 | 0 | 5 | 7042 | 1252/5782/0 | 11 | 46.3 | 5794 | 5794 | 0 | 0 | 0 |
| r1-k1-condition-burst | returns-append | 2 | 2/0/0/0 | 7 | 3/0/1/0/1 | 0 | 5 | 3603 | 1674/1919/0 | 9 | 15.4 | 1925 | 1925 | 0 | 0 | 0 |
| r1-k1-condition-burst | catalog-append | 1 | 1/0/0/0 | 7 | 1/0/1/0/0 | 0 | 3 | 2781 | 0/2775/0 | 8 | 22.2 | 2775 | 2778 | 0 | 0 | 0 |
| r1-k1-condition-burst | v2 | 2 | 0/2/0/0 | 8 | 1/0/1/0/1 | 0 | 22 | 22329 | 4947/5201/12159 | 10 | 92.3 | 11536 | 11539 | 0 | 0 | 0 |
| r1-k1-condition-scope-burst | sales-append | 2 | 2/0/0/0 | 6 | 2/0/2/0/1 | 0 | 5 | 7141 | 1246/5886/0 | 8 | 47.2 | 5899 | 5899 | 0 | 0 | 0 |
| r1-k1-condition-scope-burst | returns-append | 2 | 2/0/0/0 | 7 | 3/0/1/0/1 | 0 | 5 | 3647 | 1708/1925/0 | 9 | 15.4 | 1934 | 1934 | 0 | 0 | 0 |
| r1-k1-condition-scope-burst | catalog-append | 1 | 1/0/0/0 | 7 | 1/0/1/0/0 | 0 | 3 | 2787 | 0/2781/0 | 8 | 22.3 | 2781 | 2784 | 0 | 0 | 0 |
| r1-k1-condition-scope-burst | v2 | 2 | 0/2/0/0 | 8 | 1/0/1/0/1 | 0 | 25 | 27699 | 5022/10490/12155 | 10 | 135.8 | 16968 | 16972 | 0 | 0 | 0 |
| r1-k1-definition-burst | sales-append | 2 | 2/0/0/0 | 6 | 0/0/2/3/0 | 0 | 9 | 8478 | 2726/5741/0 | 8 | 46.1 | 5758 | 5758 | 0 | 0 | 0 |
| r1-k1-definition-burst | returns-append | 2 | 2/0/0/0 | 13 | 0/0/2/3/0 | 0 | 11 | 10309 | 3013/7278/0 | 15 | 66.7 | 6379 | 8338 | 0 | 0 | 0 |
| r1-k1-definition-burst | catalog-append | 1 | 1/0/0/0 | 7 | 0/0/1/1/0 | 0 | 4 | 2722 | 1/2714/0 | 8 | 21.7 | 2716 | 2720 | 0 | 0 | 0 |
| r1-k1-definition-burst | v2 | 2 | 0/2/0/0 | 6 | 0/0/1/2/0 | 0 | 26 | 27477 | 4581/10702/12166 | 8 | 118.7 | 15940 | 15943 | 0 | 0 | 2 |
| r1-k1-schema-burst | sales-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 4 | 4 | 0 | 0 | 0 |
| r1-k1-schema-burst | returns-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 0 | 0 | 0 |
| r1-k1-schema-burst | catalog-append | 1 | 1/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 1 | 0.0 | 3 | 3 | 0 | 0 | 0 |
| r1-k1-schema-burst | v2 | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 16 | 0 | 0 |
| r1-k1-revoke-burst | sales-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 4 | 4 | 0 | 2 | 16 |
| r1-k1-revoke-burst | returns-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 2 | 0/0/0 | 2 | 0.0 | 3 | 3 | 0 | 2 | 16 |
| r1-k1-revoke-burst | catalog-append | 1 | 0/0/0/1 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 1 | 0.0 | 3 | 3 | 0 | 1 | 8 |
| r1-k1-revoke-burst | v2 | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 4 | 4 | 0 | 0 | 16 |
| r1-k2-condition-burst | sales-append | 4 | 4/0/0/0 | 9 | 4/2/2/0/2 | 0 | 5 | 6651 | 1359/5280/0 | 13 | 42.3 | 3906 | 5284 | 0 | 0 | 0 |
| r1-k2-condition-burst | returns-append | 4 | 4/0/0/0 | 8 | 6/0/2/0/2 | 0 | 5 | 3638 | 1540/2089/0 | 12 | 16.7 | 2089 | 2093 | 0 | 0 | 0 |
| r1-k2-condition-burst | catalog-append | 2 | 2/0/0/0 | 6 | 2/0/2/0/0 | 0 | 3 | 2703 | 0/2697/0 | 8 | 21.6 | 2698 | 2701 | 0 | 0 | 0 |
| r1-k2-condition-burst | v2 | 4 | 0/4/0/0 | 7 | 2/0/2/0/2 | 0 | 32 | 35432 | 4913/5613/24862 | 11 | 92.5 | 11558 | 11562 | 0 | 0 | 5 |
| r1-k2-condition-scope-burst | sales-append | 4 | 4/0/0/0 | 4 | 4/0/4/0/2 | 0 | 5 | 6660 | 1392/5256/0 | 8 | 42.1 | 5259 | 5259 | 0 | 0 | 0 |
| r1-k2-condition-scope-burst | returns-append | 4 | 4/0/0/0 | 8 | 6/0/2/0/2 | 0 | 5 | 3597 | 1525/2064/0 | 12 | 16.5 | 2065 | 2068 | 0 | 0 | 0 |
| r1-k2-condition-scope-burst | catalog-append | 2 | 2/0/0/0 | 6 | 2/0/2/0/0 | 0 | 3 | 2567 | 0/2562/0 | 8 | 20.5 | 2562 | 2565 | 0 | 0 | 0 |
| r1-k2-condition-scope-burst | v2 | 4 | 0/4/0/0 | 7 | 2/0/2/0/2 | 0 | 34 | 41170 | 4925/11331/24868 | 11 | 139.1 | 17385 | 17389 | 0 | 0 | 2 |
| r1-k2-definition-burst | sales-append | 4 | 4/0/0/0 | 4 | 0/0/4/6/0 | 0 | 9 | 8366 | 3018/5333/0 | 8 | 42.7 | 5337 | 5337 | 0 | 0 | 0 |
| r1-k2-definition-burst | returns-append | 4 | 4/0/0/0 | 8 | 0/0/4/6/0 | 0 | 11 | 10623 | 2812/7796/0 | 12 | 68.4 | 8551 | 8552 | 0 | 0 | 0 |
| r1-k2-definition-burst | catalog-append | 2 | 2/0/0/0 | 6 | 0/0/2/2/0 | 0 | 4 | 2819 | 1/2811/0 | 8 | 22.5 | 2812 | 2817 | 0 | 0 | 0 |
| r1-k2-definition-burst | v2 | 4 | 0/4/0/0 | 4 | 0/0/2/4/0 | 0 | 37 | 41386 | 4774/11781/24777 | 8 | 118.8 | 16766 | 16770 | 0 | 0 | 11 |
| r1-k2-schema-burst | sales-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 5 | 0 | 0 | 0 |
| r1-k2-schema-burst | returns-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 4 | 0 | 0 | 0 |
| r1-k2-schema-burst | catalog-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 2 | 0.0 | 5 | 5 | 0 | 0 | 0 |
| r1-k2-schema-burst | v2 | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 4 | 32 | 0 | 0 |
| r1-k2-revoke-burst | sales-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 4 | 0 | 4 | 32 |
| r1-k2-revoke-burst | returns-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 5 | 5 | 0 | 4 | 32 |
| r1-k2-revoke-burst | catalog-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 0 | 2 | 16 |
| r1-k2-revoke-burst | v2 | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 4 | 0 | 0 | 32 |
| r1-k4-condition-burst | sales-append | 7 | 7/0/0/0 | 7 | 7/4/3/0/3 | 0 | 5 | 7066 | 1449/5600/0 | 14 | 44.8 | 4130 | 5604 | 0 | 0 | 0 |
| r1-k4-condition-burst | returns-append | 7 | 7/0/0/0 | 5 | 10/1/3/0/3 | 0 | 3 | 2139 | 0/2133/0 | 12 | 17.1 | 2133 | 2137 | 0 | 0 | 0 |
| r1-k4-condition-burst | catalog-append | 4 | 4/0/0/0 | 4 | 4/0/4/0/0 | 0 | 3 | 2698 | 0/2691/0 | 8 | 21.5 | 2691 | 2695 | 0 | 0 | 0 |
| r1-k4-condition-burst | v2 | 7 | 0/7/0/0 | 3 | 4/2/2/0/3 | 2 | 43 | 42761 | 4591/6676/31430 | 10 | 91.4 | 10929 | 11889 | 0 | 0 | 16 |
| r1-k4-condition-scope-burst | sales-append | 7 | 7/0/0/0 | 9 | 7/0/7/0/3 | 0 | 7 | 12341 | 1437/10885/0 | 16 | 87.1 | 5509 | 5513 | 0 | 0 | 0 |
| r1-k4-condition-scope-burst | returns-append | 7 | 7/0/0/0 | 14 | 10/0/4/0/3 | 0 | 7 | 5960 | 1570/4378/0 | 21 | 35.0 | 2254 | 2258 | 0 | 0 | 0 |
| r1-k4-condition-scope-burst | catalog-append | 4 | 4/0/0/0 | 4 | 4/0/4/0/0 | 0 | 3 | 2639 | 0/2633/0 | 8 | 21.1 | 2633 | 2636 | 0 | 0 | 0 |
| r1-k4-condition-scope-burst | v2 | 7 | 0/7/0/0 | 5 | 4/0/4/0/3 | 0 | 56 | 61724 | 4639/17678/39327 | 12 | 151.1 | 11766 | 16804 | 0 | 0 | 22 |
| r1-k4-definition-burst | sales-append | 7 | 7/0/0/0 | 9 | 0/0/7/10/0 | 0 | 12 | 14296 | 3147/11127/0 | 16 | 89.1 | 5809 | 5812 | 0 | 0 | 0 |
| r1-k4-definition-burst | returns-append | 7 | 7/0/0/0 | 12 | 0/0/7/10/0 | 0 | 14 | 12757 | 2818/9920/0 | 19 | 85.3 | 6484 | 8576 | 0 | 0 | 0 |
| r1-k4-definition-burst | catalog-append | 4 | 4/0/0/0 | 4 | 0/0/4/4/0 | 0 | 4 | 2918 | 2/2910/0 | 8 | 23.3 | 2912 | 2915 | 0 | 0 | 0 |
| r1-k4-definition-burst | v2 | 7 | 0/7/0/0 | 13 | 0/0/4/7/0 | 0 | 56 | 61956 | 5244/17311/39324 | 20 | 215.5 | 11009 | 17719 | 0 | 0 | 12 |
| r1-k4-schema-burst | sales-append | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 3 | 4 | 0 | 0 | 0 |
| r1-k4-schema-burst | returns-append | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 3 | 5 | 0 | 0 | 0 |
| r1-k4-schema-burst | catalog-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 3 | 5 | 0 | 0 | 0 |
| r1-k4-schema-burst | v2 | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 3 | 5 | 56 | 0 | 0 |
| r1-k4-revoke-burst | sales-append | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 3 | 4 | 0 | 7 | 56 |
| r1-k4-revoke-burst | returns-append | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 7 | 0.0 | 4 | 5 | 0 | 7 | 56 |
| r1-k4-revoke-burst | catalog-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 3 | 4 | 0 | 4 | 32 |
| r1-k4-revoke-burst | v2 | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 3 | 4 | 0 | 0 | 56 |
| r1-k6-condition-burst | sales-append | 9 | 9/0/0/0 | 3 | 9/4/5/0/3 | 0 | 5 | 6622 | 1391/5220/0 | 12 | 41.8 | 1407 | 5223 | 0 | 0 | 0 |
| r1-k6-condition-burst | returns-append | 8 | 8/0/0/0 | 8 | 11/3/2/0/3 | 0 | 5 | 3610 | 1538/2065/0 | 16 | 16.5 | 527 | 2069 | 0 | 0 | 0 |
| r1-k6-condition-burst | catalog-append | 5 | 5/0/0/0 | 4 | 5/1/4/0/0 | 0 | 3 | 2545 | 0/2539/0 | 9 | 20.3 | 4 | 2543 | 0 | 0 | 0 |
| r1-k6-condition-burst | v2 | 8 | 0/8/0/0 | 5 | 5/3/2/0/3 | 3 | 43 | 41827 | 4941/5953/30879 | 13 | 92.1 | 766 | 11511 | 0 | 0 | 21 |
| r1-k6-condition-scope-burst | sales-append | 9 | 9/0/0/0 | 15 | 9/0/9/0/3 | 0 | 9 | 17199 | 1399/15780/0 | 24 | 126.3 | 5250 | 5305 | 0 | 0 | 0 |
| r1-k6-condition-scope-burst | returns-append | 8 | 8/0/0/0 | 13 | 11/0/5/0/3 | 0 | 7 | 5734 | 1544/4178/0 | 21 | 33.4 | 2076 | 2106 | 0 | 0 | 0 |
| r1-k6-condition-scope-burst | catalog-append | 5 | 5/0/0/0 | 11 | 5/0/5/0/0 | 0 | 5 | 5247 | 0/5238/0 | 16 | 41.9 | 2571 | 2674 | 0 | 0 | 0 |
| r1-k6-condition-scope-burst | v2 | 8 | 0/8/0/0 | 10 | 5/0/5/0/3 | 0 | 67 | 82808 | 4861/27490/50365 | 18 | 239.0 | 11441 | 17160 | 0 | 0 | 9 |
| r1-k6-definition-burst | sales-append | 9 | 9/0/0/0 | 15 | 0/0/9/12/0 | 0 | 19 | 22043 | 5840/16175/0 | 24 | 151.7 | 5281 | 8468 | 0 | 0 | 0 |
| r1-k6-definition-burst | returns-append | 8 | 8/0/0/0 | 19 | 0/0/8/11/0 | 0 | 24 | 22494 | 5697/16769/0 | 27 | 132.0 | 6556 | 8439 | 0 | 0 | 0 |
| r1-k6-definition-burst | catalog-append | 5 | 5/0/0/0 | 11 | 0/0/5/5/0 | 0 | 7 | 5509 | 2/5499/0 | 16 | 44.0 | 2631 | 2877 | 0 | 0 | 0 |
| r1-k6-definition-burst | v2 | 8 | 0/8/0/0 | 10 | 0/0/5/8/0 | 0 | 72 | 82167 | 4513/27974/49584 | 18 | 237.3 | 11616 | 16434 | 0 | 0 | 10 |
| r1-k6-schema-burst | sales-append | 9 | 9/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 9 | 0.0 | 0 | 6 | 0 | 0 | 0 |
| r1-k6-schema-burst | returns-append | 8 | 8/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 8 | 0.0 | 0 | 6 | 0 | 0 | 0 |
| r1-k6-schema-burst | catalog-append | 5 | 5/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 5 | 0.0 | 0 | 6 | 0 | 0 | 0 |
| r1-k6-schema-burst | v2 | 8 | 8/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 8 | 0.0 | 0 | 6 | 64 | 0 | 0 |
| r1-k6-revoke-burst | sales-append | 9 | 0/0/0/9 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 9 | 0.0 | 0 | 4 | 0 | 9 | 72 |
| r1-k6-revoke-burst | returns-append | 8 | 0/0/0/8 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 5 | 0 | 8 | 64 |
| r1-k6-revoke-burst | catalog-append | 5 | 0/0/0/5 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 5 | 0.0 | 0 | 5 | 0 | 5 | 40 |
| r1-k6-revoke-burst | v2 | 8 | 0/0/0/8 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 5 | 0 | 0 | 64 |

### 到达方式：staggered

| 组 | 变化 | 维护次数 | 刷新/修复/未恢复/重提 | 合并的并发维护 | 条件：跳过/复用/执行/强制/交给关联经验 | 修复复用 | DB 查询 | DB ms | 其中 守卫与关联检查/指标检查/修复 ms | 等待维护的使用 | 等待总时长 s | p95 ms | 最大 ms | 过期使用 | 误撤销 | 不可用 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1-k1-condition-staggered | sales-append | 2 | 2/0/0/0 | 0 | 2/2/0/0/1 | 0 | 3 | 1453 | 1446/0/0 | 2 | 1.5 | 0 | 1453 | 0 | 0 | 0 |
| r1-k1-condition-staggered | returns-append | 2 | 2/0/0/0 | 0 | 3/0/1/0/1 | 0 | 3 | 1988 | 0/1982/0 | 2 | 2.0 | 0 | 1986 | 0 | 0 | 0 |
| r1-k1-condition-staggered | catalog-append | 1 | 1/0/0/0 | 0 | 1/0/1/0/0 | 0 | 3 | 2823 | 0/2817/0 | 1 | 2.8 | 0 | 2821 | 0 | 0 | 0 |
| r1-k1-condition-staggered | v2 | 2 | 0/2/0/0 | 0 | 1/0/1/0/1 | 0 | 18 | 13064 | 2016/5163/5863 | 2 | 13.1 | 0 | 10777 | 0 | 0 | 0 |
| r1-k1-condition-scope-staggered | sales-append | 2 | 2/0/0/0 | 0 | 2/0/2/0/1 | 0 | 7 | 11917 | 1261/10644/0 | 2 | 11.9 | 3 | 6559 | 0 | 0 | 0 |
| r1-k1-condition-scope-staggered | returns-append | 2 | 2/0/0/0 | 0 | 3/0/1/0/1 | 0 | 5 | 3423 | 1517/1898/0 | 2 | 3.4 | 2 | 1901 | 0 | 0 | 0 |
| r1-k1-condition-scope-staggered | catalog-append | 1 | 1/0/0/0 | 0 | 1/0/1/0/0 | 0 | 3 | 2588 | 0/2583/0 | 1 | 2.6 | 0 | 2586 | 0 | 0 | 0 |
| r1-k1-condition-scope-staggered | v2 | 2 | 0/2/0/0 | 0 | 1/0/1/0/1 | 0 | 25 | 26778 | 4559/10424/11770 | 2 | 26.8 | 0 | 16004 | 0 | 0 | 0 |
| r1-k1-definition-staggered | sales-append | 2 | 2/0/0/0 | 0 | 0/0/2/3/0 | 0 | 11 | 13521 | 2764/10744/0 | 2 | 13.5 | 3 | 8128 | 0 | 0 | 0 |
| r1-k1-definition-staggered | returns-append | 2 | 2/0/0/0 | 0 | 0/0/2/3/0 | 0 | 11 | 9901 | 2729/7159/0 | 2 | 9.9 | 2 | 7996 | 0 | 0 | 0 |
| r1-k1-definition-staggered | catalog-append | 1 | 1/0/0/0 | 0 | 0/0/1/1/0 | 0 | 4 | 2589 | 1/2584/0 | 1 | 2.6 | 0 | 2588 | 0 | 0 | 0 |
| r1-k1-definition-staggered | v2 | 2 | 0/2/0/0 | 0 | 0/0/1/2/0 | 0 | 26 | 27016 | 4676/10484/11829 | 2 | 27.0 | 0 | 16164 | 0 | 0 | 0 |
| r1-k1-schema-staggered | sales-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k1-schema-staggered | returns-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k1-schema-staggered | catalog-append | 1 | 1/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 1 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k1-schema-staggered | v2 | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 2 | 0.0 | 0 | 4 | 16 | 0 | 0 |
| r1-k1-revoke-staggered | sales-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 2 | 16 |
| r1-k1-revoke-staggered | returns-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 2 | 16 |
| r1-k1-revoke-staggered | catalog-append | 1 | 0/0/0/1 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 1 | 0.0 | 0 | 3 | 0 | 1 | 8 |
| r1-k1-revoke-staggered | v2 | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 0 | 16 |
| r1-k2-condition-staggered | sales-append | 4 | 4/0/0/0 | 0 | 4/3/1/0/2 | 0 | 3 | 5207 | 0/5200/0 | 4 | 5.2 | 0 | 5205 | 0 | 0 | 0 |
| r1-k2-condition-staggered | returns-append | 4 | 4/0/0/0 | 0 | 6/1/1/0/2 | 0 | 3 | 1877 | 0/1873/0 | 4 | 1.9 | 0 | 1873 | 0 | 0 | 0 |
| r1-k2-condition-staggered | catalog-append | 2 | 2/0/0/0 | 0 | 2/1/1/0/0 | 0 | 3 | 2559 | 0/2553/0 | 2 | 2.6 | 0 | 2554 | 0 | 0 | 0 |
| r1-k2-condition-staggered | v2 | 4 | 0/4/0/0 | 0 | 2/2/0/0/2 | 2 | 23 | 10154 | 5806/598/3728 | 4 | 10.2 | 40 | 9818 | 0 | 0 | 0 |
| r1-k2-condition-scope-staggered | sales-append | 4 | 4/0/0/0 | 0 | 4/0/4/0/2 | 0 | 11 | 22396 | 1278/21101/0 | 4 | 22.4 | 5246 | 6516 | 0 | 0 | 0 |
| r1-k2-condition-scope-staggered | returns-append | 4 | 4/0/0/0 | 0 | 6/0/2/0/2 | 0 | 7 | 5270 | 1496/3763/0 | 4 | 5.3 | 4 | 1899 | 0 | 0 | 0 |
| r1-k2-condition-scope-staggered | catalog-append | 2 | 2/0/0/0 | 0 | 2/0/2/0/0 | 0 | 5 | 5271 | 0/5263/0 | 2 | 5.3 | 3 | 2665 | 0 | 0 | 0 |
| r1-k2-condition-scope-staggered | v2 | 4 | 0/4/0/0 | 0 | 2/0/2/0/2 | 0 | 39 | 40755 | 4581/20742/15391 | 4 | 40.8 | 5511 | 15959 | 0 | 0 | 0 |
| r1-k2-definition-staggered | sales-append | 4 | 4/0/0/0 | 0 | 0/0/4/6/0 | 0 | 21 | 29120 | 6179/22908/0 | 4 | 29.1 | 5518 | 9289 | 0 | 0 | 0 |
| r1-k2-definition-staggered | returns-append | 4 | 4/0/0/0 | 0 | 0/0/4/6/0 | 0 | 21 | 20285 | 5651/14606/0 | 4 | 20.3 | 1955 | 8193 | 0 | 0 | 0 |
| r1-k2-definition-staggered | catalog-append | 2 | 2/0/0/0 | 0 | 0/0/2/2/0 | 0 | 7 | 5329 | 2/5319/0 | 2 | 5.3 | 3 | 2734 | 0 | 0 | 0 |
| r1-k2-definition-staggered | v2 | 4 | 0/4/0/0 | 0 | 0/0/2/4/0 | 0 | 45 | 46671 | 7506/21236/17880 | 4 | 46.7 | 8413 | 16346 | 0 | 0 | 0 |
| r1-k2-schema-staggered | sales-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k2-schema-staggered | returns-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k2-schema-staggered | catalog-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k2-schema-staggered | v2 | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 32 | 0 | 0 |
| r1-k2-revoke-staggered | sales-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 4 | 32 |
| r1-k2-revoke-staggered | returns-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 2 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 4 | 32 |
| r1-k2-revoke-staggered | catalog-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 2 | 0.0 | 0 | 4 | 0 | 2 | 16 |
| r1-k2-revoke-staggered | v2 | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 0 | 32 |
| r1-k4-condition-staggered | sales-append | 7 | 7/0/0/0 | 0 | 7/6/1/0/3 | 0 | 3 | 5332 | 0/5325/0 | 7 | 5.3 | 0 | 5329 | 0 | 0 | 0 |
| r1-k4-condition-staggered | returns-append | 7 | 7/0/0/0 | 0 | 10/3/1/0/3 | 0 | 3 | 1958 | 0/1953/0 | 7 | 2.0 | 0 | 1956 | 0 | 0 | 0 |
| r1-k4-condition-staggered | catalog-append | 4 | 4/0/0/0 | 0 | 4/3/1/0/0 | 0 | 3 | 2712 | 0/2707/0 | 4 | 2.7 | 0 | 2710 | 0 | 0 | 0 |
| r1-k4-condition-staggered | v2 | 7 | 0/7/0/0 | 0 | 4/3/1/0/3 | 3 | 32 | 15028 | 3198/5918/5885 | 7 | 15.0 | 43 | 10883 | 0 | 0 | 0 |
| r1-k4-condition-scope-staggered | sales-append | 7 | 7/0/0/0 | 0 | 7/0/7/0/3 | 0 | 17 | 38945 | 1319/37599/0 | 7 | 38.9 | 5246 | 6698 | 0 | 0 | 0 |
| r1-k4-condition-scope-staggered | returns-append | 7 | 7/0/0/0 | 0 | 10/0/4/0/3 | 0 | 11 | 9209 | 1547/7647/0 | 7 | 9.2 | 2 | 1936 | 0 | 0 | 0 |
| r1-k4-condition-scope-staggered | catalog-append | 4 | 4/0/0/0 | 0 | 4/0/4/0/0 | 0 | 9 | 11195 | 0/11181/0 | 4 | 11.2 | 3 | 2879 | 0 | 0 | 0 |
| r1-k4-condition-scope-staggered | v2 | 7 | 0/7/0/0 | 0 | 4/0/4/0/3 | 0 | 62 | 72586 | 4857/37482/30182 | 7 | 72.6 | 5669 | 16819 | 0 | 0 | 0 |
| r1-k4-definition-staggered | sales-append | 7 | 7/0/0/0 | 0 | 0/0/7/10/0 | 0 | 34 | 45734 | 8373/37321/0 | 7 | 45.7 | 5286 | 8221 | 0 | 0 | 0 |
| r1-k4-definition-staggered | returns-append | 7 | 7/0/0/0 | 0 | 0/0/7/10/0 | 0 | 34 | 32591 | 8504/24046/0 | 7 | 32.6 | 1936 | 8482 | 0 | 0 | 0 |
| r1-k4-definition-staggered | catalog-append | 4 | 4/0/0/0 | 0 | 0/0/4/4/0 | 0 | 13 | 11085 | 3/11067/0 | 4 | 11.1 | 3 | 2872 | 0 | 0 | 0 |
| r1-k4-definition-staggered | v2 | 7 | 0/7/0/0 | 0 | 0/0/4/7/0 | 0 | 74 | 65351 | 8325/37484/19461 | 7 | 65.4 | 8610 | 12303 | 0 | 0 | 0 |
| r1-k4-schema-staggered | sales-append | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k4-schema-staggered | returns-append | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k4-schema-staggered | catalog-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 4 | 0 | 0 | 0 |
| r1-k4-schema-staggered | v2 | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 56 | 0 | 0 |
| r1-k4-revoke-staggered | sales-append | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 7 | 0.0 | 0 | 4 | 0 | 7 | 56 |
| r1-k4-revoke-staggered | returns-append | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 7 | 56 |
| r1-k4-revoke-staggered | catalog-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 4 | 32 |
| r1-k4-revoke-staggered | v2 | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 0 | 56 |
| r1-k6-condition-staggered | sales-append | 9 | 9/0/0/0 | 0 | 9/8/1/0/3 | 0 | 3 | 5232 | 0/5226/0 | 9 | 5.2 | 0 | 5227 | 0 | 0 | 0 |
| r1-k6-condition-staggered | returns-append | 8 | 8/0/0/0 | 0 | 11/4/1/0/3 | 0 | 3 | 1941 | 0/1936/0 | 8 | 1.9 | 0 | 1937 | 0 | 0 | 0 |
| r1-k6-condition-staggered | catalog-append | 5 | 5/0/0/0 | 0 | 5/4/1/0/0 | 0 | 3 | 2616 | 0/2611/0 | 5 | 2.6 | 0 | 2612 | 0 | 0 | 0 |
| r1-k6-condition-staggered | v2 | 8 | 0/8/0/0 | 0 | 5/5/0/0/3 | 5 | 32 | 12719 | 5836/963/5896 | 8 | 12.7 | 0 | 12008 | 0 | 0 | 0 |
| r1-k6-condition-scope-staggered | sales-append | 9 | 9/0/0/0 | 0 | 9/0/9/0/3 | 0 | 21 | 48909 | 1273/47603/0 | 9 | 48.9 | 5236 | 6525 | 0 | 0 | 0 |
| r1-k6-condition-scope-staggered | returns-append | 8 | 8/0/0/0 | 0 | 11/0/5/0/3 | 0 | 13 | 11034 | 1516/9499/0 | 8 | 11.0 | 3 | 1938 | 0 | 0 | 0 |
| r1-k6-condition-scope-staggered | catalog-append | 5 | 5/0/0/0 | 0 | 5/0/5/0/0 | 0 | 11 | 13032 | 0/13016/0 | 5 | 13.0 | 3 | 2647 | 0 | 0 | 0 |
| r1-k6-condition-scope-staggered | v2 | 8 | 0/8/0/0 | 0 | 5/0/5/0/3 | 0 | 71 | 69979 | 4580/40729/24596 | 8 | 70.0 | 0 | 15957 | 0 | 0 | 0 |
| r1-k6-definition-staggered | sales-append | 9 | 9/0/0/0 | 0 | 0/0/9/12/0 | 0 | 40 | 57181 | 8487/48635/0 | 9 | 57.2 | 5287 | 8296 | 0 | 0 | 0 |
| r1-k6-definition-staggered | returns-append | 8 | 8/0/0/0 | 0 | 0/0/8/11/0 | 0 | 37 | 33743 | 8264/25437/0 | 8 | 33.7 | 4 | 8161 | 0 | 0 | 0 |
| r1-k6-definition-staggered | catalog-append | 5 | 5/0/0/0 | 0 | 0/0/5/5/0 | 0 | 16 | 12994 | 4/12974/0 | 5 | 13.0 | 3 | 2635 | 0 | 0 | 0 |
| r1-k6-definition-staggered | v2 | 8 | 0/8/0/0 | 0 | 0/0/5/8/0 | 0 | 84 | 75795 | 10294/40636/24782 | 8 | 75.8 | 0 | 16139 | 0 | 0 | 0 |
| r1-k6-schema-staggered | sales-append | 9 | 9/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 9 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k6-schema-staggered | returns-append | 8 | 8/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k6-schema-staggered | catalog-append | 5 | 5/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 5 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k6-schema-staggered | v2 | 8 | 8/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 3 | 64 | 0 | 0 |
| r1-k6-revoke-staggered | sales-append | 9 | 0/0/0/9 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 9 | 0.0 | 0 | 3 | 0 | 9 | 72 |
| r1-k6-revoke-staggered | returns-append | 8 | 0/0/0/8 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 3 | 0 | 8 | 64 |
| r1-k6-revoke-staggered | catalog-append | 5 | 0/0/0/5 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 5 | 0.0 | 0 | 3 | 0 | 5 | 40 |
| r1-k6-revoke-staggered | v2 | 8 | 0/0/0/8 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 3 | 0 | 0 | 64 |

## 3. 逐写入撤销组的恢复（重新提交）

重新提交代替重新学习与提炼，不含 LLM 成本；真实的重新提炼成本见 metricbench 的 *-relearn 阶段。

| 组 | 变化 | 重新提交 | 通过门槛 | 耗时 s | DB ms |
|---|---|---|---|---|---|
| r1-k1-revoke-staggered | none | 0 | 0 | 0.0 | 0 |
| r1-k1-revoke-staggered | sales-append | 2 | 2 | 12.1 | 12065 |
| r1-k1-revoke-staggered | returns-append | 2 | 2 | 9.0 | 8950 |
| r1-k1-revoke-staggered | catalog-append | 1 | 1 | 2.7 | 2669 |
| r1-k1-revoke-staggered | v2 | 2 | 0 | 13.3 | 13334 |
| r1-k1-revoke-burst | none | 0 | 0 | 0.0 | 0 |
| r1-k1-revoke-burst | sales-append | 2 | 2 | 12.1 | 12095 |
| r1-k1-revoke-burst | returns-append | 2 | 2 | 8.9 | 8870 |
| r1-k1-revoke-burst | catalog-append | 1 | 1 | 2.7 | 2677 |
| r1-k1-revoke-burst | v2 | 2 | 0 | 13.5 | 13465 |
| r1-k2-revoke-staggered | none | 0 | 0 | 0.0 | 0 |
| r1-k2-revoke-staggered | sales-append | 4 | 4 | 23.6 | 23564 |
| r1-k2-revoke-staggered | returns-append | 4 | 4 | 16.7 | 16695 |
| r1-k2-revoke-staggered | catalog-append | 2 | 2 | 5.5 | 5505 |
| r1-k2-revoke-staggered | v2 | 4 | 0 | 10.6 | 10599 |
| r1-k2-revoke-burst | none | 0 | 0 | 0.0 | 0 |
| r1-k2-revoke-burst | sales-append | 4 | 4 | 23.4 | 23410 |
| r1-k2-revoke-burst | returns-append | 4 | 4 | 16.8 | 16778 |
| r1-k2-revoke-burst | catalog-append | 2 | 2 | 5.4 | 5363 |
| r1-k2-revoke-burst | v2 | 4 | 0 | 10.9 | 10890 |
| r1-k4-revoke-staggered | none | 0 | 0 | 0.0 | 0 |
| r1-k4-revoke-staggered | sales-append | 7 | 7 | 39.4 | 39424 |
| r1-k4-revoke-staggered | returns-append | 7 | 7 | 25.9 | 25914 |
| r1-k4-revoke-staggered | catalog-append | 4 | 4 | 10.8 | 10799 |
| r1-k4-revoke-staggered | v2 | 7 | 0 | 13.3 | 13338 |
| r1-k4-revoke-burst | none | 0 | 0 | 0.0 | 0 |
| r1-k4-revoke-burst | sales-append | 7 | 7 | 39.2 | 39198 |
| r1-k4-revoke-burst | returns-append | 7 | 7 | 25.8 | 25770 |
| r1-k4-revoke-burst | catalog-append | 4 | 4 | 10.4 | 10376 |
| r1-k4-revoke-burst | v2 | 7 | 0 | 13.5 | 13499 |
| r1-k6-revoke-staggered | none | 0 | 0 | 0.0 | 0 |
| r1-k6-revoke-staggered | sales-append | 9 | 9 | 49.9 | 49844 |
| r1-k6-revoke-staggered | returns-append | 8 | 8 | 27.7 | 27680 |
| r1-k6-revoke-staggered | catalog-append | 5 | 5 | 12.9 | 12896 |
| r1-k6-revoke-staggered | v2 | 8 | 0 | 10.4 | 10412 |
| r1-k6-revoke-burst | none | 0 | 0 | 0.0 | 0 |
| r1-k6-revoke-burst | sales-append | 9 | 9 | 49.9 | 49891 |
| r1-k6-revoke-burst | returns-append | 8 | 8 | 27.8 | 27741 |
| r1-k6-revoke-burst | catalog-append | 5 | 5 | 12.9 | 12893 |
| r1-k6-revoke-burst | v2 | 8 | 0 | 10.5 | 10479 |

## 4. 按共享度汇总

四次变化合计，多轮取平均。条件执行＝访问数据库的条件检查（含在途合并与定义级强制重跑的关联守卫，不含交给关联经验的）；DB ms 为中间层全部查询；相对 definition＝同一共享度、同一到达方式下 DB ms 之比。共享度越低，condition 与 definition 应越接近。

### 到达方式：burst

| 共享度 k | 口径数 | 组 | 条件执行 | DB ms | 等待 s | 相对 definition |
|---|---|---|---|---|---|---|
| 1 | 4 | revoke | 0 | 11 | 0.0 | 0.00 |
| 1 | 4 | schema | 0 | 12 | 0.0 | 0.00 |
| 1 | 4 | definition | 15 | 48987 | 253.3 | 1.00 |
| 1 | 4 | condition-scope | 5 | 41274 | 220.6 | 0.84 |
| 1 | 4 | condition | 4 | 35755 | 176.2 | 0.73 |
| 2 | 8 | revoke | 0 | 12 | 0.0 | 0.00 |
| 2 | 8 | schema | 0 | 14 | 0.0 | 0.00 |
| 2 | 8 | definition | 30 | 63194 | 252.4 | 1.00 |
| 2 | 8 | condition-scope | 10 | 53994 | 218.2 | 0.85 |
| 2 | 8 | condition | 8 | 48424 | 173.1 | 0.77 |
| 4 | 15 | revoke | 0 | 12 | 0.0 | 0.00 |
| 4 | 15 | schema | 0 | 11 | 0.0 | 0.00 |
| 4 | 15 | definition | 53 | 91927 | 413.2 | 1.00 |
| 4 | 15 | condition-scope | 19 | 82664 | 294.3 | 0.90 |
| 4 | 15 | condition | 12 | 54664 | 174.8 | 0.59 |
| 6 | 19 | revoke | 0 | 12 | 0.0 | 0.00 |
| 6 | 19 | schema | 0 | 15 | 0.0 | 0.00 |
| 6 | 19 | definition | 63 | 132214 | 565.1 | 1.00 |
| 6 | 19 | condition-scope | 24 | 110987 | 440.6 | 0.84 |
| 6 | 19 | condition | 13 | 54605 | 170.7 | 0.41 |

### 到达方式：staggered

| 共享度 k | 口径数 | 组 | 条件执行 | DB ms | 等待 s | 相对 definition |
|---|---|---|---|---|---|---|
| 1 | 4 | revoke | 0 | 11 | 0.0 | 0.00 |
| 1 | 4 | schema | 0 | 13 | 0.0 | 0.00 |
| 1 | 4 | definition | 15 | 53028 | 53.0 | 1.00 |
| 1 | 4 | condition-scope | 5 | 44706 | 44.7 | 0.84 |
| 1 | 4 | condition | 3 | 19327 | 19.3 | 0.36 |
| 2 | 8 | revoke | 0 | 11 | 0.0 | 0.00 |
| 2 | 8 | schema | 0 | 11 | 0.0 | 0.00 |
| 2 | 8 | definition | 30 | 101404 | 101.4 | 1.00 |
| 2 | 8 | condition-scope | 10 | 73692 | 73.7 | 0.73 |
| 2 | 8 | condition | 3 | 19797 | 19.8 | 0.20 |
| 4 | 15 | revoke | 0 | 12 | 0.0 | 0.00 |
| 4 | 15 | schema | 0 | 13 | 0.0 | 0.00 |
| 4 | 15 | definition | 53 | 154761 | 154.8 | 1.00 |
| 4 | 15 | condition-scope | 19 | 131935 | 131.9 | 0.85 |
| 4 | 15 | condition | 4 | 25030 | 25.0 | 0.16 |
| 6 | 19 | revoke | 0 | 11 | 0.0 | 0.00 |
| 6 | 19 | schema | 0 | 12 | 0.0 | 0.00 |
| 6 | 19 | definition | 63 | 179712 | 179.7 | 1.00 |
| 6 | 19 | condition-scope | 24 | 142954 | 142.9 | 0.80 |
| 6 | 19 | condition | 3 | 22508 | 22.5 | 0.13 |

## 说明

- 各组的条件、受限修复、回归与门槛相同；定义级组同样享有同一定义的维护合并与相同检查 SQL 的在途合并。
- 条件级的收益来自三处：读到的表未变化的条件不查（condition-scope 只有这一项）；同一条件在同一版本上的结论跨定义复用（含关联守卫与修复回归，以及键列更少的已通过键唯一性蕴含的条件）；同表同键的粒度修复复用。definition 与 condition-scope 之差是重验范围，condition-scope 与 condition 之差是跨定义复用。单个定义、条件不共享、或写入涉及定义的全部条件时，几种重验应当接近。
- burst 下定义级组的相同检查可能恰好同时在途而被合并，收益会小于 staggered。
- 判题器与数据、口径同源；探测题只有一个月份，过期与误撤销按这一题判定。
- 各组在同一数据库上顺序运行，不清空 OS/PG 缓存，执行顺序按轮换。
