# 维护方式对照（不调用 LLM）

口径数随共享度 k 变化（k = 6 为全部 19 条），8 个 Agent；每次变化后每个 Agent 把全部口径各用一次。组名 r轮次-k共享度-维护方式-到达方式。本报告是描述性结果，不作显著性声明。协议见 docs/metric-experience-protocol.md。

## 1. 准入（各组相同）

| 组 | 晋升 | 耗时 s | DB 查询 | DB ms |
|---|---|---|---|---|
| r1-k1-revoke-staggered | 4 | 64.1 | 32 | 19381 |
| r1-k1-revoke-burst | 4 | 61.8 | 32 | 19149 |
| r1-k1-schema-staggered | 4 | 27.3 | 32 | 19705 |
| r1-k1-schema-burst | 4 | 26.6 | 32 | 19119 |
| r1-k1-definition-staggered | 4 | 75.8 | 32 | 19902 |
| r1-k1-definition-burst | 4 | 60.3 | 32 | 18573 |
| r1-k1-condition-scope-staggered | 4 | 72.3 | 32 | 19023 |
| r1-k1-condition-scope-burst | 4 | 54.8 | 32 | 19233 |
| r1-k1-condition-staggered | 4 | 45.1 | 32 | 19026 |
| r1-k1-condition-burst | 4 | 47.1 | 32 | 19410 |
| r1-k2-revoke-staggered | 8 | 99.9 | 49 | 35037 |
| r1-k2-revoke-burst | 8 | 100.6 | 49 | 34052 |
| r1-k2-schema-staggered | 8 | 46.4 | 49 | 34837 |
| r1-k2-schema-burst | 8 | 45.6 | 49 | 34354 |
| r1-k2-definition-staggered | 8 | 145.6 | 49 | 37143 |
| r1-k2-definition-burst | 8 | 81.6 | 49 | 34618 |
| r1-k2-condition-scope-staggered | 8 | 122.3 | 49 | 34309 |
| r1-k2-condition-scope-burst | 8 | 71.8 | 49 | 34720 |
| r1-k2-condition-staggered | 8 | 71.4 | 50 | 37769 |
| r1-k2-condition-burst | 8 | 67.3 | 49 | 33972 |
| r1-k4-revoke-staggered | 15 | 161.9 | 78 | 59267 |
| r1-k4-revoke-burst | 15 | 161.8 | 78 | 59242 |
| r1-k4-schema-staggered | 15 | 75.8 | 78 | 58880 |
| r1-k4-schema-burst | 15 | 76.4 | 78 | 59842 |
| r1-k4-definition-staggered | 15 | 239.9 | 78 | 59950 |
| r1-k4-definition-burst | 15 | 130.5 | 78 | 58676 |
| r1-k4-condition-scope-staggered | 15 | 207.7 | 78 | 59776 |
| r1-k4-condition-scope-burst | 15 | 114.6 | 78 | 58773 |
| r1-k4-condition-staggered | 15 | 101.8 | 78 | 59644 |
| r1-k4-condition-burst | 15 | 102.7 | 78 | 62225 |
| r1-k6-revoke-staggered | 19 | 191.6 | 94 | 74378 |
| r1-k6-revoke-burst | 19 | 188.7 | 94 | 74723 |
| r1-k6-schema-staggered | 19 | 91.7 | 94 | 73926 |
| r1-k6-schema-burst | 19 | 92.0 | 94 | 73960 |
| r1-k6-definition-staggered | 19 | 272.8 | 94 | 73979 |
| r1-k6-definition-burst | 19 | 160.6 | 94 | 73553 |
| r1-k6-condition-scope-staggered | 19 | 238.9 | 94 | 73415 |
| r1-k6-condition-scope-burst | 19 | 151.1 | 94 | 74155 |
| r1-k6-condition-staggered | 19 | 113.6 | 94 | 73421 |
| r1-k6-condition-burst | 19 | 112.8 | 94 | 73506 |

## 2. 每次变化后的维护、可用性与正确性

维护结果：刷新＝待验证后重查通过；修复＝条件不成立、正式撤销后受限修复并通过回归；未恢复＝撤销后修复失败或不在修复范围；重提＝逐写入撤销，只能重新提炼。条件（跳过/复用/执行/强制/交给关联经验）：跳过＝读到的表未变化；复用＝同一版本上已有同一条件或蕴含它的结论；执行＝本次访问数据库（含在途合并）；强制＝定义级重跑关联守卫；交给关联经验＝由关联经验按其守卫涉及的表决定是否重跑。DB 为中间层在该次变化后全部使用期间的查询（维护之外只有版本读取）。等待＝本次使用执行了维护或合并进了别人的维护。过期使用＝返回为有效但答错探测题；误撤销＝变化前的修订仍然正确却被撤销；不可用＝返回撤销或候选状态。

### 到达方式：burst

