# Q2 V3 Causal Forecast

状态：`DEVELOPMENT_V2_PASS_FULL_RUN_ALLOWED`。末槽因果修复后的 M1 为 97/100，P1 为 96/100，开发期审核为97/100；冻结选择 B0 并允许五项年度运行，但尚不是正式 Q2 或 Q3/Q4 上游。

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
