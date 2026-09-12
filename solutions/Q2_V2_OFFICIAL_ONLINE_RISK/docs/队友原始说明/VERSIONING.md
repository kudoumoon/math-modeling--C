# 版本管理

## 基线

- 初始复制基线：`legacy-copy-20260912`
- 原始复制时间：2026-09-12 12:25 后
- 原始工程：`D:\C题文件代码\问题二实现_1405后验证优化`
- 本工作区：`D:\C题文件代码DEEPSEEK专用\Q2=Q3`

## 规则

1. 每个阶段提交一次 Git commit。
2. 大数据结果不进入 Git；使用 `versions/` 下的 SHA-256 清单追踪。
3. 新运行必须使用 `runs/<run_id>/config.json` 或等价配置文件。
4. 运行日志写入对应问题的 `logs/`。
5. 正式决策必须记录 `code_version`、`config_hash`、`data_hash` 和输出文件哈希。

## 最终版本

- Q2：`versions/Q2/q2-frozen-v3-final_sha256.csv`
- Q2 元数据：`versions/Q2/q2-frozen-v3-final_metadata.json`
- Q2 ONLINE 重新冻结：`versions/Q2/q2-online-refrozen-final_sha256.csv`
- Q2 ONLINE 元数据：`versions/Q2/q2-online-refrozen-final_metadata.json`
- Q2 三题意专项最终版：`versions/Q2/q2-three-issues-final_sha256.csv`
- Q2 三题意专项元数据：`versions/Q2/q2-three-issues-final_metadata.json`
- Q3：`versions/Q3/q3-conditional-final_sha256.csv`
- Q3 元数据：`versions/Q3/q3-conditional-final_metadata.json`
- Q2 封口状态：`Q2_FROZEN = TRUE`
- Q3 状态：`Q3_FROZEN_CONDITIONAL = TRUE`，等待 A/B 结算解释