| 组 | 变化 | 维护次数 | 刷新/修复/未恢复/重提 | 合并的并发维护 | 条件：跳过/复用/执行/强制/交给关联经验 | 修复复用 | DB 查询 | DB ms | 其中 守卫与关联检查/指标检查/修复 ms | 等待维护的使用 | 等待总时长 s | p95 ms | 最大 ms | 过期使用 | 误撤销 | 不可用 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1-k1-revoke-burst | sales-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 0 | 2 | 16 |
| r1-k1-revoke-burst | returns-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 0 | 2 | 16 |
| r1-k1-revoke-burst | catalog-append | 1 | 0/0/0/1 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 1 | 0.0 | 4 | 4 | 0 | 1 | 8 |
| r1-k1-revoke-burst | v2 | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 0 | 0 | 16 |
| r1-k1-schema-burst | sales-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 4 | 4 | 0 | 0 | 0 |
| r1-k1-schema-burst | returns-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 0 | 0 | 0 |
| r1-k1-schema-burst | catalog-append | 1 | 1/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 1 | 0.0 | 3 | 3 | 0 | 0 | 0 |
| r1-k1-schema-burst | v2 | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 16 | 0 | 0 |
| r1-k1-definition-burst | sales-append | 2 | 2/0/0/0 | 6 | 0/0/2/3/0 | 0 | 9 | 8537 | 2706/5819/0 | 8 | 46.7 | 5834 | 5834 | 0 | 0 | 0 |
| r1-k1-definition-burst | returns-append | 2 | 2/0/0/0 | 13 | 0/0/2/3/0 | 0 | 11 | 10781 | 3096/7665/0 | 15 | 70.7 | 6890 | 8829 | 0 | 0 | 0 |
| r1-k1-definition-burst | catalog-append | 1 | 1/0/0/0 | 7 | 0/0/1/1/0 | 0 | 4 | 2936 | 2/2928/0 | 8 | 23.4 | 2930 | 2934 | 0 | 0 | 0 |
| r1-k1-definition-burst | v2 | 2 | 0/2/0/0 | 6 | 0/0/1/2/0 | 0 | 26 | 28540 | 4735/11352/12422 | 8 | 122.7 | 16411 | 16415 | 0 | 0 | 2 |
| r1-k1-condition-scope-burst | sales-append | 2 | 2/0/0/0 | 6 | 2/0/2/0/1 | 0 | 5 | 7349 | 1281/6059/0 | 8 | 48.6 | 6075 | 6075 | 0 | 0 | 0 |
| r1-k1-condition-scope-burst | returns-append | 2 | 2/0/0/0 | 7 | 3/0/1/0/1 | 0 | 5 | 3614 | 1677/1924/0 | 9 | 15.4 | 1932 | 1932 | 0 | 0 | 0 |
| r1-k1-condition-scope-burst | catalog-append | 1 | 1/0/0/0 | 7 | 1/0/1/0/0 | 0 | 3 | 2923 | 0/2917/0 | 8 | 23.3 | 2918 | 2921 | 0 | 0 | 0 |
| r1-k1-condition-scope-burst | v2 | 2 | 0/2/0/0 | 8 | 1/0/1/0/1 | 0 | 24 | 28680 | 4987/11432/12235 | 10 | 141.5 | 17682 | 17685 | 0 | 0 | 0 |
| r1-k1-condition-burst | sales-append | 2 | 2/0/0/0 | 9 | 2/1/1/0/1 | 0 | 5 | 7240 | 1251/5979/0 | 11 | 47.9 | 5994 | 5994 | 0 | 0 | 0 |
| r1-k1-condition-burst | returns-append | 2 | 2/0/0/0 | 7 | 3/0/1/0/1 | 0 | 5 | 3677 | 1710/1952/0 | 9 | 15.7 | 1961 | 1961 | 0 | 0 | 0 |
| r1-k1-condition-burst | catalog-append | 1 | 1/0/0/0 | 7 | 1/0/1/0/0 | 0 | 3 | 2882 | 0/2876/0 | 8 | 23.0 | 2876 | 2880 | 0 | 0 | 0 |
| r1-k1-condition-burst | v2 | 2 | 0/2/0/0 | 8 | 1/0/1/0/1 | 0 | 21 | 18659 | 5148/5394/8096 | 10 | 77.0 | 9622 | 9625 | 0 | 0 | 0 |
| r1-k2-revoke-burst | sales-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 2 | 0/0/0 | 4 | 0.0 | 3 | 3 | 0 | 4 | 32 |
| r1-k2-revoke-burst | returns-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 4 | 0 | 4 | 32 |
| r1-k2-revoke-burst | catalog-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 3 | 0 | 2 | 16 |
| r1-k2-revoke-burst | v2 | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 3 | 3 | 0 | 0 | 32 |
| r1-k2-schema-burst | sales-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 4 | 0 | 0 | 0 |
| r1-k2-schema-burst | returns-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 4 | 0 | 0 | 0 |
| r1-k2-schema-burst | catalog-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 3 | 4 | 0 | 0 | 0 |
| r1-k2-schema-burst | v2 | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 4 | 32 | 0 | 0 |
| r1-k2-definition-burst | sales-append | 4 | 4/0/0/0 | 4 | 0/0/4/6/0 | 0 | 9 | 8849 | 3212/5619/0 | 8 | 45.0 | 5624 | 5624 | 0 | 0 | 0 |
| r1-k2-definition-burst | returns-append | 4 | 4/0/0/0 | 8 | 0/0/4/6/0 | 0 | 11 | 11752 | 2954/8780/0 | 12 | 75.2 | 9400 | 9400 | 0 | 0 | 0 |
| r1-k2-definition-burst | catalog-append | 2 | 2/0/0/0 | 6 | 0/0/2/2/0 | 0 | 4 | 3092 | 2/3083/0 | 8 | 24.7 | 3085 | 3089 | 0 | 0 | 0 |
| r1-k2-definition-burst | v2 | 4 | 0/4/0/0 | 4 | 0/0/2/4/0 | 0 | 37 | 41625 | 4690/11945/24934 | 8 | 119.5 | 16825 | 16829 | 0 | 0 | 8 |
| r1-k2-condition-scope-burst | sales-append | 4 | 4/0/0/0 | 4 | 4/0/4/0/2 | 0 | 5 | 7206 | 1420/5774/0 | 8 | 46.2 | 5777 | 5777 | 0 | 0 | 0 |
| r1-k2-condition-scope-burst | returns-append | 4 | 4/0/0/0 | 8 | 6/0/2/0/2 | 0 | 5 | 3644 | 1550/2085/0 | 12 | 16.7 | 2086 | 2089 | 0 | 0 | 0 |
| r1-k2-condition-scope-burst | catalog-append | 2 | 2/0/0/0 | 6 | 2/0/2/0/0 | 0 | 3 | 2610 | 0/2604/0 | 8 | 20.8 | 2604 | 2607 | 0 | 0 | 0 |
| r1-k2-condition-scope-burst | v2 | 4 | 0/4/0/0 | 7 | 2/0/2/0/2 | 0 | 33 | 32915 | 5113/11921/15832 | 11 | 124.2 | 15531 | 15532 | 0 | 0 | 5 |
| r1-k2-condition-burst | sales-append | 4 | 4/0/0/0 | 9 | 4/2/2/0/2 | 0 | 5 | 6722 | 1421/5288/0 | 13 | 42.3 | 3850 | 5292 | 0 | 0 | 0 |
| r1-k2-condition-burst | returns-append | 4 | 4/0/0/0 | 8 | 6/0/2/0/2 | 0 | 5 | 3697 | 1561/2127/0 | 12 | 17.0 | 2127 | 2131 | 0 | 0 | 0 |
| r1-k2-condition-burst | catalog-append | 2 | 2/0/0/0 | 6 | 2/0/2/0/0 | 0 | 3 | 2731 | 0/2724/0 | 8 | 21.8 | 2725 | 2728 | 0 | 0 | 0 |
| r1-k2-condition-burst | v2 | 4 | 0/4/0/0 | 7 | 2/0/2/0/2 | 0 | 32 | 35436 | 4911/5549/24929 | 11 | 92.6 | 11576 | 11581 | 0 | 0 | 5 |
| r1-k4-revoke-burst | sales-append | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 3 | 4 | 0 | 7 | 56 |
| r1-k4-revoke-burst | returns-append | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 2 | 0/0/0 | 7 | 0.0 | 3 | 4 | 0 | 7 | 56 |
| r1-k4-revoke-burst | catalog-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 4 | 5 | 0 | 4 | 32 |
| r1-k4-revoke-burst | v2 | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 4 | 5 | 0 | 0 | 56 |
| r1-k4-schema-burst | sales-append | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 3 | 4 | 0 | 0 | 0 |
| r1-k4-schema-burst | returns-append | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 3 | 4 | 0 | 0 | 0 |
| r1-k4-schema-burst | catalog-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 3 | 5 | 0 | 0 | 0 |
| r1-k4-schema-burst | v2 | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 7 | 0.0 | 4 | 6 | 56 | 0 | 0 |
| r1-k4-definition-burst | sales-append | 7 | 7/0/0/0 | 9 | 0/0/7/10/0 | 0 | 12 | 14589 | 3149/11417/0 | 16 | 91.4 | 5893 | 5896 | 0 | 0 | 0 |
| r1-k4-definition-burst | returns-append | 7 | 7/0/0/0 | 12 | 0/0/7/10/0 | 0 | 14 | 13149 | 2945/10184/0 | 19 | 86.7 | 6367 | 8678 | 0 | 0 | 0 |
| r1-k4-definition-burst | catalog-append | 4 | 4/0/0/0 | 4 | 0/0/4/4/0 | 0 | 4 | 2872 | 1/2864/0 | 8 | 22.9 | 2866 | 2869 | 0 | 0 | 0 |
| r1-k4-definition-burst | v2 | 7 | 0/7/0/0 | 13 | 0/0/4/7/0 | 0 | 56 | 65750 | 4993/17136/43543 | 20 | 230.6 | 11405 | 17418 | 0 | 0 | 4 |
| r1-k4-condition-scope-burst | sales-append | 7 | 7/0/0/0 | 9 | 7/0/7/0/3 | 0 | 7 | 11978 | 1374/10589/0 | 16 | 84.7 | 5370 | 5373 | 0 | 0 | 0 |
| r1-k4-condition-scope-burst | returns-append | 7 | 7/0/0/0 | 14 | 10/0/4/0/3 | 0 | 7 | 5704 | 1557/4135/0 | 21 | 33.1 | 2084 | 2088 | 0 | 0 | 0 |
| r1-k4-condition-scope-burst | catalog-append | 4 | 4/0/0/0 | 4 | 4/0/4/0/0 | 0 | 3 | 2707 | 0/2701/0 | 8 | 21.6 | 2701 | 2704 | 0 | 0 | 0 |
| r1-k4-condition-scope-burst | v2 | 7 | 0/7/0/0 | 5 | 4/0/4/0/3 | 0 | 56 | 61183 | 4583/17640/38872 | 12 | 149.9 | 11798 | 16583 | 0 | 0 | 22 |
| r1-k4-condition-burst | sales-append | 7 | 7/0/0/0 | 7 | 7/4/3/0/3 | 0 | 5 | 6739 | 1385/5341/0 | 14 | 42.7 | 3939 | 5346 | 0 | 0 | 0 |
| r1-k4-condition-burst | returns-append | 7 | 7/0/0/0 | 5 | 10/1/3/0/3 | 0 | 3 | 2100 | 0/2093/0 | 12 | 16.8 | 2093 | 2098 | 0 | 0 | 0 |
| r1-k4-condition-burst | catalog-append | 4 | 4/0/0/0 | 4 | 4/0/4/0/0 | 0 | 3 | 3225 | 0/3219/0 | 8 | 25.8 | 3219 | 3222 | 0 | 0 | 0 |
| r1-k4-condition-burst | v2 | 7 | 0/7/0/0 | 3 | 4/2/2/0/3 | 2 | 43 | 44723 | 4989/7365/32300 | 10 | 96.4 | 11410 | 12658 | 0 | 0 | 17 |
| r1-k6-revoke-burst | sales-append | 9 | 0/0/0/9 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 9 | 0.0 | 0 | 6 | 0 | 9 | 72 |
| r1-k6-revoke-burst | returns-append | 8 | 0/0/0/8 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 4 | 0 | 8 | 64 |
| r1-k6-revoke-burst | catalog-append | 5 | 0/0/0/5 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 5 | 0.0 | 0 | 5 | 0 | 5 | 40 |
| r1-k6-revoke-burst | v2 | 8 | 0/0/0/8 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 8 | 0.0 | 0 | 5 | 0 | 0 | 64 |
| r1-k6-schema-burst | sales-append | 9 | 9/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 9 | 0.0 | 0 | 7 | 0 | 0 | 0 |
| r1-k6-schema-burst | returns-append | 8 | 8/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 8 | 0.0 | 0 | 7 | 0 | 0 | 0 |
| r1-k6-schema-burst | catalog-append | 5 | 5/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 5 | 0.0 | 0 | 6 | 0 | 0 | 0 |
| r1-k6-schema-burst | v2 | 8 | 8/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 5 | 64 | 0 | 0 |
| r1-k6-definition-burst | sales-append | 9 | 9/0/0/0 | 15 | 0/0/9/12/0 | 0 | 19 | 22291 | 5797/16464/0 | 24 | 153.9 | 5297 | 8681 | 0 | 0 | 0 |
| r1-k6-definition-burst | returns-append | 8 | 8/0/0/0 | 19 | 0/0/8/11/0 | 0 | 24 | 22454 | 5750/16675/0 | 27 | 131.1 | 6290 | 8206 | 0 | 0 | 0 |
| r1-k6-definition-burst | catalog-append | 5 | 5/0/0/0 | 11 | 0/0/5/5/0 | 0 | 7 | 5425 | 2/5414/0 | 16 | 43.3 | 2652 | 2772 | 0 | 0 | 0 |
| r1-k6-definition-burst | v2 | 8 | 0/8/0/0 | 10 | 0/0/5/8/0 | 0 | 71 | 64436 | 4653/28019/31672 | 18 | 199.5 | 9447 | 14527 | 0 | 0 | 14 |
| r1-k6-condition-scope-burst | sales-append | 9 | 9/0/0/0 | 15 | 9/0/9/0/3 | 0 | 9 | 17367 | 1425/15921/0 | 24 | 127.4 | 5314 | 5317 | 0 | 0 | 0 |
| r1-k6-condition-scope-burst | returns-append | 8 | 8/0/0/0 | 13 | 11/0/5/0/3 | 0 | 7 | 5719 | 1556/4150/0 | 21 | 33.2 | 2044 | 2111 | 0 | 0 | 0 |
| r1-k6-condition-scope-burst | catalog-append | 5 | 5/0/0/0 | 11 | 5/0/5/0/0 | 0 | 5 | 5199 | 0/5191/0 | 16 | 41.5 | 2595 | 2603 | 0 | 0 | 0 |
| r1-k6-condition-scope-burst | v2 | 8 | 0/8/0/0 | 10 | 5/0/5/0/3 | 0 | 66 | 82380 | 4916/27676/49696 | 18 | 241.3 | 11542 | 17443 | 0 | 0 | 10 |
| r1-k6-condition-burst | sales-append | 9 | 9/0/0/0 | 3 | 9/4/5/0/3 | 0 | 5 | 6640 | 1373/5254/0 | 12 | 42.0 | 1390 | 5258 | 0 | 0 | 0 |
| r1-k6-condition-burst | returns-append | 8 | 8/0/0/0 | 8 | 11/3/2/0/3 | 0 | 5 | 3628 | 1541/2078/0 | 16 | 16.6 | 537 | 2082 | 0 | 0 | 0 |
| r1-k6-condition-burst | catalog-append | 5 | 5/0/0/0 | 4 | 5/1/4/0/0 | 0 | 3 | 2623 | 0/2617/0 | 9 | 20.9 | 5 | 2621 | 0 | 0 | 0 |
| r1-k6-condition-burst | v2 | 8 | 0/8/0/0 | 5 | 5/3/2/0/3 | 3 | 43 | 41904 | 4977/6056/30818 | 13 | 92.2 | 737 | 11549 | 0 | 0 | 22 |

