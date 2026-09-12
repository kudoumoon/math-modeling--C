# WARNING: wrong-upstream Q4 archive

**本目录不是正式 Q4，其费用、排程、图表和结果 Excel 禁止写入最终论文。**

- Q4-3 继承了已确认上游错误的 Q3 V2。
- `q4_core.py`、`q4_full.py`、`q4_oracle.py`、`q4_p1.py` 直接导入 `q2_pipeline_v1` 和 `q2_v2_compatible`。
- 即使 Q4 内部物理与账本检查通过，也不能证明它基于正确 Q2 V2。

归档仅用于追溯价格预测、合同调整、画图和审计方法。新 Q4 必须等正确 Q3 冻结后重建。

源码内“Q3 v2 已冻结”等文字是当时运行环境的历史注释，已被仓库级 `VERSION_STATUS.json` 否定，不代表当前状态。该快照仍依赖原本地 Q2/Q3 目录层级，因此**不承诺独立复现**。
