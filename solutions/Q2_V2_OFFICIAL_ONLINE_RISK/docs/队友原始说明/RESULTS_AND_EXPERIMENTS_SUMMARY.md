# 2026 C题 Q2/Q3 结果、实验与优化总报告

- 生成时间：2026-09-12T16:44:29+08:00
- 工作区：`D:\C题文件代码DEEPSEEK专用\Q2=Q3`
- Git 分支：`codex/q2-q3-finish`
- Git 提交：`74fced60afac586b4479b08d74c9399eb954f7be`
- 原始工程未修改；所有新文件均位于 DeepSeek 专用工作区。

## 1. 一页结论

- Q2 最终主模型：**ONLINE-RISK-SP**
- Q2 最终全年成本：**1380.803333 万元**
- 严格因果在线模型成本：**1380.803333064248 万元**
- 测试网格探索最低值：**1378.287021 万元**
- 相对 M1 节省：**25.192684 万元**（1.7918%）
- Q2 无条件冻结：**False**
- Q2 ONLINE 专项重新冻结：**True**
- Q2 三个题意边界后条件冻结：**True**
- Battery A/B 改变主排序：**True**
- ONLINE Scoring-A/B：**1380.8033330642481 / 1380.770759944227 万元**
- ONLINE S=10/20/30：**{'10': 1380.8033330642481, '20': 1380.2627373700163, '30': 1384.4506385797868}**
- ONLINE Bootstrap 95% CI：**[11.811093040737797, 39.64262523297586] 万元**
- Q3 条件冻结：**True**
- Q3 未无条件冻结原因：official/teacher choice between settlement A and B

核心判断：测试期最低值不能直接正式化。最终正式结果优先采用严格因果、参数选择可追溯、物理和信息边界经独立审计的模型。

## 2. 结果存放位置

```text
Q2/
├── results/q2_final_validation_v3/
│   ├── 00_source_snapshot/
│   ├── 01_cost_audit/
│   ├── 02_information_audit/
│   ├── 03_physical_audit/
│   ├── 04_terminal/
│   ├── 05_cvar_stability/
│   ├── 06_recency/
│   ├── 07_online_selector/
│   ├── 08_calibration/
│   ├── 09_statistics/
│   ├── 10_scenario_quality/
│   ├── 11_top5_rerun/
│   └── 12_paper_assets/
├── paper_assets/
├── logs/
├── config/
├── Q2_FINAL_VALIDATION_REPORT.md
└── Q2_FINAL_MODEL_DECISION.json

Q3/
├── results/
├── paper_assets/
├── paper_pack/Q3_B4_CONDITIONAL/
├── RUN_STATE.json
└── Q3_FINAL_MODEL_DECISION.json
versions/
├── baseline_source_hashes.csv
├── pip_freeze_initial.txt
├── Q2/
└── Q3/
```

## 3. 主模型对比

### 3.1 原始成本与终端库存调整

```csv
model,raw_cost_wan,final_soc,soc_gap_to_6000,inventory_adjustment_yuan,inventory_adjusted_cost_wan,planned_terminal_soc,realized_terminal_soc,realized_gap_after_plan_target,plan_target_diagnostic_cost_wan,terminal_rule_internal_pass,terminal_inventory_comparable,note
CVaR-tau-0.95-rho-0.05,1378.2870206458374,4337.9888481481485,-1662.0111518518515,778.4860235266387,1378.3648692481902,6000.0,6050.480840555558,50.48084055555773,1378.4324585243055,True,True,raw ranking uses common inventory adjustment; diagnostic reruns only Dec31 with plan target 6000 from saved Dec30 state
Recency-gamma-0.05,1380.1774247271633,4264.2630756481485,-1735.7369243518517,813.0191753655672,1380.2587266447,6000.0,6009.786462222223,9.786462222223236,1380.336065241222,True,True,raw ranking uses common inventory adjustment; diagnostic reruns only Dec31 with plan target 6000 from saved Dec30 state
CAL-CVaR,1398.3749353866112,4337.9888481481485,-1662.0111518518515,778.4860235266387,1398.452783988964,6000.0,6050.480840555558,50.48084055555773,1398.5118159320373,True,True,raw ranking uses common inventory adjustment; diagnostic reruns only Dec31 with plan target 6000 from saved Dec30 state
M1,1405.9960168988364,10800.0,4800.0,-2248.320000000298,1405.7711848988365,6000.0,6073.154094981479,73.15409498147892,1405.7683968988365,True,True,raw ranking uses common inventory adjustment; diagnostic reruns only Dec31 with plan target 6000 from saved Dec30 state
M2-TV,1405.7367444061606,4682.371377184048,-1317.6286228159524,617.1772469263524,1405.798462130853,6000.0,5961.476017504573,-38.523982495426935,1405.7822223952292,True,True,raw ranking uses common inventory adjustment; diagnostic reruns only Dec31 with plan target 6000 from saved Dec30 state
ONLINE-RISK-SP,1380.803333064248,4264.2630756481485,,,1380.8846349817845,,,,,True,True,
```

说明：原始成本反映当年真实结算；库存调整按统一影子价值把期末 SOC 折算为同库存口径。是否改变排名以实际表为准，不允许把计划终端约束当作实际终端公平。

### 3.2 Top-5 干净复跑

