# Q2 稳健性

## ONLINE 场景数

ONLINE 在 S=10/20/30/50 下的结果、候选一致率和年成本变化见：

`Q2/results/q2_online_final_closure/03_scenario_count/`

稳定性判定：True

## ONLINE 统计

ONLINE 与 M1、M2-TV、CAL-CVaR 的日级 Wilcoxon、7-day block bootstrap、月度与季节比较见：

`Q2/results/q2_online_final_closure/04_statistics/`

## ONLINE 时间映射

ONLINE 在 Mapping-A/B 下的差异为 0.05612987166734709%。

## 终端与评分

Scoring-A/B 的最终成本和候选一致率见：

`Q2/results/q2_online_final_closure/02_scoring_soc_value/`

## 初始 SOC

Feb-1 初始 SOC 取1200/3000/6000/9000/10800 kWh 时，ONLINE 成本范围为0.450501万元，
相对 6000 kWh 基准最大变化0.032626%，五种初值下 ONLINE 均排名第一。

## 储能解释 A/B

A 口径 ONLINE 为1380.803333万元；B 口径 ONLINE 为1567.528452万元，
且 B 口径下 M1 为1455.973744万元。储能解释会改变模型排序，
因此“储能可以日内因果响应”必须在模型假设中显著披露。
