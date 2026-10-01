| metric | deepseek-v4.1-flash | pooled |
|---|---|---|
| sessions (correct) | 100 (63) | 100 (63) |
| DB calls / session (median) | 5.0 | 5.0 |
| SQL templates per 100 SQL | 75.6 | 75.6 |
| SQL whose template seen before % | 24.4 | 24.4 |
| distinct templates per 100-SQL block | 83 | 83 |
| exploration calls % (schema+data) | 67.9 | 67.9 |
|   schema % | 66.6 | 66.6 |
|   data explore % | 1.3 | 1.3 |
| validation calls % | 4.8 | 4.8 |
| abandoned attempts % | 5.4 | 5.4 |
| final-answer SQL % | 20.5 | 20.5 |
| failed calls % | 0.6 | 0.6 |
| failed SQL % (of SQL) | 1.7 | 1.7 |
|   compute-only SQL % | 0.8 | 0.8 |
| wrong answers with no failed call % | 100.0 | 100.0 |
| sessions with >=1 failure % | 2.0 | 2.0 |
| sessions with >=1 validation % | 16.0 | 16.0 |
| sessions starting with schema lookup % | 100.0 | 100.0 |
| session length s (median) | 35.7 | 35.7 |
| knowledge calls: fact seen in earlier session % | 92.9 | 92.9 |
|   same template % | 91.0 | 91.0 |
|   same text % | 89.4 | 89.4 |
| knowledge SQL: fact / template / text % | 38.2 / 17.6 / 0.0 | 38.2 / 17.6 / 0.0 |
| DB time of repeated facts % | 76.7 | 76.7 |
| same fact by another session within 60 s % | 90.8 | 90.8 |

Same semantics, different SQL (correct sessions only): 24 questions with >=2 correct sessions; mean 2.38 templates over 2.58 correct sessions per question; 87.5% of questions answered with >=2 templates; 47 templates over 15 question classes vs 15 for the application.
Application: 25 queries, 15 templates, template repeat 40.0%.
