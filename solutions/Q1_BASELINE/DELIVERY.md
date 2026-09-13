# Q1_BASELINE 最终交付入口

本次只补齐归档和图件，不重新求解、不优化模型、不生成新 Q1 v2。原文件名中的 `result1_v2.xlsx` 和 `q1_reproduce_v2.py` 是既有名称。

**本目录所有模型结果继续使用旧 Time A：第一段为当天 00:10-00:20，最后一段为次日 00:00-00:10，145 个状态覆盖当天 00:10 至次日 00:10。** 不得将它们标为新确认的区间结束标签 / 自然日口径结果。旧报告中的“唯一时间口径”只是当时的历史结论。

## 正式交付位置

| 分类 | 正式入口 | 说明 |
|---|---|---|
| results | [结果工作簿](results/baseline/result1_v2.xlsx) | 历史正式工作簿的逐字节副本，144 段购电量和 6 组充放电量 |
| results | [逐段账本](results/baseline/q1_dispatch.csv) | 购电、充放电、剩余供给、状态和费用 |
| results | [原始摘要](results/baseline/q1_summary.json) | 既有求解结果、历史审计和环境记录 |
| results | [图件源数据](results/figure_data/) | 9 份图表专用 CSV，均可追溯到现有账本 |
| figures | [出版图件](figures/) | 原始、过程、结果各 3 张；每张 PNG + PDF + SVG，共 27 文件 |
| program | [归档出图程序](program/q1_delivery_figures.py) | 仅归档、核查、出图；不调用优化器 |
| program | [历史求解程序](program/q1_reproduce_v2.py) | 保持原样，本次未执行 |
| others | [历史报告副本](others/baseline_reports/) | 原论文报告、清单和仓库状态说明 |
| others | [图注与图件索引](others/FIGURE_CAPTIONS.md) | 每图用途、时间和统计范围 |
| others | [数据审核](others/delivery_data_audit.json) | 输入、CSV、XLSX、物理残差和费用核查 |
| others | [文件清单](others/delivery_manifest.json) | 本目录文件的 SHA-256；清单本身除外 |

原 `result/`、根部三个旧报告全部保留；规范读取入口为上述 `results/` 和 `others/`。逐文件映射见 [archive_mapping.json](others/archive_mapping.json)。原 `历史副本/` 中的工作簿仍是非权威副本，不应代替正式 `result1_v2.xlsx`。

旧 `交付清单.md` 中“没有独立图件”的描述已由本说明取代；该文件作为历史证据不改写。其内部相对路径按原 Q1 根目录解释，不能从 `others/baseline_reports/` 直接套用。

## 结果边界

既有储能方案购电费为 **35,126.948589 元**，同输入无储能参照为 **48,052.046591 元**，节约 **12,925.098002 元（26.898122%）**。参照直接计算 `sum(price * max(load_kw - pv_kw, 0) / 6)`，没有新的 LP 求解。

本次核查保证归档复制和图表与现有结果一致，不构成重新评估新时间口径、重建最优性证书或更新模型评分。图件是单个确定性序列的展示，不提供年化收益、置信区间或泛化保证；过程图也不是伪造的求解器收敛曲线。

## 再生成图件与核查

在仓库根目录，使用已具备 `program/requirements_delivery.txt` 所列依赖的 Python：

```bash
.venv/bin/python solutions/Q1_BASELINE/program/q1_delivery_figures.py
.venv/bin/python solutions/Q1_BASELINE/program/q1_delivery_figures.py --audit-only
```

第一条仅重复后处理，不执行模型。第二条核查已有成果，不重新绘图。出图代码实际复用了 `program/vendor/figure_skill/` 中随附的技能脚本，中文字体和 OFL 许可在 `program/vendor/fonts/`。PDF 嵌入字体；SVG 保留可编辑文字，外部编辑器需安装同名字体才能保持相同字形。

只交付本目录也能从账本再生成图；当仓库中的 `data/附件1.xlsx`、`data/附件5/result1.xlsx` 存在时还会自动核对附件。若移走原附件，审核会明确记为 `NOT_PRESENT`，不会冒称完成输入核验。历史求解程序仍依赖仓库级 `data/`、`plan/` 和 SciPy；其旧运行清单保留原 Windows 路径与历史环境，不等同于新的运行记录。

图件形式审核、分类审核、CSV 回读、原件保全分别记录在 `others/figure_file_audit.json`、`figure_category_audit.json`、`figure_source_audit.json`、`historical_preservation_audit.json`；目视结果见 `others/VISUAL_REVIEW.md`。

技能脚本对Type0字体的可能未嵌入警告保留原文，全部PDF的后代字体嵌入流另经 `others/pdf_font_embedding_audit.json` 核实。历史 `__pycache__/` 属运行缓存，未删除且不纳入交付哈希范围，不应打入正式交付包。
