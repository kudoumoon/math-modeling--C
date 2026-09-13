# Q2 delivery figures r1

本交付只读取已生成的 `results/final_v1` 和原始附件，没有导入模型代码，
没有调用求解器、训练、预测拟合或年度回放。没有修改 `finalize_q2.py`。

## 九张逻辑图

|类别|图名|论证与数据|
|---|---|---|
|原始|raw_q2_01_daily_energy|365 日负荷/PV 日能量直方图，相同分箱，保留全部日期。|
|原始|raw_q2_02_diurnal_tariff|144 槽跨日中位数、P10-P90 范围与已知附件1电价；范围不是置信区间。|
|原始|raw_q2_03_load_pv_relation|365 对日负荷/PV能量，季度颜色与点形冗余编码；仅描述关联。|
|过程|process_q2_01_executed_soc|48,096 个执行前 SOC 状态的完整热力图，无平滑或抽样。|
|过程|process_q2_02_candidate_selection|已有日账本的15候选选择轨迹与次数，含两项零选择候选，不是收敛曲线或候选优越性检验。|
|过程|process_q2_03_emergency_distribution|按计划行小时累计紧急量及334日日紧急量ECDF，保留194个零紧急日。|
|结果|result_q2_01_monthly_cash|月度计划费用与紧急费用堆叠；334日总现金14,012,090.21元。|
|结果|result_q2_02_monthly_risk|月内日费用箱线、经验P95与紧急日频率；显示月样本量和离群点，无推断或新增策略指标。|
|结果|result_q2_03_common333_sensitivity|五个旧case共同333计划日期的现金/紧急量相对主策略差值，未作库存调整。|

每张图导出 `PNG(300 dpi) + SVG + PDF + 灰度PNG(300 dpi)`，共36个主要图文件；
150 dpi 读图预览位于 `figures/delivery_r1/previews/`，不计入九图数量。
全部图宽7.2英寸，实际高度、尺寸/字体检查、源代码及输出哈希见manifest。
SVG文字可编辑且不嵌入位图，PDF使用嵌入TrueType字体。

## 时间和统计口径

- 主策略为冻结 B0，旧 Time A：`time_index=0` 的实际起点为当日00:10，
  `time_index=143` 的实际起点为次日00:00。图中 `slot/6` 是名义计划行小时。
  这里没有把旧计划行重新命名为自然时钟。
- 原始图保留2025年365个附件日期；主结果与过程图为2月1日至12月31日334个计划日期。
- 敏感性只用 `day_index=31..363`，共333日，即2月1日至12月30日。
  对每个case从finalizer附带日账本再次核对现金和紧急量；没有把334日总量混入比较。
  Time B只是原有右端点解释敏感性，不是新的自然日口径。
- 月P95采用线性经验分位数；箱体为IQR，中线为中位数，须为1.5 IQR，离群点保留。
  没有绘制或重新定义策略CVaR目标。月频率分母是该月实际天数，不假设各日独立。
- SOC是已存执行状态，Battery A反馈并不因此被声称为经济最优。

## 可运行命令

在仓库根目录从父级交付表生成图和图源数据：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python solutions/Q2_V3_CAUSAL_FORECAST/program/q2_delivery_figures.py
```

从已经归档的图源数据可携带重绘，不依赖原始 `runs/` 路径或个人技能安装：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python solutions/Q2_V3_CAUSAL_FORECAST/program/q2_delivery_figures.py --from-figure-data
```

单文件格式复核：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python solutions/Q2_V3_CAUSAL_FORECAST/program/figure_tools/check_figure.py 'solutions/Q2_V3_CAUSAL_FORECAST/figures/delivery_r1/*.png' 'solutions/Q2_V3_CAUSAL_FORECAST/figures/delivery_r1/*.svg' 'solutions/Q2_V3_CAUSAL_FORECAST/figures/delivery_r1/*.pdf' --strict
```

所需Python依赖列于 `program/figure_tools/requirements.txt`。随仓携带技能的
`setup_style/export_figure/visual_qa/check_figure/profile_data`，来源哈希与必要修补
见 `program/figure_tools/vendor_manifest.json`。唯一脚本修补是正确沿PDF Type0
的DescendantFonts检查字体嵌入，避免把已嵌入的CID字体误报为缺失；没有屏蔽警告。
灰度转换直接读取精确尺寸PNG并保留DPI，避免技能原灰度函数二次裁切主PNG。
可选 `--profile-run` 也只读取版本内 `results/annual_runs/` 的规范归档；
正常生成和 `--from-figure-data` 均不依赖仓库根目录的 ignored `runs/`。
布局检查额外直接核对所有图注与x轴标签/刻度包围盒，要求至少4pt垂直间距，
补足技能原检查只检查裁切和刻度相交的覆盖缺口。

## 证据文件

- `results/figure_data/figure_source_manifest.json`：原始输入哈希、各图源表路径和压缩后文件哈希。
- `results/figure_data/`：原始观测、逐日/逐槽主账本、SOC矩阵、候选字典/轨迹、月费用/风险和敏感性图源。
- `others/figure_contracts.json`：九图逐图论点、证据链、图型、样本量、排除规则、后端与导出规范。
- `others/figure_eda.json`：调用技能profile_data生成的类型、缺失、分布、异常值与分组检查。
- `others/figure_delivery_manifest.json`：逐图布局/文件检查、源/输入/输出哈希与运行状态。
- `others/figure_visual_review.json`：作者彩色/灰度读图回执。独立审核仍由父级指定agent完成。

重绘只覆盖本r1的图与其源数据/QA文件，不修改final_v1表格。新增模型或算法结论
不属于本图件交付；所有候选、现金与敏感性值来自已有轨迹。