```csv
experiment_id,stored_total_cost_wan,clean_rerun_total_cost_wan,difference_wan,runtime_sec,config_hash,code_commit_hash,result_hash,random_seed,fresh_process_solver_invocation,abs_difference_wan,pass_lt_1e_minus_6_wan
TOP1_CVAR95S,1378.2870206458374,1378.2870206458374,0.0,114.53661740000008,cf40847830374e25b4e8b66a8e63b31c3011952c5f22ed3c8f8c6545b78d60f7,bed993b69b208a371c7897189b0921eed450abe1,acfd1605d8a5e5be04f28580aa935e42e0c6585dd491e0d71aaf550b2ee416d7,NOT_APPLICABLE_DETERMINISTIC,True,0.0,True
TOP2_CVAR90S,1378.452579984371,1378.452579984371,0.0,170.73045560000082,9f05f9e0a8a5121a72bb20342217e362a8b12858797f4fc5a65ea9875202e62f,bed993b69b208a371c7897189b0921eed450abe1,0751d8ada4ce5752f44819ae584c838e3351bf166e288fca51628d7243b8009c,NOT_APPLICABLE_DETERMINISTIC,True,0.0,True
TOP3_CVAR90M,1387.597334845664,1387.597334845664,0.0,93.98522219999997,bd63ecbb68c89ac68280cc6c97bdcfbde93095ab636289ad0670016384caac3c,bed993b69b208a371c7897189b0921eed450abe1,3bba8c70de556091eacfb238e4eeea2f74657ce360d6ce3e9fbf03327040708d,NOT_APPLICABLE_DETERMINISTIC,True,0.0,True
TOP4_CAL_CVAR,1398.3749353866117,1398.3749353866117,-2.273736754432321e-13,105.16095510000014,a37b3f9c8bb03c4708fa9f62d280fe23b3374353a56687569316dd5efb7c4ffe,bed993b69b208a371c7897189b0921eed450abe1,00b5a866decb3439375fa3c9d3700a707551331201a48bd1aea213265892d9a7,NOT_APPLICABLE_DETERMINISTIC,True,2.273736754432321e-13,True
TOP5_SIMPLE,1405.036861361186,1405.036861361186,0.0,6.668710399999327,28a22ae90eca1e62e2e0f7684c55399a794f91a14c0028f2b34edcce4a66d73f,bed993b69b208a371c7897189b0921eed450abe1,4d7df002d82fb129e03846283bed9fcb42738c2d29eb8569ccc3b7cd156945a3,NOT_APPLICABLE_DETERMINISTIC,True,0.0,True
```

Top-5 均使用固定配置重新求解，保存运行时间、配置哈希、代码提交和结果哈希。

## 4. 方法优化过程

1. **Baseline / M1**：同星期负荷预测、近期光伏预测和经验分位风险。
2. **M2-TV**：整日配对残差场景、两阶段随机规划和终端价值。
3. **CAL-CVaR**：1 月选择风险参数，在正式期冻结评估；避免测试集调参。
4. **Recency-SP**：对近期历史场景提高权重，检验残差分布漂移。
5. **ONLINE-RISK-SP**：每天只使用此前已实现成本选择有限候选参数；所有候选从当天开始时的同一真实 SOC 求解，今天的结果只能进入明天评分。

关键优化思想：不是直接追 1378，而是把测试期低值转成合法、可在线执行的选择规则。

## 5. CVaR 场景数稳定性

### 5.1 正式 tau=0.90, rho=0.05

```csv
family,tau,rho,gamma,nominal_scenario_count,actual_scenario_count_min,actual_scenario_count_median,actual_scenario_count_max,distinct_scenario_count_min,distinct_scenario_count_max,ess_min,ess_median,ess_mean,ess_max,median_effective_tail_mass,tail_support_ge_5,total_cost_wan,plan_cost_wan,emergency_cost_wan,emergency_mwh,spill_mwh,final_soc,runtime_sec,deterministic_selection,random_seed,provenance
formal_tau90_rho005_gamma0,0.9,0.05,0.0,10,10,10.0,10,10,10,9.999999999999996,9.999999999999996,9.999999999999998,9.999999999999996,0.9999999999999994,False,1398.3749353866117,1310.2499099247411,88.12502546187034,147.44592482325595,2084.392496079191,4337.9888481481485,62.78992049999943,True,NOT_APPLICABLE,independently cost-audited stored full-year run
formal_tau90_rho005_gamma0,0.9,0.05,0.0,20,17,20.0,20,17,20,17.0,19.999999999999996,19.98203592814371,19.999999999999996,1.999999999999999,False,1401.1253095765278,1311.417945613571,89.70736396295696,151.29475179600746,2076.562261999225,4872.039815943632,389.1953517,True,NOT_APPLICABLE,fresh checkpointed full-year run
formal_tau90_rho005_gamma0,0.9,0.05,0.0,30,17,30.0,30,17,30,17.0,30.0,29.72754491017964,30.0,2.999999999999999,False,1397.511744444818,1311.027663749921,86.48408069489689,145.64980133139508,2069.871803195995,4891.90370144546,515.1053038,True,NOT_APPLICABLE,fresh checkpointed full-year run
formal_tau90_rho005_gamma0,0.9,0.05,0.0,50,17,50.0,50,17,50,17.0,49.99999999999999,48.32035928143712,49.99999999999999,4.999999999999998,False,1396.5406688469554,1311.8023078883607,84.73836095859455,142.35771137310104,2061.259581092996,4887.396651851853,1291.4592952000005,True,NOT_APPLICABLE,fresh checkpointed full-year run
formal_tau90_rho005_gamma0,0.9,0.05,0.0,100,17,60.0,60,17,60,17.0,60.000000000000014,57.16766467065868,60.000000000000014,6.0,True,1394.836028649821,1312.124754365092,82.71127428472876,138.77648546824912,2059.249259252886,4856.019110425927,1498.6437265999994,True,NOT_APPLICABLE,fresh checkpointed full-year run
```

### 5.2 探索 tau=0.95, rho=0.05