### 到达方式：staggered

| 组 | 变化 | 维护次数 | 刷新/修复/未恢复/重提 | 合并的并发维护 | 条件：跳过/复用/执行/强制/交给关联经验 | 修复复用 | DB 查询 | DB ms | 其中 守卫与关联检查/指标检查/修复 ms | 等待维护的使用 | 等待总时长 s | p95 ms | 最大 ms | 过期使用 | 误撤销 | 不可用 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| r1-k1-revoke-staggered | sales-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 2 | 16 |
| r1-k1-revoke-staggered | returns-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 2 | 16 |
| r1-k1-revoke-staggered | catalog-append | 1 | 0/0/0/1 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 1 | 0.0 | 0 | 3 | 0 | 1 | 8 |
| r1-k1-revoke-staggered | v2 | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 0 | 16 |
| r1-k1-schema-staggered | sales-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k1-schema-staggered | returns-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 2 | 0.0 | 0 | 4 | 0 | 0 | 0 |
| r1-k1-schema-staggered | catalog-append | 1 | 1/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 1 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k1-schema-staggered | v2 | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 16 | 0 | 0 |
| r1-k1-definition-staggered | sales-append | 2 | 2/0/0/0 | 0 | 0/0/2/3/0 | 0 | 11 | 13476 | 2734/10727/0 | 2 | 13.5 | 4 | 8124 | 0 | 0 | 0 |
| r1-k1-definition-staggered | returns-append | 2 | 2/0/0/0 | 0 | 0/0/2/3/0 | 0 | 11 | 10016 | 2725/7278/0 | 2 | 10.0 | 3 | 8082 | 0 | 0 | 0 |
| r1-k1-definition-staggered | catalog-append | 1 | 1/0/0/0 | 0 | 0/0/1/1/0 | 0 | 4 | 2665 | 1/2659/0 | 1 | 2.7 | 0 | 2663 | 0 | 0 | 0 |
| r1-k1-definition-staggered | v2 | 2 | 0/2/0/0 | 0 | 0/0/1/2/0 | 0 | 26 | 22542 | 2735/11601/8179 | 2 | 22.6 | 0 | 12660 | 0 | 0 | 0 |
| r1-k1-condition-scope-staggered | sales-append | 2 | 2/0/0/0 | 0 | 2/0/2/0/1 | 0 | 7 | 12073 | 1244/10817/0 | 2 | 12.1 | 3 | 6669 | 0 | 0 | 0 |
| r1-k1-condition-scope-staggered | returns-append | 2 | 2/0/0/0 | 0 | 3/0/1/0/1 | 0 | 5 | 3498 | 1531/1959/0 | 2 | 3.5 | 3 | 1962 | 0 | 0 | 0 |
| r1-k1-condition-scope-staggered | catalog-append | 1 | 1/0/0/0 | 0 | 1/0/1/0/0 | 0 | 3 | 2656 | 0/2651/0 | 1 | 2.7 | 0 | 2654 | 0 | 0 | 0 |
| r1-k1-condition-scope-staggered | v2 | 2 | 0/2/0/0 | 0 | 1/0/1/0/1 | 0 | 25 | 27660 | 4631/10860/12138 | 2 | 27.7 | 0 | 16542 | 0 | 0 | 0 |
| r1-k1-condition-staggered | sales-append | 2 | 2/0/0/0 | 0 | 2/2/0/0/1 | 0 | 3 | 1262 | 1256/0/0 | 2 | 1.3 | 0 | 1263 | 0 | 0 | 0 |
| r1-k1-condition-staggered | returns-append | 2 | 2/0/0/0 | 0 | 3/0/1/0/1 | 0 | 3 | 2005 | 0/2000/0 | 2 | 2.0 | 0 | 2003 | 0 | 0 | 0 |
| r1-k1-condition-staggered | catalog-append | 1 | 1/0/0/0 | 0 | 1/0/1/0/0 | 0 | 3 | 2617 | 0/2612/0 | 1 | 2.6 | 0 | 2615 | 0 | 0 | 0 |
| r1-k1-condition-staggered | v2 | 2 | 0/2/0/0 | 0 | 1/0/1/0/1 | 0 | 18 | 13136 | 1944/5233/5934 | 2 | 13.1 | 0 | 10924 | 0 | 0 | 0 |
| r1-k2-revoke-staggered | sales-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 4 | 0.0 | 0 | 4 | 0 | 4 | 32 |
| r1-k2-revoke-staggered | returns-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 2 | 0/0/0 | 4 | 0.0 | 0 | 2 | 0 | 4 | 32 |
| r1-k2-revoke-staggered | catalog-append | 2 | 0/0/0/2 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 3 | 0 | 2 | 16 |
| r1-k2-revoke-staggered | v2 | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 0 | 32 |
| r1-k2-schema-staggered | sales-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 4 | 0/0/0 | 4 | 0.0 | 0 | 4 | 0 | 0 | 0 |
| r1-k2-schema-staggered | returns-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k2-schema-staggered | catalog-append | 2 | 2/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 2 | 0.0 | 0 | 4 | 0 | 0 | 0 |
| r1-k2-schema-staggered | v2 | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 32 | 0 | 0 |
| r1-k2-definition-staggered | sales-append | 4 | 4/0/0/0 | 0 | 0/0/4/6/0 | 0 | 21 | 28268 | 5713/22526/0 | 4 | 28.3 | 5381 | 8479 | 0 | 0 | 0 |
| r1-k2-definition-staggered | returns-append | 4 | 4/0/0/0 | 0 | 0/0/4/6/0 | 0 | 21 | 20096 | 5582/14483/0 | 4 | 20.1 | 1926 | 8146 | 0 | 0 | 0 |
| r1-k2-definition-staggered | catalog-append | 2 | 2/0/0/0 | 0 | 0/0/2/2/0 | 0 | 7 | 5237 | 2/5227/0 | 2 | 5.2 | 3 | 2634 | 0 | 0 | 0 |
| r1-k2-definition-staggered | v2 | 4 | 0/4/0/0 | 0 | 0/0/2/4/0 | 0 | 45 | 42802 | 7483/21570/13702 | 4 | 42.8 | 8661 | 16526 | 0 | 0 | 0 |
| r1-k2-condition-scope-staggered | sales-append | 4 | 4/0/0/0 | 0 | 4/0/4/0/2 | 0 | 11 | 22717 | 1299/21401/0 | 4 | 22.7 | 5268 | 6635 | 0 | 0 | 0 |
| r1-k2-condition-scope-staggered | returns-append | 4 | 4/0/0/0 | 0 | 6/0/2/0/2 | 0 | 7 | 5543 | 1630/3902/0 | 4 | 5.5 | 3 | 1982 | 0 | 0 | 0 |
| r1-k2-condition-scope-staggered | catalog-append | 2 | 2/0/0/0 | 0 | 2/0/2/0/0 | 0 | 5 | 5274 | 0/5265/0 | 2 | 5.3 | 3 | 2654 | 0 | 0 | 0 |
| r1-k2-condition-scope-staggered | v2 | 4 | 0/4/0/0 | 0 | 2/0/2/0/2 | 0 | 39 | 43222 | 4611/20925/17641 | 4 | 43.2 | 5545 | 16048 | 0 | 0 | 0 |
| r1-k2-condition-staggered | sales-append | 4 | 4/0/0/0 | 0 | 4/3/1/0/2 | 0 | 3 | 5352 | 0/5346/0 | 4 | 5.4 | 0 | 5349 | 0 | 0 | 0 |
| r1-k2-condition-staggered | returns-append | 4 | 4/0/0/0 | 0 | 6/1/1/0/2 | 0 | 3 | 1907 | 0/1902/0 | 4 | 1.9 | 0 | 1902 | 0 | 0 | 0 |
| r1-k2-condition-staggered | catalog-append | 2 | 2/0/0/0 | 0 | 2/1/1/0/0 | 0 | 3 | 2644 | 0/2639/0 | 2 | 2.6 | 0 | 2639 | 0 | 0 | 0 |
| r1-k2-condition-staggered | v2 | 4 | 0/4/0/0 | 0 | 2/2/0/0/2 | 2 | 23 | 12551 | 5986/609/5931 | 4 | 12.6 | 40 | 12211 | 0 | 0 | 0 |
| r1-k4-revoke-staggered | sales-append | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 7 | 56 |
| r1-k4-revoke-staggered | returns-append | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 7 | 56 |
| r1-k4-revoke-staggered | catalog-append | 4 | 0/0/0/4 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 4 | 32 |
| r1-k4-revoke-staggered | v2 | 7 | 0/0/0/7 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 0 | 56 |
| r1-k4-schema-staggered | sales-append | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k4-schema-staggered | returns-append | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k4-schema-staggered | catalog-append | 4 | 4/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 4 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k4-schema-staggered | v2 | 7 | 7/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 7 | 0.0 | 0 | 4 | 56 | 0 | 0 |
| r1-k4-definition-staggered | sales-append | 7 | 7/0/0/0 | 0 | 0/0/7/10/0 | 0 | 34 | 46462 | 8435/37979/0 | 7 | 46.4 | 5361 | 8257 | 0 | 0 | 0 |
| r1-k4-definition-staggered | returns-append | 7 | 7/0/0/0 | 0 | 0/0/7/10/0 | 0 | 34 | 32556 | 8638/23872/0 | 7 | 32.5 | 1916 | 8326 | 0 | 0 | 0 |
| r1-k4-definition-staggered | catalog-append | 4 | 4/0/0/0 | 0 | 0/0/4/4/0 | 0 | 13 | 10990 | 4/10971/0 | 4 | 11.0 | 3 | 2827 | 0 | 0 | 0 |
| r1-k4-definition-staggered | v2 | 7 | 0/7/0/0 | 0 | 0/0/4/7/0 | 0 | 74 | 72244 | 10392/36565/25202 | 7 | 72.3 | 8482 | 16146 | 0 | 0 | 0 |
| r1-k4-condition-scope-staggered | sales-append | 7 | 7/0/0/0 | 0 | 7/0/7/0/3 | 0 | 17 | 38923 | 1287/37608/0 | 7 | 38.9 | 5315 | 6637 | 0 | 0 | 0 |
| r1-k4-condition-scope-staggered | returns-append | 7 | 7/0/0/0 | 0 | 10/0/4/0/3 | 0 | 11 | 9212 | 1508/7687/0 | 7 | 9.2 | 3 | 2035 | 0 | 0 | 0 |
| r1-k4-condition-scope-staggered | catalog-append | 4 | 4/0/0/0 | 0 | 4/0/4/0/0 | 0 | 9 | 10585 | 0/10571/0 | 4 | 10.6 | 3 | 2669 | 0 | 0 | 0 |
| r1-k4-condition-scope-staggered | v2 | 7 | 0/7/0/0 | 0 | 4/0/4/0/3 | 0 | 62 | 71280 | 4669/36918/29622 | 7 | 71.3 | 5548 | 16240 | 0 | 0 | 0 |
| r1-k4-condition-staggered | sales-append | 7 | 7/0/0/0 | 0 | 7/6/1/0/3 | 0 | 3 | 5428 | 0/5422/0 | 7 | 5.4 | 0 | 5425 | 0 | 0 | 0 |
| r1-k4-condition-staggered | returns-append | 7 | 7/0/0/0 | 0 | 10/3/1/0/3 | 0 | 3 | 1941 | 0/1936/0 | 7 | 1.9 | 0 | 1939 | 0 | 0 | 0 |
| r1-k4-condition-staggered | catalog-append | 4 | 4/0/0/0 | 0 | 4/3/1/0/0 | 0 | 3 | 2611 | 0/2605/0 | 4 | 2.6 | 0 | 2609 | 0 | 0 | 0 |
| r1-k4-condition-staggered | v2 | 7 | 0/7/0/0 | 0 | 4/3/1/0/3 | 3 | 32 | 15089 | 3211/5961/5889 | 7 | 15.1 | 40 | 10956 | 0 | 0 | 0 |
| r1-k6-revoke-staggered | sales-append | 9 | 0/0/0/9 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 9 | 0.0 | 0 | 4 | 0 | 9 | 72 |
| r1-k6-revoke-staggered | returns-append | 8 | 0/0/0/8 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 3 | 0 | 8 | 64 |
| r1-k6-revoke-staggered | catalog-append | 5 | 0/0/0/5 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 5 | 0.0 | 0 | 3 | 0 | 5 | 40 |
| r1-k6-revoke-staggered | v2 | 8 | 0/0/0/8 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 4 | 0 | 0 | 64 |
| r1-k6-schema-staggered | sales-append | 9 | 9/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 9 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k6-schema-staggered | returns-append | 8 | 8/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k6-schema-staggered | catalog-append | 5 | 5/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 5 | 0.0 | 0 | 3 | 0 | 0 | 0 |
| r1-k6-schema-staggered | v2 | 8 | 8/0/0/0 | 0 | 0/0/0/0/0 | 0 | 1 | 3 | 0/0/0 | 8 | 0.0 | 0 | 3 | 64 | 0 | 0 |
| r1-k6-definition-staggered | sales-append | 9 | 9/0/0/0 | 0 | 0/0/9/12/0 | 0 | 40 | 55894 | 8259/47581/0 | 9 | 55.9 | 5206 | 8138 | 0 | 0 | 0 |
| r1-k6-definition-staggered | returns-append | 8 | 8/0/0/0 | 0 | 0/0/8/11/0 | 0 | 37 | 33750 | 8333/25374/0 | 8 | 33.7 | 4 | 8134 | 0 | 0 | 0 |
| r1-k6-definition-staggered | catalog-append | 5 | 5/0/0/0 | 0 | 0/0/5/5/0 | 0 | 16 | 12947 | 4/12926/0 | 5 | 12.9 | 3 | 2666 | 0 | 0 | 0 |
| r1-k6-definition-staggered | v2 | 8 | 0/8/0/0 | 0 | 0/0/5/8/0 | 0 | 84 | 78086 | 10326/40987/26686 | 8 | 78.1 | 0 | 15956 | 0 | 0 | 0 |
| r1-k6-condition-scope-staggered | sales-append | 9 | 9/0/0/0 | 0 | 9/0/9/0/3 | 0 | 21 | 49112 | 1316/47759/0 | 9 | 49.1 | 5259 | 6627 | 0 | 0 | 0 |
| r1-k6-condition-scope-staggered | returns-append | 8 | 8/0/0/0 | 0 | 11/0/5/0/3 | 0 | 13 | 10996 | 1514/9462/0 | 8 | 11.0 | 3 | 1932 | 0 | 0 | 0 |
| r1-k6-condition-scope-staggered | catalog-append | 5 | 5/0/0/0 | 0 | 5/0/5/0/0 | 0 | 11 | 12919 | 0/12903/0 | 5 | 12.9 | 3 | 2629 | 0 | 0 | 0 |
| r1-k6-condition-scope-staggered | v2 | 8 | 0/8/0/0 | 0 | 5/0/5/0/3 | 0 | 71 | 74692 | 4595/41033/28988 | 8 | 74.7 | 0 | 16043 | 0 | 0 | 0 |
| r1-k6-condition-staggered | sales-append | 9 | 9/0/0/0 | 0 | 9/8/1/0/3 | 0 | 3 | 5234 | 0/5228/0 | 9 | 5.2 | 0 | 5229 | 0 | 0 | 0 |
| r1-k6-condition-staggered | returns-append | 8 | 8/0/0/0 | 0 | 11/4/1/0/3 | 0 | 3 | 1948 | 0/1942/0 | 8 | 1.9 | 0 | 1942 | 0 | 0 | 0 |
| r1-k6-condition-staggered | catalog-append | 5 | 5/0/0/0 | 0 | 5/4/1/0/0 | 0 | 3 | 2581 | 0/2576/0 | 5 | 2.6 | 0 | 2576 | 0 | 0 | 0 |
| r1-k6-condition-staggered | v2 | 8 | 0/8/0/0 | 0 | 5/5/0/0/3 | 5 | 32 | 12865 | 5891/1046/5901 | 8 | 12.9 | 0 | 12076 | 0 | 0 | 0 |

