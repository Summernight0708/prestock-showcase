# 财报解析与质量分类演示

## 输入

`samples/` 包含三份合成的 BBox XHTML 文件。表格按 Poppler BBox 的页、行、词及坐标结构组织，数值与公司标识用于演示。

- `complete.xhtml`：23 项核心指标，包含本期与比较期两列。
- `missing_anchor.xhtml`：22 项核心指标，其中经营活动产生的现金流量净额作为缺失场景。
- `heading_gap.xhtml`：使用“经营数据概览”标题，展示完整报表入口对标题的依赖。

完整样例和缺锚点样例分别生成 46、44 条事实。本期与比较期各占一半，质量分类以本期合并指标集合为依据。

## 运行

在仓库根目录执行：

```bash
python -m pip install -r requirements.txt
python demo.py
```

指定输出目录：

```bash
python demo.py --output ./my-results
```

控制台结果：

```text
complete: complete, facts=46, current_metrics=23
missing_anchor: invalid, facts=44, current_metrics=22
heading_gap: invalid, facts=0, current_metrics=0
```

## 查看输出

- [结果总览](../examples/results/summary.json)
- [完整样例事实明细](../examples/results/complete/facts.json)
- [完整样例质量分类](../examples/results/complete/quality.json)
- [缺锚点样例质量分类](../examples/results/missing_anchor/quality.json)
- [标题异常样例质量分类](../examples/results/heading_gap/quality.json)

事实记录包含指标、数值、单位、期间、合并口径、列角色、页码、行号、坐标及源单元格文本。`source_input_sha256` 标识输入 XHTML；兼容原模块接口的 `source_pdf_sha256` 字段使用同一输入指纹，`data_origin` 为 `synthetic_bbox_fixture`。

## 代码结构

```text
demo.py                                  演示入口与输入输出适配
samples/                                 三类合成 BBox 样例
src/a_share_research/
  financial_report_bbox.py               原项目 BBox 解析器
  financial_reports.py                   原项目指标与期间处理
  cninfo_pipeline/quality.py             原项目质量分类器
data/metadata/                           原项目 23 项指标字典
tests/                                   解析回归与演示测试
examples/results/                        实际运行生成的示例输出
```

[源码清单](../evidence/source-manifest.json)记录复用模块、指标字典与原解析测试的文件指纹。

## 验证

```bash
python -m unittest discover -s tests -v
```

35 项测试通过，其中 31 项复用原项目解析回归，4 项验证演示流程。演示测试检查具体数值、本期与比较期、来源指纹、23/22 项指标覆盖及分类原因。

本次验证环境：Windows、Python 3.14.7、pandas 3.1.0。
