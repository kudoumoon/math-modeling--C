# Q2 V3 Causal Forecast

当前为用户选定的最终交付目录：五项年度运行已经完成，本轮仅补齐结果工作簿、图件和归档，模型仍为冻结B0。新口径未重新建模，历史模型评分不等于本次导出审核。交付入口见`results/final_v1/result2.xlsx`和根目录最终交付索引。

年度原始运行在`results/annual_runs/`，开发期原始运行在`results/development_runs/`；Q3 v3和Q4 v1都使用其中的`q2v3-r2-full-b0-a-20260913-01`。`others/executed_source/`保留该运行的原源码。

工作簿购电表保留历史Time A合同标签，储能及紧急表由同一已存轨迹转换为实际自然时钟统计。`results/final_v1/q2_plan_day_storage_blocks.csv`和`q2_natural_day_storage_blocks.csv`分别保留两套窗口；这不是新的自然日模型。主成本为14,012,090.207768975元，模型与策略未重跑。

## 目录

- `program`：Q2 自包含预测、ONLINE-RISK-SP 规划、执行和测试。
- `results`：完成的机器结果、逐段账本和运行清单。
- `figures`：由结果表生成的论文图。
- `others`：版本身份、审核和复现说明。

## 最小运行

```bash
PYTHONPATH=solutions/Q2_V3_CAUSAL_FORECAST/program \
  .venv/bin/python solutions/Q2_V3_CAUSAL_FORECAST/program/run_q2_v3.py \
  --run-id q2v3-b0-smoke \
  --output-root runs/q2v3-b0-smoke \
  --arm B0 --start-day 0 --end-day 1 --report-start-day 0 --workers 2
```

每个输出目录必须是新路径。正式开发期实验从 1 月 1 日开始并至少运行至 6 月 30 日；7-12 月只允许在开发期采用规则冻结后运行一次。

Battery A 是“区间内连续测量反馈以十分钟平均量等价表示”的条件实现；Battery B 是电池动作日前冻结后的严格敏感性。二者不得混表或择低发布。

## 已失效的开发期结论

`results/development_v1` 保留第一次2-6月四臂实验，但其 B0 末槽曾读取零点尚未完成的上一计划日末槽，因此不得继续用于模型选择。修复后还增加了 Time B 因果专用预测、一槽延迟命令/保护分账和2月SOC重置对照；正式结论只读取后续 `development_v2`。

## 当前开发期结论

`results/development_v2` 的四臂均从1月1日连续运行，2月1日至6月30日共150日配对评价。Abl-L、Abl-PV和B1的资产调整费用点估计分别降低0.647%、0.226%和0.330%，但14日连续块Bootstrap的95%区间全部跨0，因此没有挑战者通过全部采用门槛。冻结选择为B0 `Q2V2-SW2-REC5`，不根据已知结果降低门槛。