## 3. 逐写入撤销组的恢复（重新提交）

重新提交代替重新学习与提炼，不含 LLM 成本；真实的重新提炼成本见 metricbench 的 *-relearn 阶段。

| 组 | 变化 | 重新提交 | 通过门槛 | 耗时 s | DB ms |
|---|---|---|---|---|---|
| r1-k1-revoke-staggered | none | 0 | 0 | 0.0 | 0 |
| r1-k1-revoke-staggered | sales-append | 2 | 2 | 12.5 | 12456 |
| r1-k1-revoke-staggered | returns-append | 2 | 2 | 9.0 | 9037 |
| r1-k1-revoke-staggered | catalog-append | 1 | 1 | 2.7 | 2726 |
| r1-k1-revoke-staggered | v2 | 2 | 0 | 14.0 | 13979 |
| r1-k1-revoke-burst | none | 0 | 0 | 0.0 | 0 |
| r1-k1-revoke-burst | sales-append | 2 | 2 | 12.6 | 12567 |
| r1-k1-revoke-burst | returns-append | 2 | 2 | 9.4 | 9361 |
| r1-k1-revoke-burst | catalog-append | 1 | 1 | 3.0 | 3026 |
| r1-k1-revoke-burst | v2 | 2 | 0 | 11.5 | 11503 |
| r1-k2-revoke-staggered | none | 0 | 0 | 0.0 | 0 |
| r1-k2-revoke-staggered | sales-append | 4 | 4 | 23.5 | 23452 |
| r1-k2-revoke-staggered | returns-append | 4 | 4 | 16.5 | 16510 |
| r1-k2-revoke-staggered | catalog-append | 2 | 2 | 5.3 | 5264 |
| r1-k2-revoke-staggered | v2 | 4 | 0 | 10.7 | 10686 |
| r1-k2-revoke-burst | none | 0 | 0 | 0.0 | 0 |
| r1-k2-revoke-burst | sales-append | 4 | 4 | 24.4 | 24377 |
| r1-k2-revoke-burst | returns-append | 4 | 4 | 16.7 | 16727 |
| r1-k2-revoke-burst | catalog-append | 2 | 2 | 5.6 | 5570 |
| r1-k2-revoke-burst | v2 | 4 | 0 | 10.9 | 10859 |
| r1-k4-revoke-staggered | none | 0 | 0 | 0.0 | 0 |
| r1-k4-revoke-staggered | sales-append | 7 | 7 | 39.6 | 39575 |
| r1-k4-revoke-staggered | returns-append | 7 | 7 | 26.1 | 26054 |
| r1-k4-revoke-staggered | catalog-append | 4 | 4 | 10.7 | 10678 |
| r1-k4-revoke-staggered | v2 | 7 | 0 | 13.5 | 13521 |
| r1-k4-revoke-burst | none | 0 | 0 | 0.0 | 0 |
| r1-k4-revoke-burst | sales-append | 7 | 7 | 39.7 | 39644 |
| r1-k4-revoke-burst | returns-append | 7 | 7 | 25.9 | 25859 |
| r1-k4-revoke-burst | catalog-append | 4 | 4 | 10.5 | 10514 |
| r1-k4-revoke-burst | v2 | 7 | 0 | 13.4 | 13406 |
| r1-k6-revoke-staggered | none | 0 | 0 | 0.0 | 0 |
| r1-k6-revoke-staggered | sales-append | 9 | 9 | 50.9 | 50862 |
| r1-k6-revoke-staggered | returns-append | 8 | 8 | 27.9 | 27922 |
| r1-k6-revoke-staggered | catalog-append | 5 | 5 | 13.9 | 13855 |
| r1-k6-revoke-staggered | v2 | 8 | 0 | 10.4 | 10446 |
| r1-k6-revoke-burst | none | 0 | 0 | 0.0 | 0 |
| r1-k6-revoke-burst | sales-append | 9 | 9 | 50.1 | 50072 |
| r1-k6-revoke-burst | returns-append | 8 | 8 | 27.7 | 27736 |
| r1-k6-revoke-burst | catalog-append | 5 | 5 | 14.3 | 14309 |
| r1-k6-revoke-burst | v2 | 8 | 0 | 6.4 | 6404 |