```csv
family,tau,rho,gamma,nominal_scenario_count,actual_scenario_count_min,actual_scenario_count_median,actual_scenario_count_max,distinct_scenario_count_min,distinct_scenario_count_max,ess_min,ess_median,ess_mean,ess_max,median_effective_tail_mass,tail_support_ge_5,total_cost_wan,plan_cost_wan,emergency_cost_wan,emergency_mwh,spill_mwh,final_soc,runtime_sec,deterministic_selection,random_seed,provenance
exploratory_tau95_rho005_gamma002,0.95,0.05,0.02,10,10,10.0,10,10,10,8.78435926082378,8.78435926082378,8.8678579599942,9.893906988594107,0.4392179630411894,False,1378.2870206458374,1312.818759519672,65.46826112616552,108.2161062658137,2070.4979553767985,4337.9888481481485,59.93375709999964,True,NOT_APPLICABLE,independently cost-audited stored full-year run
exploratory_tau95_rho005_gamma002,0.95,0.05,0.02,20,17,20.0,20,17,20,16.83866585349261,17.78770443290993,17.921672258872253,19.738189935838413,0.8893852216454973,False,1388.0508665120446,1315.1501676334776,72.90069887856717,120.95469040042208,2112.7137471489023,4918.621590565215,283.40563380000003,True,NOT_APPLICABLE,fresh checkpointed full-year run
exploratory_tau95_rho005_gamma002,0.95,0.05,0.02,50,17,50.0,50,17,50,16.83866585349261,44.740259764245714,43.46667753704343,46.213256106256,2.237012988212288,False,1388.0340163521585,1315.190568214768,72.84344813739038,121.08011651085064,2099.522185341408,4944.504790469311,1300.9361606000002,True,NOT_APPLICABLE,fresh checkpointed full-year run
exploratory_tau95_rho005_gamma002,0.95,0.05,0.02,100,17,60.0,60,17,60,16.83866585349261,53.70674685309252,51.40060807457141,53.70674685309252,2.6853373426546283,False,1385.3159105846894,1315.4990190154572,69.81689156923215,116.10392393356172,2101.629204294095,4921.014194453909,1486.9857473000002,True,NOT_APPLICABLE,fresh checkpointed full-year run
exploratory_tau95_rho005_gamma002,0.95,0.05,0.02,150,17,60.0,60,17,60,16.83866585349261,53.70674685309252,51.40060807457141,53.70674685309252,2.6853373426546283,False,1385.3159105846894,1315.4990190154572,69.81689156923215,116.10392393356172,2101.629204294095,4921.014194453909,1486.9857473000002,True,NOT_APPLICABLE,exact structural alias of S100: both use all <=60 eligible days
```

重点读取 `median_effective_tail_mass`、`tail_support_ge_5`、`actual_scenario_count_*` 和总成本，而不是只看名义场景数。

## 6. Recency 参数敏感性

```csv
gamma,weight_half_life_days,ess_min,ess_median,ess_mean,ess_max,min_normalized_weight,max_normalized_weight,total_cost_wan,plan_cost_wan,emergency_cost_wan,emergency_mwh,spill_mwh,final_soc,runtime_sec,post_hoc_only,provenance
0.0,inf,9.999999999999996,9.999999999999996,9.999999999999998,9.999999999999996,0.1,0.1,1413.1526357523246,1293.6199234357946,119.53271231653008,199.0281967254437,1891.4416977415076,4289.552805648148,85.8010405,True,fresh checkpointed full-year run
0.01,69.31471805599453,9.66008250089636,9.66008250089636,9.684301315245142,9.973333159471569,0.0734468843450294,0.1324973285054993,1404.4563185105878,1293.5741994455132,110.88211906507452,182.8104345001104,1891.135357782553,4289.552805648148,75.61359330000005,True,fresh checkpointed full-year run
0.02,34.657359027997266,8.78435926082378,8.78435926082378,8.8678579599942,9.893906988594107,0.0521107820076569,0.1695879846581261,1395.3380438360118,1293.528803428531,101.80924040748071,169.06137195910185,1899.590974049584,4289.552805648148,58.85087310000017,True,independently audited stored full-year run
0.03,23.104906018664845,7.678873245249522,7.678873245249522,7.8295439954306385,9.7640660930386,0.035784926791686,0.2100880577418002,1377.6559188381466,1296.540366965482,81.11555187266464,132.0238107615991,1923.6239079377212,4272.547658148148,90.28921039999932,True,fresh checkpointed full-year run
0.04,17.328679513998633,6.595784555262508,6.595784555262508,6.801633934056774,9.58794697558613,0.0238542227399714,0.25263891497458,1378.7069509163264,1294.512825572506,84.19412534382053,136.94749780849472,1908.872655123941,4264.2630756481485,82.11055529999976,True,fresh checkpointed full-year run
0.05,13.862943611198904,5.6560180944747405,5.6560180944747405,5.898427397714137,9.371123437275262,0.0154895742726154,0.2959430893225981,1380.1774247271633,1295.6369236191567,84.54050110800658,136.33834563587425,1944.892452163037,4264.2630756481485,52.728694900000846,True,independently audited stored full-year run
0.07,9.902102579427789,4.268386788581164,4.268386788581164,4.537124309887203,8.842103153290209,0.0061240276611285,0.3807793199639943,1383.8665692081056,1290.172616864839,93.69395234326664,151.27477704975016,1906.426133029484,4427.350223777773,74.22858799999995,True,fresh checkpointed full-year run
0.1,6.931471805599452,3.0592786572535458,3.0592786572535458,3.30909008427984,7.914591208177648,0.0013570309507981,0.4953671420942297,1393.2894499261624,1280.9329396651924,112.35651026096993,180.41992428416611,1826.9882016433617,4270.885713240741,85.00635890000012,True,fresh checkpointed full-year run
```

