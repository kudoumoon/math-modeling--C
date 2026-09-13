# Q4 V1 最终交付入口

主目录：`results/q4-v1-annual-20260913-01/`。`result4-2.xlsx`与`result4-3.xlsx`分别为动态电价下问题2和问题3的主结果；`result4-3-B-sensitivity.xlsx`为历史结算B对照。原题不另设Q4-1，价格方法和比较范围见`ROUND01_METHOD_NOTES.md`。局部`q4-p1-*`不作为年度结果。

年度图件在`figures/q4-v1-annual-20260913-01/`，价格诊断表归入`results/price_diagnostics/`。共享审核回执归入`others/joint_review/`，原运行源码在`others/executed_source/`，便于核验原来源。

Q4调用Q2 V3/B0的规划执行核心与Q3 V3的日内调整实现，同Q3绑定`q2v3-r2-full-b0-a-20260913-01`。Q3/Q4共同依赖`Q3_Q4_JOINT`的便携Q2主运行、`data/`和来源文件，均随最终包保留。

本轮不改写原年度工作簿或成本，不启动Q4 V2草稿。旧Time A、主结算A及价格解释仍属历史模型限制，新确认规则未重新建模。原算法的来源校验需要完整Git历史，不能只复制四个目录直接运行。
