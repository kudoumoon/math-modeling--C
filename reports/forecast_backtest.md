# Q3/Q4 因果预测模型回测报告

本报告由 `PYTHONPATH=src .venv/bin/python -m forecasting.cli` 生成。所有模型按月扩展窗口重训；模型选择仅使用2025-02至2025-06，2025-07至2025-12为回顾性审计区间。

## 开发期选定模型

- `load_10min`：`hist_gradient_boosting`
- `price_10min`：`hist_gradient_boosting`
- `pv_hourly`：`hist_gradient_boosting_residual`

## 指标

| target      | model                           | split       |     n |      mae |     rmse |     bias |   interval_coverage |
|:------------|:--------------------------------|:------------|------:|---------:|---------:|---------:|--------------------:|
| load_10min  | hist_gradient_boosting          | audit       | 26496 | 178.4708 | 246.4924 | -28.0553 |              0.8225 |
| load_10min  | hist_gradient_boosting          | development | 21600 | 147.0772 | 199.7813 | -28.5465 |              0.7954 |
| price_10min | hist_gradient_boosting          | audit       | 26496 |   0.0425 |   0.0603 |  -0.0063 |              0.8123 |
| price_10min | hist_gradient_boosting          | development | 21600 |   0.0407 |   0.0551 |  -0.0059 |              0.8082 |
| pv_hourly   | hist_gradient_boosting_residual | audit       | 17628 | 172.1501 | 337.0427 | -51.7147 |              0.8298 |
| pv_hourly   | hist_gradient_boosting_residual | development | 14400 | 209.0471 | 381.8006 |   5.5285 |              0.7715 |

## 信息边界

- 负荷与价格预测只使用目标日之前已完成日期的滞后量和滚动统计。
- 前一日最后一个 `0:00–0:10+1` 区间在当日0:00尚未完成，特征中显式置空。
- 光伏模型只校准附件3在各发布时刻已经给出的预报；训练标签必须在发布时刻前已完整形成。
- 预测区间只使用当前发布时刻之前已完成目标的历史残差。
- 审计区间此前已在仓库文档中出现过汇总结果，因此只能称回顾性审计，不能称全新未见测试。
