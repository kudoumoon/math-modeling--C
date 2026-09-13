# Q1图件索引与可直接引用的图注

以下为已有Q1_BASELINE的后处理图件。时间均为旧Time A：当天00:10至次日00:10。
每张图对应一个源CSV，完整格式为PNG(300 DPI)、PDF、SVG；PDF嵌入字体，SVG保留可编辑文本。
三类各3张，共9张逻辑图。过程图是账本核查与调度摘要，不是求解器迭代记录。

## raw_q1_01_inputs

**输入时序及电价。** 上下两面板分别展示功率和电价，避免双纵轴造成视觉假相关。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/raw_q1_01_inputs.csv`。

## raw_q1_02_net_load_distribution

**净负荷分布。** 144个相邻时段的净负荷直方图，频数之和为144；不是独立重复试验。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/raw_q1_02_net_load_distribution.csv`。

## raw_q1_03_load_pv_relation

**负荷与光伏匹配。** 每点对应一个时段，虚线为光伏等于负荷；不拟合回归或作因果解释。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/raw_q1_03_load_pv_relation.csv`。

## process_q1_01_residuals

**守恒与状态残差。** 重算残差按10^-12 kWh缩放展示，验收容差为10^-5 kWh，未画入坐标范围；不是收敛轨迹。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/process_q1_01_residuals.csv`。

## process_q1_02_constraint_activity

**约束触界位置。** 使用绝对容差10^-5 kWh判断触界，容量行表示时段起点状态；最终状态另在SOC图展示。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/process_q1_02_constraint_activity.csv`。

## process_q1_03_block_flows

**四小时充放电汇总。** 每组为连续24段的总电量，不是样本均值；横轴使用旧Time A实际序列边界。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/process_q1_03_block_flows.csv`。

## result_q1_01_dispatch

**购电与储能调度。** 上图为购电和净负荷，下图充电为正、放电为负；电量除以1/6 h得到区间平均功率。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/result_q1_01_dispatch.csv`。

## result_q1_02_soc

**储能状态轨迹。** 145个边界状态；SOC按12000 kWh额定容量计算；首末均为50%。折线只连接边界值。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/result_q1_02_soc.csv`。

## result_q1_03_cost

**购电费用对比。** 两个确定性单序列总费用；无储能参照为sum(p*max(load-PV,0)/6)，不调用优化器。
单个确定性序列，不作统计推断；无误差棒、置信区间或显著性检验。

源数据：`results/figure_data/result_q1_03_cost.csv`。
