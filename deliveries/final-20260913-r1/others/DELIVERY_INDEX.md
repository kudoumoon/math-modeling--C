# Q1-Q4 最终交付冻结说明

交付编号：`final-20260913-r1`，Git标签：`final-delivery-20260913-r1`。本轮补齐图件、结果表与归档，未重新训练、求解或执行年度策略；模型版本不升级。新确认的时间、计费和执行规则已记录，但未对历史轨迹重新建模。

发布入口：[GitHub最终交付包](https://github.com/kudoumoon/math-modeling--C/releases/tag/final-delivery-20260913-r1)。以其中的`Q1-Q4-final-20260913-r1.zip`为统一交接包，附SHA-256校验文件。

五个主工作簿另集中在`deliveries/final-20260913-r1/results/`：`result1.xlsx`、`result2.xlsx`、`result3.xlsx`、`result4-2.xlsx`、`result4-3.xlsx`，均为各题主结果的逐字节副本。Q1只将既有`result1_v2.xlsx`复制为题目要求的文件名，不生成新Q1 v2。来源映射见`others/WORKBOOK_MAPPING.json`。

## 四题入口

|题目|锁定目录|主要结果|
|---|---|---|
|Q1|`solutions/Q1_BASELINE`|`results/baseline/`中的原工作簿、144槽账本与汇总；`figures/`中的新增图件|
|Q2|`solutions/Q2_V3_CAUSAL_FORECAST`|`results/final_v1/result2.xlsx`；`results/final_v1/`费用、储能、紧急事件和敏感性表|
|Q3|`solutions/Q3_V3_ALIGNED`|`results/q3v3-r1/A/result3.xlsx`；其他目录为原有对照方案|
|Q4|`solutions/Q4_V1_ALIGNED`|`results/q4-v1-annual-20260913-01/result4-2.xlsx`及`result4-3.xlsx`；B工作簿为对照|

每题的`program`为程序，`results`为表格及机器结果，`figures`为图片，`others`为说明、审计与来源快照。Q1原`result/`及根部报告保留为历史兼容副本，新交付从`results/baseline/`和`others`读取，不代表生成了新的Q1模型。

## 归档和依赖

- Q2的五份年度和四份开发期原始运行分别归入`results/annual_runs/`和`results/development_runs/`，保留原始manifest与文件哈希。
- Q3/Q4共同使用的Q2主运行是`q2v3-r2-full-b0-a-20260913-01`，模型为B0 `Q2V2-SW2-REC5`。Q3 v3与Q4 v1是本次选定的最新完整年度版本，没有采用未完成的MIDNIGHT草稿。
- Q3/Q4共享审核材料复制到各自`others/joint_review/`；Q3发布价值图归入`figures/release_value/`，Q4价格诊断表归入`results/price_diagnostics/`。
- `solutions/Q3_Q4_JOINT`保留为兼容依赖，不能从运行环境删掉；`data/`、`plan/`、根目录来源清单和说明同样随包提供。它不是第五个待提交模型。
- Q2/Q3/Q4的`others/executed_source/`保存各自原manifest绑定的源码。当前交付器与文档的修补不回写历史来源或成本。
- `FILE_MANIFEST.json`逐文件记录路径、分类、大小及SHA-256；`ARCHIVE_MAPPING.json`记录文件归档与Git来源映射；`PACKAGE_RECEIPT.json`及`SHA256SUMS`用于校验压缩包。

## 数据口径与使用边界

历史主计算保留Time A：计划日00:10至次日00:10，普通合同、费用与原预测器不变。本轮没有把它重新标成新自然日模型。

Q2新导出工作簿的购电表沿用原模板的计划日标签；储能与紧急购电表从同一历史轨迹拼接实际00:00至24:00的记录，前一计划日槽143供当天首槽。计划日与自然日的储能及事件表分别保存，因此窗口边缘的总量不必相等。Q2的Time B是旧跨日移位敏感性，不是新确认的自然日口径。RESET1只允许2月1日开始的那一次6000 kWh重置，主方案没有该重置。

Q1/Q3/Q4既有工作簿按原字节保留，其历史时间边界和限制详见各题说明。本轮的文件完整性及导出验收，不代替模型重新评审；此前94/91分不适用于新口径。

## 运行与校验

压缩包保留仓库相对路径，用于直接查看、交接与校验。原程序的防错检查需要Git历史，实际运行请完整克隆仓库并切换交付标签，不能仅解压四个目录后启动程序。Python依赖见根目录`pyproject.toml`、共享`requirements-lock.txt`及各题交付说明。

Q2仅重新导出已有账本（不会求解，但输出路径必须为新目录）：

```sh
.venv/bin/python solutions/Q2_V3_CAUSAL_FORECAST/program/finalize_q2.py --skip-figures --output-dir /tmp/q2-export-check
```

归档程序：`scripts/final_delivery.py archive`。打包程序：`scripts/final_delivery.py package --output <新的ZIP路径>`。图件的实际再生成命令见各题图件说明；最终包内不包含虚拟环境、缓存、错误上游旧模型及未完成的MIDNIGHT草稿。