所有 gamma 结果标记为 post-hoc sensitivity，不允许据此直接替换正式参数。若若干相邻 gamma 形成连续低谷，可以说明近期结构有真实价值；仍必须通过因果选择才能正式化。

## 7. 同基线单因素消融

```csv
variant,changed_component,scenario_count,terminal,terminal_lambda,cvar_beta,cvar_weight,total_cost_wan,plan_cost_wan,emergency_cost_wan,emergency_mwh,spill_mwh,final_soc,runtime_sec,config_hash,incremental_saving_vs_base_wan,inventory_adjusted_cost_wan,incremental_contribution_not_causal
Base,none,10,continuous,0.0,0.0,0.0,1423.1583333284552,1291.09592085668,132.06241247177525,233.45935888339145,1971.8511703968188,1201.5683760509262,132.294715,907a81399ded7fbfcc70ef02f99988c14e935b6e3b332b177842c8bdd424fd7d,0.0,1423.383091865721,True
Base+recency,scenario recency weighting gamma=0.05,10,continuous,0.0,0.0,0.0,1386.840816778393,1294.021025724661,92.81979105373202,157.0277159781681,2002.2739364116987,1200.0,154.83828640000047,25d0ba929ec5cac03e8fabc050d857935044f423c6fd6555f38a8956d259ef21,36.31751655006224,1387.065648778393,True
Base+CVaR,CVaR tau=0.90 rho=0.05,10,continuous,0.0,0.9,0.05,1409.09176055256,1306.5793698455327,102.51239070702714,182.48643344199425,2173.514320785784,1341.1846942439445,111.51285759999972,76b2e528e435cfcc8f040d4491d68d22d974e66775f6997b29f8ffa0d16222b5,14.066572775895338,1409.3099794614816,True
Base+terminal-value,terminal inventory value lambda=0.4684,10,value,0.4684,0.0,0.0,1413.1526357523246,1293.6199234357946,119.53271231653008,199.0281967254437,1891.4416977415076,4289.552805648148,109.43190419999974,8b7cde5ecdbf9fe1a30c83ada1a2a28d0f3c5d023a428bfecf5ef7ab206cea85,10.005697576130617,1413.232753098908,True
Base+similarity,forecast-feature similarity conditioning K=10,10,continuous,0.0,0.0,0.0,1406.0126390386788,1297.5154429303632,108.4971961083157,192.0882485224421,2026.2453308349968,1200.0,100.29175159999976,41dda8c8931a2c2e40914bc3292810968f0a197d9054cfa0aaba85e082daf6c4,17.14569428977643,1406.237471038679,True
Base+medoid,farthest-medoid trajectory reduction K=10,10,continuous,0.0,0.0,0.0,1411.4216757160232,1339.5568516619462,71.86482405407696,131.34307085981033,2501.272141801473,1356.1860777777745,84.8863323000005,7b52f2052a7d629dfda4514cbef4572603936858383d8568192e09f946cfad83,11.736657612432056,1411.63919196014,True
```

表中 `incremental_saving_vs_base_wan` 只是增量经验贡献，不是严格因果效应，因为模块间仍可能存在交互。

## 8. 严格因果在线选择器

```csv
model,days,plan_cost_yuan,emergency_cost_yuan,total_cost_yuan,total_cost_10k_yuan,grid_purchase_kwh,emergency_kwh,emergency_intervals,emergency_days,spill_kwh,charge_kwh,discharge_kwh,soc_min_kwh,soc_max_kwh,end_soc_kwh,cross_day_soc_residual_kwh,balance_residual_kwh,soc_residual_kwh,simultaneous_actual_intervals,solver_failures,runtime_seconds
ONLINE-RISK-SP,334,13068019.45803071,740013.8726117717,13808033.330642482,1380.803333064248,21060861.801040016,121324.59054901858,746,135,2054802.41466566,6261877.079940142,5073682.597983431,1200.0,10800.0,4264.2630756481485,0.0,2.273736754432321e-13,9.094947017729282e-13,0,0,234.5468069000008
```

选择频率：

```json
{
  "nocvar_g0.05": 72,
  "cvar_t0.95_r0.20_g0.02": 39,
  "cvar_t0.90_r0.05_g0.00": 37,
  "cvar_t0.90_r0.05_g0.05": 36,
  "cvar_t0.90_r0.20_g0.00": 36,
  "cvar_t0.90_r0.05_g0.02": 33,
  "cvar_t0.90_r0.20_g0.05": 24,
  "cvar_t0.95_r0.20_g0.05": 20,
  "cvar_t0.95_r0.05_g0.02": 17,
  "nocvar_g0.02": 14,
  "cvar_t0.90_r0.20_g0.02": 3,
  "nocvar_g0.00": 3
}
```

因果规则：候选参数评分只使用过去已结算日；当天 15 个候选都从同一真实 SOC 出发；选中方案执行后才把当天各候选结果加入历史。

## 9. 成本、物理与信息审计

### 9.1 既有正式候选

```csv
model,plan_cost_yuan,emergency_cost_yuan,total_cost_yuan,reported_total_cost_yuan,difference_yuan,pass_lt_0.01_yuan,source_npz_sha256
M1,13402717.394037362,657242.7749510019,14059960.168988364,14059960.168988364,0.0,True,07a22cc700231f04da3e3c8baf569506aca15a794cdc93dd952e5fda33c8b860
M2-TV,12950161.427076302,1107206.016985303,14057367.444061603,14057367.444061603,0.0,True,482dbb52822bb808a0fde9b5eb4d7b01339a2aba3b340751b2c0e25cd6f43636
CAL-CVaR,13102499.09924741,881250.2546187033,13983749.353866111,13983749.353866115,-1.862645149230957e-09,True,00b5a866decb3439375fa3c9d3700a707551331201a48bd1aea213265892d9a7
Recency-gamma-0.05,12956369.236191569,845405.0110800657,13801774.247271633,13801774.247271633,0.0,True,ea642c6bbba1e79fa5b3c66cace9d82ab1dea2e6d246eedc39a5744b4bd5b306
CVaR-tau-0.95-rho-0.05,13128187.59519672,654682.6112616551,13782870.206458377,13782870.206458377,0.0,True,acfd1605d8a5e5be04f28580aa935e42e0c6585dd491e0d71aaf550b2ee416d7
```

