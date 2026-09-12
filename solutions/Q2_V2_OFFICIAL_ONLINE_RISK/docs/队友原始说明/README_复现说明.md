# 2026 C题问题二（Q2）可复现交付包

打包日期：2026-09-12（Asia/Shanghai）  
来源工程：`D:\C题文件代码DEEPSEEK专用\Q2=Q3`  
来源 Git 提交：`a31220b084153b7a0355119afffe8d1de6a50d5e`（打包时工作树干净）

## 1. 当前结论

- 当前条件主模型：`ONLINE-RISK-SP`。
- Battery Interpretation A 下年度成本：`1380.803333064248` 万元。
- 当前状态：**条件冻结**，不是无条件封版。
- 条件：每天 0:00 冻结计划购电量，储能在日内根据已经观测到的信息进行因果响应。
- 严格 Battery Interpretation B 会改变模型排序，但现有 B 实现仍需按“G/C/D 日前联合优化”进一步公平重建，不能直接把 13.52% 差异视为最终裁定。
- `1378.287021` 万元是测试网格中的探索结果，不是当前正式主结果。

权威状态文件：`Q2/Q2_FINAL_MODEL_DECISION.json`、`Q2/RUN_STATE.json`。  
完整说明：`Q2_THREE_ISSUES_ANALYSIS.md`、`RESULTS_AND_EXPERIMENTS_SUMMARY.md`。

## 2. 包内结构

- `data/`：原题、附件1、附件2及官方 result2 模板。
- `Q2/`：Q2 完整结果、审计证据、配置、日志和论文素材。
- `results/`：早期基线、深搜与 1405 后验证结果；用于追溯，不代表全部均为正式方案。
- `paper_assets/Q2/`：论文表格、图片和 Markdown 素材。
- `versions/Q2/`：历史版本哈希与元数据。
- 根目录 `q2_*.py`、`run_q2_*.py`、`analyze_q2_*.py`：模型、运行和审计代码。
- `tests/`：Q2 自动化测试。
- `deliverables/`：当前便携导出结果和关键交付物。

## 3. 环境要求

- 推荐 Windows 10/11 64 位。
- 推荐 Python 3.11.x；原运行环境为 Python 3.11.9。
- 至少预留约 2 GB 磁盘空间；完整复跑还需要足够内存和数小时计算时间。

在 PowerShell 中进入解压后的目录，然后执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_environment.ps1
.\run_quick_verify.ps1
```

快速验证只检查数据、代码、已有结果和测试，不重新求解全年模型。

## 4. 完整主结果复跑

```powershell
.\run_full_main_reproduction.ps1 -Workers 5
```

该命令把新结果写入 `reproduction_output/`，不会覆盖包内的历史证据。完成后会将复算成本与 `1380.803333064248` 万元比较。

## 5. 导出当前 result2

```powershell
& .\.venv\Scripts\python.exe .\export_result2_online.py
```

输出：`deliverables/result2_ONLINE_RISK_SP_条件主结果.xlsx`。该文件来自已保存的 ONLINE-RISK-SP 数组，文件名明确保留“条件主结果”，避免误称为无条件官方答案。

## 6. 重要口径

1. 附件1 的 `0:10` 价格采用左端区间映射到 `0:10-0:20`；替代映射敏感性低于 0.1%。
2. 题目只直接给出 2025-01-01 00:00 SOC=6000 kWh；当前 Q2 使用 2025-02-01 SOC=6000 kWh 作为中性初始化并做过敏感性检验。
3. 代码中的 `spill` 应解释为“未利用剩余供给量”，不能严格称为光伏弃电。
4. 根目录及历史结果中可能保留旧绝对路径作为实验溯源文本；实际运行代码的数据入口已经改为包内相对路径 `data/附件/`。

## 7. 安全使用建议

先运行快速验证，再决定是否执行全年复跑。不要直接把历史文件名带有“冻结候选”的 Excel 当作当前主模型输出；以 `Q2_FINAL_MODEL_DECISION.json` 和本说明为准。