## 4. 按共享度汇总

四次变化合计，多轮取平均。条件执行＝访问数据库的条件检查（含在途合并）；DB ms 为中间层全部查询；相对 definition＝同一共享度、同一到达方式下 DB ms 之比。共享度越低，condition 与 definition 应越接近。

### 到达方式：burst

| 共享度 k | 口径数 | 组 | 条件执行 | DB ms | 等待 s | 相对 definition |
|---|---|---|---|---|---|---|
| 1 | 4 | revoke | 0 | 11 | 0.0 | 0.00 |
| 1 | 4 | schema | 0 | 12 | 0.0 | 0.00 |
| 1 | 4 | definition | 6 | 50794 | 263.5 | 1.00 |
| 1 | 4 | condition-scope | 5 | 42566 | 228.8 | 0.84 |
| 1 | 4 | condition | 4 | 32458 | 163.6 | 0.64 |
| 2 | 8 | revoke | 0 | 11 | 0.0 | 0.00 |
| 2 | 8 | schema | 0 | 12 | 0.0 | 0.00 |
| 2 | 8 | definition | 12 | 65319 | 264.3 | 1.00 |
| 2 | 8 | condition-scope | 10 | 46374 | 208.0 | 0.71 |
| 2 | 8 | condition | 8 | 48586 | 173.8 | 0.74 |
| 4 | 15 | revoke | 0 | 12 | 0.0 | 0.00 |
| 4 | 15 | schema | 0 | 12 | 0.0 | 0.00 |
| 4 | 15 | definition | 22 | 96359 | 431.5 | 1.00 |
| 4 | 15 | condition-scope | 19 | 81573 | 289.4 | 0.85 |
| 4 | 15 | condition | 12 | 56787 | 181.7 | 0.59 |
| 6 | 19 | revoke | 0 | 13 | 0.0 | 0.00 |
| 6 | 19 | schema | 0 | 15 | 0.0 | 0.00 |
| 6 | 19 | definition | 27 | 114606 | 527.9 | 1.00 |
| 6 | 19 | condition-scope | 24 | 110665 | 443.5 | 0.97 |
| 6 | 19 | condition | 13 | 54795 | 171.8 | 0.48 |