### 9.2 在线模型独立复算

```csv
model,plan_cost_yuan,emergency_cost_yuan,total_cost_yuan,reported_total_cost_yuan,difference_yuan,pass_lt_0.01_yuan,source_npz_sha256
ONLINE-RISK-SP,13068019.45803071,740013.8726117717,13808033.330642482,13808033.33064248,3.725290298461914e-09,True,56f3cfa663d2851f90ef9b7e20972542488aa81584684ae7d71c7f0c0f039fea
```

### 9.3 时间标签双解释

```csv
model,mapping_A_total_cost_wan,mapping_B_total_cost_wan,delta_cost_wan_B_minus_A,absolute_delta_pct,mapping_A_emergency_mwh,mapping_B_emergency_mwh,mapping_A_final_soc,mapping_B_final_soc,robust_below_0.1pct
M1,1405.9960168988364,1405.3354506807932,-0.6605662180431864,0.0469820831712011,107.86895765391832,107.08281159713638,10800.0,10800.0,True
M2-TV,1405.7367444061606,1405.107000169729,-0.6297442364316339,0.0447981628806084,182.89139931223303,181.76443254180336,4682.371377184048,4743.448534684047,True
CAL-CVaR,1398.3749353866117,1397.560775110658,-0.8141602759533271,0.0582218870884034,147.44592482325595,146.04062031972117,4337.9888481481485,4375.707413148149,True
Recency-gamma-0.05,1380.1774247271633,1379.9647086058535,-0.2127161213097679,0.0154122301595983,136.33834563587425,136.05069352254876,4264.2630756481485,4301.981640648149,True
```

最大替代映射成本变化：0.0582218870884034%。若低于 0.1%，可认为结果对时间标签解释稳健。

## 10. 日级统计

```csv
win_days,loss_days,tie_days,mean_daily_delta_yuan,median_daily_delta_yuan,P10_yuan,P25_yuan,P50_yuan,P75_yuan,P90_yuan,max_saving_yuan,max_loss_yuan,comparison,max_saving_date,max_loss_date
227,107,0,228.1760931803881,815.2573732014098,-3454.894013377704,-760.3955815722966,815.2573732014098,1882.558491488112,3190.743636400743,18428.44549674142,-22259.006853325343,Calibrated SP-CVaR vs M1 Empirical Quantile,2025-07-01,2025-12-06
161,173,0,220.41344369907625,-24.665292125229826,-3044.0109328346307,-956.7720788234165,-24.665292125229826,905.3980745006202,3364.152196020524,36962.21227820456,-21660.104910038088,Calibrated SP-CVaR vs M2-TV,2025-07-06,2025-12-06
```

Bootstrap 区间包含 0：**True**。日级 Wilcoxon 显著不等于年累计成本一定稳定改善。

## 11. Q2 执行规范完成情况

| STEP | 状态 | 证据 |
|---:|---|---|
| 1 | 完成 | `00_source_snapshot/` |
| 2 | 完成 | `01_cost_audit/independent_cost_audit.csv` |
| 3 | 完成 | 信息、物理、Emergency、非预见性审计 |
| 4 | 完成 | `02_information_audit/time_mapping_dual_run.csv` |
| 5 | 完成 | `04_terminal/terminal_fairness_v2.csv` |
| 6 | 完成 | `05_cvar_stability/cvar_unit_test.json` |
| 7 | 完成 | 正式 CVaR S=10/20/30/50/100 |
| 8 | 不适用 | 场景选择为确定性，无随机种子 |
| 9 | 完成 | 探索 CVaR95 S=20/50/100/150 |
| 10 | 完成 | `06_recency/recency_gamma_sensitivity.csv` |
| 11 | 完成 | January 校准选择表 |
| 12 | 完成 | leave-block-out 稳定性 |
| 13 | 完成 | `07_online_selector/` |
| 14 | 完成 | 日级与月度统计 |
| 15 | 完成 | Wilcoxon 与 7-day bootstrap |
| 16 | 完成 | 场景质量审计 |
| 17 | 完成 | Top-5 clean rerun |
| 18 | 完成 | 同基线单因素消融 |
| 19 | 完成 | Q2 公式、算法、结果、限制 |
| 20 | 完成 | Q2 论文表图 |
| 21 | 完成 | 最终验证报告 |
| 22 | 完成 | 最终决策 JSON |
| 23 | 按证据判定 | 以 `q2_frozen` 为准 |

## 12. Q3 当前结果

- 条件 A 主结果：{'model': 'B4_A_N20', 'cost_wan': 1333.8574661767923}
- 条件 B 主结果：{'model': 'B4_B_N20', 'cost_wan': 1334.0302137633269}
- A/B 差额：0.17274758653456956 万元
- 正式选择条件：Economic Gate OFF。

### B4/B5 对比

