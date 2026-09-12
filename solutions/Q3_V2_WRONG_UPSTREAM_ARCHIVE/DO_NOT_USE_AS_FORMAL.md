# WARNING: wrong-upstream Q3 archive

**本目录不是正式 Q3，其费用、排程和 `result3.xlsx` 禁止写入最终论文。**

- `q3_full_pipeline_v2.py` 和 `q3_pipeline_v2.py` 仍导入 `q2_pipeline_v1`。
- `q2_v2_compatible.py` 也以 `q2_pipeline_v1` 为 core。
- 本目录没有正式 Q2 V2 的 `q2_model.py`、`q2_deep_core.py`和 `run_q2_online_selector.py`。
- 所谓 V2 暖启动使用固定 `alpha=0.65` 与 PWL 终端价值，不是 `ONLINE-RISK-SP-A-S10-BATA` 的在线场景选择。

归档仅用于保留旧思路、定位上游混用原因和辅助新 Q3 的回归对照。

该快照仍按原本地目录层级解析路径，且本仓库刻意不把 Q2 V1 放入正式依赖树，因此此归档**不承诺独立复现**。
