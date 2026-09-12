# Q2 V3 Causal Forecast

状态：`P1_PENDING`。M1 已于 2026-09-13 以 94/100 通过，允许实现最小真实链路；本目录尚不是正式 Q2 或 Q3/Q4 上游。

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