```csv
days,nsc,settlement,gate_enabled,plan_yuan,up_yuan,down_yuan,emergency_yuan,total_yuan,total_cost_wan,up_mwh,down_mwh,emergency_mwh,spill_mwh,final_soc_kwh,gate_accepted_events,gate_total_events,past_frozen_pass,max_balance_residual_kwh,max_soc_residual_kwh,simultaneous_charge_discharge_slots,physical_pass,experiment_id,runtime_sec,scenario_source,time_mapping,causality
334,10,A_cost,False,11979463.565837936,1136238.9319272216,0.0,241339.5840704993,13357042.081835648,1335.7042081835648,985.853339613174,0.0,44.17576237779546,1508.6357763287494,4263.149318148148,1002,1002,True,2.273736754432321e-13,9.094947017729282e-13,0,True,B4_A_N10,94.09450110000034,"GT07 whole-day past residuals, local path adapter",attachment 00:10 -> result 00:10-00:20,scenario indices j<day; event forecasts use issue-time data
334,10,A_cost,True,11979463.565837936,1137067.0661631976,0.0,241333.89022563293,13357864.52222676,1335.786452222676,986.4952861486662,0.0,44.17576237779546,1509.26724253746,4263.149318148148,886,1002,True,2.273736754432321e-13,9.094947017729282e-13,0,True,B5_A_N10,94.1258084000001,"GT07 whole-day past residuals, local path adapter",attachment 00:10 -> result 00:10-00:20,scenario indices j<day; event forecasts use issue-time data
334,10,B_credit,False,12158927.738583976,994441.07004853,-65933.50134092645,280710.0501909127,13368145.357482482,1336.814535748248,824.607133799793,218.5292494261232,51.22044752432092,1432.2610414511705,4283.203830648148,1002,1002,True,2.273736754432321e-13,9.094947017729282e-13,0,True,B4_B_N10,110.10442119999789,"GT07 whole-day past residuals, local path adapter",attachment 00:10 -> result 00:10-00:20,scenario indices j<day; event forecasts use issue-time data
334,10,B_credit,True,12158928.444877414,996104.9586046952,-65540.9980993676,280676.3533017321,13370168.758684464,1337.0168758684465,826.1267840823597,217.53799087088495,51.21442140765425,1434.807177429374,4283.203830648148,973,1002,True,2.273736754432321e-13,9.094947017729282e-13,0,True,B5_B_N10,110.39425550000306,"GT07 whole-day past residuals, local path adapter",attachment 00:10 -> result 00:10-00:20,scenario indices j<day; event forecasts use issue-time data
```

### Gate 检验

```csv
settlement,gate_total_saving_yuan,mean_daily_saving_yuan,median_daily_saving_yuan,P10_yuan,P50_yuan,P90_yuan,win_days,loss_days,wilcoxon_p,bootstrap_mean_ci_low_yuan,bootstrap_mean_ci_high_yuan,gate_supported_oos
A_cost,-822.4403911096706,-2.462396380567876,0.0,0.0,0.0,0.0,0,3,0.25,-6.236623755031583,0.0,False
B_credit,-2023.401201982644,-6.05808743108576,0.0,0.0,0.0,0.0,4,9,0.010498046875,-11.571408055136956,-1.5791313573395491,False
```

Q3 仍不能无条件冻结，唯一关键阻塞是官方或教师对下调结算 A/B 的最终解释。

## 13. 复现与依赖

Python 环境：`D:\C题文件代码DEEPSEEK专用\Q2=Q3\.venv`

```powershell
cd 'D:\C题文件代码DEEPSEEK专用\Q2=Q3'
& '.\\.venv\\Scripts\\python.exe' -m pip install -r requirements-lock.txt
& '.\\.venv\\Scripts\\python.exe' -m pytest -q
& '.\\.venv\\Scripts\\python.exe' '.\\run_q2_cvar_stability_v3.py'
& '.\\.venv\\Scripts\\python.exe' '.\\run_q2_recency_sensitivity_v3.py'
& '.\\.venv\\Scripts\\python.exe' '.\\run_q2_online_selector.py' --workers 15
& '.\\.venv\\Scripts\\python.exe' '.\\run_q2_top5_clean_rerun.py'
& '.\\.venv\\Scripts\\python.exe' '.\\run_q2_paired_ablation.py'
& '.\\.venv\\Scripts\\python.exe' '.\\build_q2_final_validation_v3.py'
& '.\\.venv\\Scripts\\python.exe' '.\\build_q3_final_report.py'
```

## 14. 仍需诚实保留的边界

1. 外部方案与本题的信息边界、终端处理和结算口径不完全一致。
2. 测试期网格最低值仍是探索结果，不能直接作为正式主模型。
3. 场景来自历史经验残差，对分布突变外推有限。
4. Q3 下调结算 A/B 仍需官方或教师最终裁定。
5. 所有结果为给定年度样本内严格因果回放，不代表未来保证收益。
6. Battery Interpretation A/B 会改变 Q2 主模型排序，1380.803333 万元仅在 A 口径下成立。

## 15. ONLINE-RISK-SP 最终封闭验证

# ONLINE-RISK-SP Final Closure Report

- q2_refrozen: True
- scoring A/B: 1380.8033330642481 / 1380.770759944227
- scenario-count stability: True
- scenario-count costs: {10: 1380.8033330642481, 20: 1380.2627373700163, 30: 1384.4506385797868}
- scenario-count relative range/std: 0.0030295373445948515 / 0.0015147686722974257
- online Wilcoxon p: 2.8529424208294957e-14
- online bootstrap CI: [11.811093040737797, 39.64262523297586]
- time mapping delta: 0.05612987166734709%
- clean reproduction: True
- decision reason: ONLINE information, fairness, scoring, scenario-count, statistical, time-mapping, reproduction, and paper-honesty gates passed.

## Required 18 Answers

