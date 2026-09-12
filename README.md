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

独立预测验证线包含因果预测、漂移感知在线自适应、LP计划与费用回放。2026-09-13完成第三轮独立审核，已修复月初训练标签、首日风险余量及跨日SOC的信息边界。这些实验属于候选验证资产，不改变上述Q1-Q4正式版本状态；历史Q3/Q4费用报告来自修复前实现，日内更新也尚未完成正式滚动LP重建。

第三轮独立审核为96/100，已识别硬阻断清零，达到内部90分停止条件。该分数不代表国赛获奖概率，也不表示Q1-Q4最终优化已经完成。

- 冻结验收标准：[预测器双Agent验收规约](docs/预测器双Agent验收规约.md)
- 迭代与独立评分：[预测器迭代审核](reports/预测器迭代审核.md)
- 时间语义及接入：[预测输出时间与接入契约](docs/预测输出时间与接入契约.md)
- 隔离实验：`PYTHONPATH=src OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m forecasting.experiment --run-id <唯一ID>`

- 仅运行预测：`PYTHONPATH=src .venv/bin/python -m forecasting.cli --output-root runs/<唯一ID>`
- 本轮完整产物：`runs/round03_causal_soc/`，包括模型、预测、适配轨迹、分层误差和固定控制器代理费用。
- 独立审核原始结果：`reports/forecast_review_round03.json`。
- 历史滚动结果及方法说明：[Q3/Q4 滚动收益验证](docs/Q3-Q4滚动收益验证.md)，其中旧费用尚未按全部新边界重新审定。

当前预测候选为“梯度提升树 + 光伏残差校准 + 漂移感知适配”，已在固定控制器代理中验证。完整滚动LP、经济门控和正式结果模板需在接入Q1-Q4时另行审计。H100统一模型仍属于challenger，不能凭模型复杂度替换当前小模型。
