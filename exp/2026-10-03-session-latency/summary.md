| phase | policy | correct / n | mean s | P95 s | LLM % of completion | replies | DB ms (sum) | goodput@60s / min |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| cold | no-share | 3/9 | 64.33 | 182.00 | 99.3 | 4.78 | 3992.7 | 0.311 |
| cold | definition | 9/9 | 19.06 | 64.86 | 99.6 | 3.56 | 755.9 | 2.798 |
| cold | definition-cache | 9/9 | 11.24 | 15.96 | 98.9 | 3.67 | 1047.6 | 5.335 |
| cold | condition | 9/9 | 13.70 | 31.79 | 98.9 | 3.78 | 1321.1 | 4.378 |
| warm | no-share | 4/9 | 28.81 | 56.34 | 99.9 | 4.44 | 352.0 | 0.925 |
| warm | definition | 9/9 | 13.63 | 22.26 | 98.9 | 4.11 | 1290.4 | 4.402 |
| warm | definition-cache | 9/9 | 14.47 | 26.22 | 99.4 | 3.78 | 757.4 | 4.146 |
| warm | condition | 9/9 | 15.28 | 38.87 | 99.6 | 3.67 | 592.3 | 3.927 |
| after-append | no-share | 3/9 | 37.93 | 97.44 | 98.5 | 4.78 | 5165.1 | 0.527 |
| after-append | definition | 9/9 | 17.82 | 29.44 | 69.1 | 3.44 | 49603.1 | 3.368 |
| after-append | definition-cache | 9/9 | 18.00 | 32.47 | 76.6 | 3.56 | 37910.1 | 3.334 |
| after-append | condition | 9/9 | 12.53 | 19.23 | 90.4 | 3.44 | 10785.9 | 4.790 |
| after-status | no-share | 2/9 | 73.58 | 174.46 | 93.9 | 6.89 | 40350.7 | 0.091 |
| after-status | definition | 9/9 | 33.50 | 67.67 | 46.5 | 3.89 | 161267.7 | 1.592 |
| after-status | definition-cache | 9/9 | 32.01 | 62.96 | 46.7 | 4.00 | 153580.8 | 1.666 |
| after-status | condition | 9/9 | 28.41 | 69.65 | 59.0 | 3.89 | 104773.7 | 1.642 |
| burst-status | no-share | 4/18 | 91.09 | 239.18 | 72.2 | 5.83 | 39031.3 | 0.095 |
| burst-status | definition | 18/18 | 56.92 | 89.39 | 35.2 | 3.78 | 175515.1 | 2.994 |
| burst-status | definition-cache | 18/18 | 58.05 | 108.73 | 41.8 | 3.72 | 149053.2 | 2.376 |
| burst-status | condition | 18/18 | 78.07 | 356.23 | 54.1 | 4.11 | 138315.0 | 1.233 |