### 到达方式：staggered

| 共享度 k | 口径数 | 组 | 条件执行 | DB ms | 等待 s | 相对 definition |
|---|---|---|---|---|---|---|
| 1 | 4 | revoke | 0 | 11 | 0.0 | 0.00 |
| 1 | 4 | schema | 0 | 13 | 0.0 | 0.00 |
| 1 | 4 | definition | 6 | 48698 | 48.7 | 1.00 |
| 1 | 4 | condition-scope | 5 | 45887 | 45.9 | 0.94 |
| 1 | 4 | condition | 3 | 19020 | 19.0 | 0.39 |
| 2 | 8 | revoke | 0 | 11 | 0.0 | 0.00 |
| 2 | 8 | schema | 0 | 14 | 0.0 | 0.00 |
| 2 | 8 | definition | 12 | 96403 | 96.4 | 1.00 |
| 2 | 8 | condition-scope | 10 | 76756 | 76.7 | 0.80 |
| 2 | 8 | condition | 3 | 22454 | 22.5 | 0.23 |
| 4 | 15 | revoke | 0 | 12 | 0.0 | 0.00 |
| 4 | 15 | schema | 0 | 12 | 0.0 | 0.00 |
| 4 | 15 | definition | 22 | 162252 | 162.2 | 1.00 |
| 4 | 15 | condition-scope | 19 | 130000 | 130.0 | 0.80 |
| 4 | 15 | condition | 4 | 25069 | 25.1 | 0.15 |
| 6 | 19 | revoke | 0 | 13 | 0.0 | 0.00 |
| 6 | 19 | schema | 0 | 12 | 0.0 | 0.00 |
| 6 | 19 | definition | 27 | 180678 | 180.7 | 1.00 |
| 6 | 19 | condition-scope | 24 | 147718 | 147.7 | 0.82 |
| 6 | 19 | condition | 3 | 22628 | 22.6 | 0.13 |

## 说明

- 各组的条件、受限修复、回归与门槛相同；定义级组同样享有同一定义的维护合并与相同检查 SQL 的在途合并。
- 条件级的收益来自三处：读到的表未变化的条件不查（condition-scope 只有这一项）；同一条件在同一版本上的结论跨定义复用（含关联守卫与修复回归，以及键列更少的已通过键唯一性蕴含的条件）；同表同键的粒度修复复用。definition 与 condition-scope 之差是重验范围，condition-scope 与 condition 之差是跨定义复用。单个定义、条件不共享、或写入涉及定义的全部条件时，几种重验应当接近。
- burst 下定义级组的相同检查可能恰好同时在途而被合并，收益会小于 staggered。
- 判题器与数据、口径同源；探测题只有一个月份，过期与误撤销按这一题判定。
- 各组在同一数据库上顺序运行，不清空 OS/PG 缓存，执行顺序按轮换。
