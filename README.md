# 2026 数模国赛 C 题：数据、模型与版本归档

当前按用户要求停止模型优化，最终交付锁定 **Q1_BASELINE、Q2_V3_CAUSAL_FORECAST、Q3_V3_ALIGNED、Q4_V1_ALIGNED**。本轮补齐Q1/Q2图件、Q2工作簿和年度归档，未重新训练或求解。入口见[最终交付索引](deliveries/final-20260913-r1/others/DELIVERY_INDEX.md)，下载见[最终交付Release](https://github.com/kudoumoon/math-modeling--C/releases/tag/final-delivery-20260913-r1)。

已确认**附件时间为区间结束标签、按自然日建模；减购取消原购电费后收50%违约费；合同按规定时刻制定或调整，储能可因果动态控制，缺口实时补购**。见[已确认口径v1](solutions/EXPERT_REVIEW_R2/others/CONFIRMED_CONVENTIONS_v1.md)。这些新规则尚未重新建模，旧版本数字和94/91分仅保留历史适用范围。交付完整性验收不等于新口径模型验收。

本仓库冻结 C 题原始题目、附件、结果模板、主规约和 Q1–Q4 可追溯产物。Q3 v3、Q4 v1 已使用对齐后的因果核心完成首轮全年计算；旧错误上游版本另目录归档。

历史迭代流程：此前按用户授权暂存Q2汇总P2问题，优先完成Q3 v3和Q4 v1。两者使用同一份因果Q2主运行`q2v3-r2-full-b0-a-20260913-01`，依次执行后独立联合审核，省略重复年度复现。本轮已修正RESET1对照实验的导出校验误报；最终交付只补齐既有版本，不继续迭代。历史规约见[联合迭代规约](reports/q3_q4_joint_iteration_contract.md)。

首轮联合内容审核完成：**Q3 v3为94/100，Q4 v1为91/100**，未发现本题硬阻断，达到冻结的90分停止条件。Q3主方案相对冻结Q2合同节省47.98万元；Q4-3主方案相对Q4-2节省48.52万元，均为2至12月334计划日比较。内部评分不是官方评委分数，Q2待放行依赖仍保留。见[完整审核与扣分](solutions/Q3_Q4_JOINT/others/round01_final_independent_review.md)及[版本签收记录](solutions/Q3_Q4_JOINT/others/round01_release_receipt.json)。版本标签为 `q3-v3-r1`、`q4-v1-r1`。

## 版本状态（必读）

| 目录 | 状态 | 用途 |
|---|---|---|
| `solutions/Q1_BASELINE` | 最终交付所选Baseline | `results/baseline/`原结果、`figures/`新增图件；未生成新模型版本 |
| `solutions/Q2_V3_CAUSAL_FORECAST` | 最终交付所选V3/B0 | `results/final_v1/result2.xlsx`；五份年度运行在`results/annual_runs/` |
| `solutions/Q3_V3_ALIGNED` | 内容审核94分，暂定依赖 | 正确Q2合同上的日内调整，主结果 `results/q3v3-r1/A/result3.xlsx` |
| `solutions/Q4_V1_ALIGNED` | 内容审核91分，暂定依赖 | 动态价Q2核心及Q3调整，主结果 `results/q4-v1-annual-20260913-01/` |
| `solutions/Q2_V2_OFFICIAL_ONLINE_RISK` | 历史条件基线 | 存在归档哈希冲突，不属于本次所选交付目录 |
| `solutions/Q3_V2_WRONG_UPSTREAM_ARCHIVE` | **错误上游归档** | 实际导入 `q2_pipeline_v1`，仅供追溯 |
| `solutions/Q4_WRONG_UPSTREAM_ARCHIVE` | **错误上游归档** | 继承错误 Q3 且直接导入 V1 兼容核心，仅供追溯 |

机器可读状态见 [`VERSION_STATUS.json`](VERSION_STATUS.json) 的`final_delivery`。四题继续保留`formal_use=false`以区分历史模型与新口径验收；交付选择以该字段中的四个目录为准。两个`WRONG_UPSTREAM_ARCHIVE`和未完成的MIDNIGHT草稿均不属于最终包。

## 仓库内容

```text
problem/C题.pdf                         原始题目
data/附件1.xlsx … 附件4.xlsx           原始数据
data/附件5/                            官方结果模板
plan/C题融合路线与验证规约_v2.md       当前唯一主规约
docs/训练前数据与防泄漏规约.md          预测实验硬规则
data_manifest.json                     文件大小与 SHA-256
```

各题交付以`program/results/figures/others`分类。最终ZIP作为GitHub Release资产提供，仓库保留解包后的内容；Python虚拟环境、缓存和无关方案包不纳入。`Q3_Q4_JOINT`、数据、模板及来源文件作为运行支持材料随包保留，不能仅复制四个目录后启动程序。

## 最重要的时间口径

- 后续主口径为自然日00:00-24:00，附件点标签为区间结束：`0:10`对应00:00-00:10，`0:00+1`对应当前日23:50-24:00。
- 已归档Time A运行覆盖00:10-次日00:10，不能改标签作为新口径结果。购电模板区间文字与自然日首槽冲突，输出映射需单独明确。
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

当前交付口径：Q1保留原Baseline；Q2 v3年度账本和补导出工作簿是本次Q2入口；Q3 v3、Q4 v1使用其同一B0基线。所有成果来自原运行，未实施新口径模型；旧错误上游归档不能替代所选版本。

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
