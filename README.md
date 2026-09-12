# 2026 数模国赛 C 题：预测与滚动优化准备仓库

本仓库冻结 C 题原始题目、官方附件、结果模板和当前唯一主规约，为后续 Q3/Q4 的因果预测、滚动优化和 GPU 模型实验提供统一输入。

## 仓库内容

```text
problem/C题.pdf                         原始题目
data/附件1.xlsx … 附件4.xlsx           原始数据
data/附件5/                            官方结果模板
plan/C题融合路线与验证规约_v2.md       当前唯一主规约
docs/训练前数据与防泄漏规约.md          预测实验硬规则
data_manifest.json                     文件大小与 SHA-256
```

不在本次冻结范围内：社交平台方案包、未经复现的年度结果、现有 Q1–Q3 求解输出、缓存、个人报告和本地绝对路径配置。

## 最重要的时间口径

- 每日 144 个十分钟区间按 `0:10–0:20` 开始，最后以次日 `0:00–0:10+1` 结束。
- 表中的 `0:00+1` 或 `0:00–0:10+1` 明确属于次日，禁止把它移到当天序列开头。
- Q3/Q4 的模型只能使用决策时刻已经可见的信息；未来真实负荷、未来真实光伏和事后修订信息不能进入特征。
- 完美信息结果只能作为离线参考界或诊断基准，不能作为可部署方案成绩。

详细规定见 [训练前数据与防泄漏规约](docs/训练前数据与防泄漏规约.md)。建模和验证以 [C题融合路线与验证规约 v2](plan/C题融合路线与验证规约_v2.md) 为唯一主规约。

## 数据完整性

为避免公开无关的组委会本机路径，仓库内 9 个 XLSX 发布副本仅删除了 `xl/workbook.xml` 中的 `x15ac:absPath` 元数据；工作表内容及其余 OOXML 成员保持不变。首次拉取后可在 PowerShell 中验证：

```powershell
Get-ChildItem -Recurse -File problem,data,plan | Get-FileHash -Algorithm SHA256
```

将结果与 `data_manifest.json` 比对。原始附件只读；清洗数据、模型、日志和预测结果应写到后续独立目录，不应覆盖这里的冻结输入。

## 当前状态

当前主线已完成：因果预测主干、漂移感知在线自适应、真实 LP 与交易账本、完整 Q3/Q4 逐日滚动回测，以及块 Bootstrap、月度分解和信息消融证据。

- 运行预测回测：`PYTHONPATH=src .venv/bin/python -m forecasting.backtest`
- 运行完整收益验证：`PYTHONPATH=src .venv/bin/python -m forecasting.rolling_backtest`
- 主要结果：`reports/q3_q4_rolling_summary.csv`、`reports/q3_q4_rolling_daily.csv`、`reports/q3_q4_monthly_decomposition.csv`、`reports/q3_q4_block_bootstrap.csv`、`reports/q3_q4_information_ablation.csv`
- 方法说明：[Q3/Q4 滚动收益验证](docs/Q3-Q4滚动收益验证.md)

当前推荐候选为“因果预测 + 漂移感知适配 + LP + 经济门控”。H100 统一模型仍属于 challenger：必须在相同随机种子、相同因果边界和相同审计账本上证明现金成本与风险均改善后，才允许替换小模型主线。