1. Day-d actual Load accessed before plan: 0.
2. Day-d actual PV accessed before plan: 0.
3. Scenario source dates >= decision date: 0.
4. Selector day-d realized-cost leakage count: 0.
5. Counterfactual future-mutation test pass: True.
6. All candidates share the same initial SOC: True.
7. All candidates share the same forecast and executor: True.
8. Current Scoring-A does not include day-end SOC value; Scoring-B does.
9. Scoring-A/B costs: 1380.8033330642481 / 1380.770759944227 万元; strategy agreement=0.8053892215568862.
10. Required ONLINE S=10/20/30 costs: {10: 1380.8033330642481, 20: 1380.2627373700163, 30: 1384.4506385797868}. Optional S=50 was stopped because the machine hit solver memory limits; the resource incident is recorded separately.
11. Scenario-count candidate/tau/rho/gamma agreement is in `03_scenario_count/online_selection_path_agreement.csv`.
12. ONLINE vs M1 Wilcoxon p-value: 2.8529424208294957e-14.
13. ONLINE vs M1 7-day block bootstrap 95% CI: [11.811093040737797, 39.64262523297586] 万元.
14. Monthly stability pass: True.
15. ONLINE time-mapping A/B cost delta: 0.05612987166734709%.
16. Clean reproduction cost: 1380.8033330642481 万元; pass=True.
17. Meta-overfitting limitation documented: True.
18. Q2 can be unconditionally refrozen: True.


## 16. 三个题意边界专项验证

# Q2 三个题意边界问题专项验证报告

生成时间：2026-09-12T16:44:28+08:00

## 结论

- `spill` 术语已统一修正为“未利用剩余供给量”，英文为 `unutilized surplus energy`。
- 题目只明确给出 Jan 1 00:00 SOC=6000 kWh；Feb 1 SOC=6000 是中性初始化假设，不是题面直接条件。
- 当前 Q2 主执行口径为 Battery Interpretation A：

```text
0:00 冻结计划购电 G
日内储能依据当前及过去实际 Load/PV/SOC 因果响应
不足部分使用 5 倍价格紧急购电
```

- Interpretation B 作为严格保守敏感性：

```text
0:00 同时冻结计划购电 G 与全天储能充放电计划 C/D
实际偏差由 Emergency 或未利用剩余供给吸收
```

## 1. Spill 术语审计

详细审计见：

`Q2/results/q2_three_issues_validation/Q2_SPILL_TERMINOLOGY_AUDIT.md`

当前模型中：

$$W_t=G_t+V_t+D_t-L_t-C_t$$

同类平衡后的剩余量可能来自计划购电、光伏或允许的放电，模型没有追踪其电源来源。
因此不能将 $W_t$ 解释为严格光伏弃电。

## 2. Feb 1 初始 SOC 敏感性

### 2.1 年度成本

```csv
initial_soc_kwh,model,total_cost_wan,plan_cost_wan,emergency_cost_wan,emergency_mwh,surplus_mwh,final_soc_kwh,runtime_sec,physical_pass,leakage_pass

1200.0,ONLINE-RISK-SP,1381.0325250620372,1307.03113780086,74.00138726117717,121.32459054901858,2054.80241466566,4264.2630756481485,326.6813609000001,True,True

1200.0,M1,1405.8926846808968,1340.1684071857967,65.72427749510018,107.8689576539183,2848.775554466253,10800.0,4.021870500000659,True,True

1200.0,M2-TV,1405.965662896415,1295.2450611978848,110.72060169853027,182.89139931223303,1962.430788413814,4682.371377184048,354.4123130000007,True,True

3000.0,ONLINE-RISK-SP,1380.9463691495991,1306.944981888422,74.00138726117717,121.32459054901858,2054.80241466566,4264.2630756481485,326.04481289999967,True,True

3000.0,M1,1405.9408670809512,1340.216589585851,65.72427749510037,107.86895765391871,2850.8248265635893,10800.0,4.041308399999252,True,True

3000.0,M2-TV,1405.8798780738923,1295.1592763753622,110.72060169853027,182.89139931223303,1962.4432027489,4682.371377184048,347.94205669999974,True,True

6000.0,ONLINE-RISK-SP,1380.803333064248,1306.801945803071,74.00138726117717,121.32459054901858,2054.80241466566,4264.2630756481485,234.5468069000008,True,True

6000.0,M1,1405.9960168988364,1340.2717394037363,65.72427749510018,107.86895765391832,2854.1748998122257,10800.0,3.451481900003273,True,True

6000.0,M2-TV,1405.7367444061606,1295.0161427076305,110.72060169853027,182.89139931223303,1962.4390181607275,4682.371377184048,290.4315748000008,True,True

9000.0,ONLINE-RISK-SP,1380.6611958495496,1306.6598085883725,74.00138726117717,121.32459054901858,2054.80241466566,4264.2630756481485,339.57046529999934,True,True

9000.0,M1,1406.0178731409785,1340.293595645878,65.72427749510018,107.86895765391832,2857.512730454845,10800.0,5.076631300000372,True,True

9000.0,M2-TV,1405.592574511785,1294.8719728132546,110.72060169853027,182.89139931223303,1962.382564505789,4682.371377184048,350.50968100000136,True,True

10800.0,ONLINE-RISK-SP,1380.5820244440336,1306.5806371828564,74.00138726117717,121.32459054901858,2054.8759273099804,4264.2630756481485,338.0208695000001,True,True

10800.0,M1,1406.0293148584014,1340.3050373633012,65.72427749510018,107.86895765391832,2859.512730454845,10800.0,4.797903299999234,True,True

10800.0,M2-TV,1405.5166092497932,1294.7960075512628,110.72060169853027,182.89139931223303,1962.4393627237896,4682.371377184048,350.2868487999985,True,True
```

### 2.2 轨迹收敛

```csv
initial_soc_kwh,max_abs_daily_end_soc_difference_kwh,mean_abs_daily_end_soc_difference_kwh,first_30d_max_difference_kwh,days_until_continuous_within_100_kwh,date_stable_within_100_kwh

1200.0,0.0,0.0,0.0,0,2025-02-01

3000.0,0.0,0.0,0.0,0,2025-02-01

6000.0,0.0,0.0,0.0,0,2025-02-01

9000.0,0.0,0.0,0.0,0,2025-02-01

10800.0,0.0,0.0,0.0,0,2025-02-01
```

