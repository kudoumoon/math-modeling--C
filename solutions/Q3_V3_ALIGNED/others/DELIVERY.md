# Q3 V3 最终交付入口

主结果：`results/q3v3-r1/A/result3.xlsx`。同目录保存完整年度账本、费用、指定日期表、紧急事件和结果摘要；`baseline/B/A_6/A_6_12`为原有对照，`q3v3-p1`为局部验证，不能冒充年度主结果。

图件在`figures/q3v3-r1/`和`figures/release_value/`。共享审核回执已复制到`others/joint_review/`，原运行源码保存在`others/executed_source/`，逐字节匹配原manifest。

上游为Q2 V3的`q2v3-r2-full-b0-a-20260913-01`，模型B0 `Q2V2-SW2-REC5`。Q2原始主运行已归档到其`results/annual_runs/`；代码继续使用`Q3_Q4_JOINT/results/q2_provisional`兼容镜像，最终包保留该依赖、原始附件与来源说明。

本轮没有改写Q3结果、运行新策略或提高评分。旧Time A、旧主结算A和工作簿边界仍按原版本解释；新确认规则未重算。复现防错检查依赖Git历史，运行时须完整克隆仓库并切换最终交付标签。
