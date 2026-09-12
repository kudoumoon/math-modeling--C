# 2026 数模国赛 C 题：数据、模型与版本归档

本仓库冻结 C 题原始题目、附件、结果模板、主规约和 Q1–Q4 可追溯产物。Q3/Q4 是已确认使用错误上游的历史快照，不是正式结果。

## 版本状态（必读）

| 目录 | 状态 | 用途 |
|---|---|---|
| `solutions/Q1_BASELINE` | 当前 Q1 基线 | 可复现计算与论文参考 |
| `solutions/Q2_V2_OFFICIAL_ONLINE_RISK` | **Q2 唯一正式路线** | 队友 `ONLINE-RISK-SP-A-S10-BATA`；条件主结果 |
| `solutions/Q3_V2_WRONG_UPSTREAM_ARCHIVE` | **错误上游归档** | 实际导入 `q2_pipeline_v1`，仅供追溯 |
| `solutions/Q4_WRONG_UPSTREAM_ARCHIVE` | **错误上游归档** | 继承错误 Q3 且直接导入 V1 兼容核心，仅供追溯 |

机器可读状态见 [`VERSION_STATUS.json`](VERSION_STATUS.json)。后续 Q3/Q4 必须从 `Q2_V2_OFFICIAL_ONLINE_RISK` 重建，禁止从两个 `WRONG_UPSTREAM_ARCHIVE` 目录提取正式数值。

## 仓库内容

```text
problem/C题.pdf                         原始题目
data/附件1.xlsx … 附件4.xlsx           原始数据
data/附件5/                            官方结果模板
plan/C题融合路线与验证规约_v2.md       当前唯一主规约
docs/训练前数据与防泄漏规约.md          预测实验硬规则
data_manifest.json                     文件大小与 SHA-256
```

不在本次冻结范围内：社交平台方案包、Python 虚拟环境、缓存和重复 ZIP。Q3/Q4 年度输出予以保留，但只是错误上游的审计材料。

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

正式结果口径：Q1 已归档；Q2 已冻结为队友 ONLINE-RISK V2。`solutions` 下的 Q3/Q4 仅保留错误上游版本用于审计，待真正绑定 Q2 V2 后重建，禁止作为正式提交结果。

独立预测验证线已完成：因果预测主干、漂移感知在线自适应、真实 LP 与交易账本、Q3/Q4 逐日滚动回测，以及块 Bootstrap、月度分解和信息消融证据。这些预测实验属于候选验证资产，不改变上述 Q3/Q4 正式版本状态。

- 运行预测回测：`PYTHONPATH=src .venv/bin/python -m forecasting.backtest`
- 运行完整收益验证：`PYTHONPATH=src .venv/bin/python -m forecasting.rolling_backtest`
- 主要结果：`reports/q3_q4_rolling_summary.csv`、`reports/q3_q4_rolling_daily.csv`、`reports/q3_q4_monthly_decomposition.csv`、`reports/q3_q4_block_bootstrap.csv`、`reports/q3_q4_information_ablation.csv`
- 方法说明：[Q3/Q4 滚动收益验证](docs/Q3-Q4滚动收益验证.md)

当前预测候选为“因果预测 + 漂移感知适配 + LP + 经济门控”。H100 统一模型仍属于 challenger；GPU 训练结果必须在相同随机种子、因果边界和审计账本下通过时序基线、滚动回测、消融及下游现金成本/风险检验，才允许升级冻结版本。