### 2.3 数值判断

- ONLINE 成本范围：0.4505006180036162
- 最大相对成本变化：0.03262597990720918
- ONLINE 在全部初始 SOC 下排名第一：True

初始 SOC 官方口径应写成：

> 题目仅给出 2025 年 1 月 1 日 0:00 储电量为 6000 kWh，而问题二正式输出从 2 月 1 日开始。本文将其作为 2 月 1 日的中性初始化基准，并通过初始 SOC 敏感性分析检验该假设的影响。

## 3. 储能解释 A/B

```csv
interpretation,model,total_cost_wan,plan_cost_wan,emergency_cost_wan,emergency_mwh,surplus_mwh,charge_mwh,discharge_mwh,final_soc_kwh,balance_residual_kwh,soc_residual_kwh,future_leakage_count,emergency_to_battery_kwh,solver_failures

A,ONLINE-RISK-SP,1380.803333064248,1306.801945803071,74.00138726117717,121.32459054901858,2054.80241466566,6261.877079940142,5073.682597983431,4264.2630756481485,2.273736754432321e-13,9.094947017729282e-13,0,0.0,0

A,M1,1405.9960168988364,1340.2717394037363,65.72427749510018,107.86895765391832,2854.1748998122257,6801.949745784423,5505.259294085383,10800.0,2.273736754432321e-13,9.094947017729282e-13,0,0.0,0

A,M2-TV,1405.7367444061606,1295.0161427076305,110.72060169853027,182.89139931223303,1962.4390181607275,6224.210634136805,5042.796479411347,4682.371377184048,2.273736754432321e-13,9.094947017729282e-13,0,0.0,0

B,ONLINE-RISK-SP,1567.5284520365756,1305.7420445096195,261.78640752695605,523.2851737093221,2571.826700462896,5759.251162308681,4666.373754310828,4466.319065781069,2.273736754432321e-13,9.094947017729282e-13,0,0.0,0

B,M1,1455.9737439817302,1340.1810253527724,115.7927186289578,257.1999934715017,3038.4860377758537,6615.193102954209,5353.986413392909,10800.0,2.273736754432321e-13,9.094947017729282e-13,0,0.0,0

B,M2-TV,1587.1341205213942,1298.0738622433132,289.06025827808094,570.8809724161538,2515.992993208604,5727.6240102712445,4640.4179712464975,4841.641192456274,2.273736754432321e-13,9.094947017729282e-13,0,0.0,0
```

- ONLINE A 成本：1380.803333064248 万元
- ONLINE B 成本：1567.5284520365756 万元
- 相对差异：13.522933679335162%
- 模型主排序稳定：False

A 口径是本文正式主口径；B 口径作为更严格的题意敏感性。若 B 口径排名仍保持
ONLINE 第一，则 1380.803333 万元不依赖“储能可以日内重新调整”这一假设的单一解释。

## 4. 最终判断

- Feb 1 SOC 敏感性完成：True
- Battery A/B 完成：True
- A 口径运行与数值有效：True
- Q2 无条件冻结：False
- Q2 条件冻结：True
- Battery A/B 是否改变主排序：True
- 正式储能解释：A
- 正式剩余供给术语：未利用剩余供给量 / unutilized surplus energy

若 Battery A/B 改变主排序，则 1380.803333 万元只能表述为
“储能允许日内因果响应”假设下的结果；严格全日储能计划口径下的结果必须同时保留。

## 5. 论文建议措辞

### 模型假设

> 题目仅明确给出 2025 年 1 月 1 日 0:00 的储电量为 6000 kWh，未单独规定 2 月 1 日的初始储电量。本文以 6000 kWh 作为 2 月 1 日的中性初始化基准，并对可行边界及中间值进行敏感性检验。

> 问题二要求在每天 0:00 制定并冻结计划购电策略。本文将外网计划购电量视为日前不可调整变量；储能作为微网内部平衡资源，允许依据当前及此前已经观测到的负荷、光伏和 SOC 进行因果充放电，不使用未来真实信息。

### 符号说明

> 代码中的 `spill` 及公式中的 $W_t$ 表示未利用剩余供给量，即计划购电、光伏和允许放电在满足负荷与充电需求后仍未被利用的剩余能量。模型未进一步区分其电源来源，因此不解释为严格的光伏弃电量。

## 6. 最终决策 JSON

```json
{
  "spill_term_corrected": true,
  "formal_spill_term_cn": "未利用剩余供给量",
  "formal_spill_term_en": "unutilized surplus energy",
  "feb1_soc_is_assumption": true,
  "initial_soc_sensitivity_complete": true,
  "initial_soc_cost_range_wan": 0.4505006180036162,
  "initial_soc_max_delta_pct": 0.03262597990720918,
  "initial_soc_ranking_stable": true,
  "battery_interpretation_A_cost_wan": 1380.803333064248,
  "battery_interpretation_B_cost_wan": 1567.5284520365756,
  "battery_interpretation_delta_pct": 13.522933679335162,
  "battery_model_ranking_stable": false,
  "formal_battery_interpretation": "A: grid plan fixed; battery responds causally to realized information",
  "interpretation_A_result_valid": true,
  "main_q2_result_still_valid": false,
  "q2_unconditional_freeze": false,
  "q2_conditional_freeze": true,
  "battery_interpretation_ranking_changed": true,
  "paper_ready_final": true,
  "paper_wording_updated": true,
  "decision_reason": "The three issues were audited, but at least one sensitivity threshold or required artifact is not satisfied."
}
```

