from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from a_share_research.financial_report_bbox import (
    _parse_statement_heading,
    count_statement_headings,
    parse_bbox_xhtml,
)
from a_share_research.financial_reports import detect_period_basis


class FinancialReportBBoxTests(unittest.TestCase):
    def test_statement_heading_counter_ignores_numbered_continuation_and_counts_main_heading(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="80" xMax="180" yMin="10" yMax="20">1、合并资产负债表</word></line>
<line yMin="20"><word xMin="80" xMax="180" yMin="20" yMax="30">1、合并资产负债表（续）</word></line>
<line yMin="30"><word xMin="80" xMax="180" yMin="30" yMax="40">2、母公司利润表</word></line>
</block></flow></page></doc></body></html>"""
        self.assertEqual(count_statement_headings(xhtml), 2)

    def test_cross_flow_rows_with_small_vertical_offset_and_split_date_headers(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="250" xMax="350" yMin="10" yMax="20">合并资产负债表</word></line>
<line yMin="20"><word xMin="90" xMax="180" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30">
  <word xMin="171" xMax="192" yMin="30" yMax="40">项目</word>
  <word xMin="315" xMax="336" yMin="30" yMax="40">2025</word>
  <word xMin="339" xMax="349" yMin="30" yMax="40">年</word>
  <word xMin="352" xMax="357" yMin="30" yMax="40">3</word>
  <word xMin="360" xMax="370" yMin="30" yMax="40">月</word>
  <word xMin="373" xMax="383" yMin="30" yMax="40">31</word>
  <word xMin="386" xMax="396" yMin="30" yMax="40">日</word>
  <word xMin="428" xMax="449" yMin="30" yMax="40">2024</word>
  <word xMin="452" xMax="462" yMin="30" yMax="40">年</word>
  <word xMin="465" xMax="475" yMin="30" yMax="40">12</word>
  <word xMin="478" xMax="489" yMin="30" yMax="40">月</word>
  <word xMin="491" xMax="502" yMin="30" yMax="40">31</word>
  <word xMin="504" xMax="515" yMin="30" yMax="40">日</word>
</line>
<line yMin="50"><word xMin="80" xMax="123" yMin="50" yMax="60">货币资金</word></line>
</block></flow>
<flow><block>
<line yMin="48.4"><word xMin="335" xMax="408" yMin="48.4" yMax="58.4">100.00</word></line>
<line yMin="48.4"><word xMin="450" xMax="524" yMin="48.4" yMax="58.4">80.00</word></line>
</block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-cross-flow-date",
            "document_version_id": "version-cross-flow-date",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2025-03-31",
            "report_type": "q1",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        funds = [fact for fact in facts if fact["metric_id"] == "monetary_funds"]

        self.assertEqual(len(funds), 2)
        self.assertEqual([fact["value_decimal"] for fact in funds], ["100.00", "80.00"])
        self.assertEqual([fact["column_role"] for fact in funds], ["current", "comparative"])
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in funds],
            [
                ("2025-03-31", "2025-03-31"),
                ("2024-12-31", "2024-12-31"),
            ],
        )

    def test_combined_and_period_specific_statement_headings_are_supported(self) -> None:
        self.assertEqual(
            _parse_statement_heading("1、合并及公司资产负债表（未经审计）"),
            ("balance_sheet", "unknown"),
        )
        self.assertEqual(
            _parse_statement_heading("合并及银行利润表"),
            ("income_statement", "unknown"),
        )
        self.assertEqual(
            _parse_statement_heading("合并本报告期利润表"),
            ("income_statement", "consolidated"),
        )
        self.assertEqual(
            _parse_statement_heading("母公司年初到报告期末现金流量表"),
            ("cash_flow", "parent_only"),
        )
        self.assertEqual(
            detect_period_basis("合并本报告期利润表", "income_statement", "q3"),
            "standalone_quarter",
        )
        self.assertEqual(
            detect_period_basis("合并年初到报告期末利润表", "income_statement", "q3"),
            "ytd",
        )

    def test_date_prefixed_and_dual_scope_statement_headings_are_supported(self) -> None:
        self.assertEqual(
            _parse_statement_heading("2015年12月31日合并及母公司资产负债表"),
            ("balance_sheet", "unknown"),
        )
        self.assertEqual(
            _parse_statement_heading("2019年1月1日至6月30日止期间合并及母公司利润表"),
            ("income_statement", "unknown"),
        )
        self.assertEqual(
            _parse_statement_heading("2019年1月1日至6月30日止期间合并及母公司现金流量表"),
            ("cash_flow", "unknown"),
        )
        self.assertEqual(
            _parse_statement_heading("2015年度合并及母公司利润表"),
            ("income_statement", "unknown"),
        )
        self.assertEqual(
            _parse_statement_heading("2020年1月1日至6月30日止半年度合并及银行现金流量表"),
            ("cash_flow", "unknown"),
        )
        self.assertEqual(
            _parse_statement_heading("合并资产负债表和资产负债表"),
            ("balance_sheet", "unknown"),
        )
        self.assertEqual(
            _parse_statement_heading("合并利润表和利润表"),
            ("income_statement", "unknown"),
        )
        self.assertIsNone(
            _parse_statement_heading("2015年12月31日资产负债表日后事项")
        )
        # TOC entries commonly append page numbers; do not mistake them for
        # the start of a financial statement section.
        self.assertIsNone(_parse_statement_heading("合并及公司资产负债表1"))
        self.assertIsNone(_parse_statement_heading("合并资产负债表和利润表"))

    def test_date_prefixed_and_plain_duplicate_heading_count_as_one_table(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="380" yMin="10" yMax="20">2024年12月31日合并资产负债表</word></line>
<line yMin="20"><word xMin="90" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30"><word xMin="240" xMax="380" yMin="30" yMax="40">合并资产负债表</word></line>
<line yMin="40"><word xMin="350" xMax="400" yMin="40" yMax="50">期末余额</word><word xMin="460" xMax="510" yMin="40" yMax="50">期初余额</word></line>
<line yMin="50"><word xMin="100" xMax="180" yMin="50" yMax="60">资产总计</word></line>
</block></flow>
<flow><block><line yMin="50"><word xMin="340" xMax="400" yMin="50" yMax="60">1000</word><word xMin="450" xMax="510" yMin="50" yMax="60">900</word></line></block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-duplicate-date-heading",
            "document_version_id": "version-duplicate-date-heading",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2024-12-31",
            "report_type": "annual",
        }

        self.assertEqual(count_statement_headings(xhtml), 1)
        facts = parse_bbox_xhtml(xhtml, document)
        assets = [fact for fact in facts if fact["metric_id"] == "total_assets"]
        self.assertEqual(len(assets), 2)
        self.assertEqual([fact["table_index"] for fact in assets], [1, 1])

    def test_multiline_date_and_group_scope_headers_map_four_columns(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="380" yMin="10" yMax="20">合并及公司资产负债表</word></line>
<line yMin="20"><word xMin="80" xMax="150" yMin="20" yMax="30">单位：千元</word></line>
<line yMin="30">
  <word xMin="250" xMax="300" yMin="30" yMax="40">本集团</word>
  <word xMin="425" xMax="475" yMin="30" yMax="40">本行</word>
</line>
<line yMin="40">
  <word xMin="210" xMax="250" yMin="40" yMax="50">2025年</word>
  <word xMin="300" xMax="340" yMin="40" yMax="50">2024年</word>
  <word xMin="390" xMax="430" yMin="40" yMax="50">2025年</word>
  <word xMin="480" xMax="520" yMin="40" yMax="50">2024年</word>
</line>
<line yMin="50">
  <word xMin="210" xMax="250" yMin="50" yMax="60">9月30日</word>
  <word xMin="300" xMax="340" yMin="50" yMax="60">12月31日</word>
  <word xMin="390" xMax="430" yMin="50" yMax="60">9月30日</word>
  <word xMin="480" xMax="520" yMin="50" yMax="60">12月31日</word>
</line>
<line yMin="70"><word xMin="80" xMax="123" yMin="70" yMax="80">货币资金</word></line>
</block></flow>
<flow><block>
<line yMin="68.4"><word xMin="200" xMax="260" yMin="68.4" yMax="78.4">100</word></line>
<line yMin="68.4"><word xMin="290" xMax="350" yMin="68.4" yMax="78.4">90</word></line>
<line yMin="68.4"><word xMin="380" xMax="440" yMin="68.4" yMax="78.4">80</word></line>
<line yMin="68.4"><word xMin="470" xMax="530" yMin="68.4" yMax="78.4">70</word></line>
</block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-multiline-scope",
            "document_version_id": "version-multiline-scope",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2025-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        funds = [fact for fact in facts if fact["metric_id"] == "monetary_funds"]

        self.assertEqual(len(funds), 4)
        self.assertEqual([fact["value_decimal"] for fact in funds], ["100000", "90000", "80000", "70000"])
        self.assertEqual(
            [fact["statement_scope"] for fact in funds],
            ["consolidated", "consolidated", "parent_only", "parent_only"],
        )
        self.assertEqual(
            [fact["column_role"] for fact in funds],
            ["current", "comparative", "current", "comparative"],
        )
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in funds],
            [
                ("2025-09-30", "2025-09-30"),
                ("2024-12-31", "2024-12-31"),
                ("2025-09-30", "2025-09-30"),
                ("2024-12-31", "2024-12-31"),
            ],
        )

    def test_issuer_name_pair_maps_combined_and_parent_columns_fail_closed(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="430" yMin="10" yMax="20">2015年12月31日合并及母公司资产负债表</word></line>
<line yMin="30">
  <word xMin="250" xMax="310" yMin="30" yMax="40">中国银行集团</word>
  <word xMin="425" xMax="475" yMin="30" yMax="40">中国银行</word>
</line>
<line yMin="40">
  <word xMin="210" xMax="250" yMin="40" yMax="50">2025年12月31日</word>
  <word xMin="300" xMax="340" yMin="40" yMax="50">2024年12月31日</word>
  <word xMin="390" xMax="430" yMin="40" yMax="50">2025年12月31日</word>
  <word xMin="480" xMax="520" yMin="40" yMax="50">2024年12月31日</word>
</line>
<line yMin="60">
  <word xMin="80" xMax="150" yMin="60" yMax="70">资产总计</word>
  <word xMin="210" xMax="250" yMin="60" yMax="70">1000</word>
  <word xMin="300" xMax="340" yMin="60" yMax="70">900</word>
  <word xMin="390" xMax="430" yMin="60" yMax="70">800</word>
  <word xMin="480" xMax="520" yMin="60" yMax="70">700</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-issuer-scope-pair",
            "document_version_id": "version-issuer-scope-pair",
            "canonical_security_id": "601988",
            "identity_status": "adjudicated",
            "report_period_candidate": "2025-12-31",
            "report_type": "annual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        assets = [fact for fact in facts if fact["metric_id"] == "total_assets"]
        self.assertEqual(len(assets), 4)
        self.assertEqual([fact["statement_scope"] for fact in assets], [
            "consolidated", "consolidated", "parent_only", "parent_only"
        ])
        self.assertEqual([fact["column_role"] for fact in assets], [
            "current", "comparative", "current", "comparative"
        ])

        mismatched = xhtml.replace(">中国银行</word>", ">招商银行</word>")
        mismatched_facts = parse_bbox_xhtml(mismatched, document)
        mismatched_assets = [fact for fact in mismatched_facts if fact["metric_id"] == "total_assets"]
        self.assertEqual([fact["statement_scope"] for fact in mismatched_assets], ["unknown"] * 4)

    def test_multiline_year_and_month_range_headers_resolve_q3_ytd(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="380" yMin="10" yMax="20">合并及公司利润表</word></line>
<line yMin="20"><word xMin="80" xMax="150" yMin="20" yMax="30">单位：千元</word></line>
<line yMin="30">
  <word xMin="250" xMax="300" yMin="30" yMax="40">本集团</word>
  <word xMin="425" xMax="475" yMin="30" yMax="40">本行</word>
</line>
<line yMin="40">
  <word xMin="210" xMax="250" yMin="40" yMax="50">2025年度</word>
  <word xMin="300" xMax="340" yMin="40" yMax="50">2024年度</word>
  <word xMin="390" xMax="430" yMin="40" yMax="50">2025年度</word>
  <word xMin="480" xMax="520" yMin="40" yMax="50">2024年度</word>
</line>
<line yMin="50">
  <word xMin="210" xMax="250" yMin="50" yMax="60">1-9月</word>
  <word xMin="300" xMax="340" yMin="50" yMax="60">1-9月</word>
  <word xMin="390" xMax="430" yMin="50" yMax="60">1-9月</word>
  <word xMin="480" xMax="520" yMin="50" yMax="60">1-9月</word>
</line>
<line yMin="70"><word xMin="80" xMax="123" yMin="70" yMax="80">营业收入</word></line>
</block></flow>
<flow><block>
<line yMin="68.4"><word xMin="200" xMax="260" yMin="68.4" yMax="78.4">100</word></line>
<line yMin="68.4"><word xMin="290" xMax="350" yMin="68.4" yMax="78.4">90</word></line>
<line yMin="68.4"><word xMin="380" xMax="440" yMin="68.4" yMax="78.4">80</word></line>
<line yMin="68.4"><word xMin="470" xMax="530" yMin="68.4" yMax="78.4">70</word></line>
</block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-q3-ytd",
            "document_version_id": "version-q3-ytd",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2025-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]

        self.assertEqual(len(revenue), 4)
        self.assertEqual(
            [fact["statement_scope"] for fact in revenue],
            ["consolidated", "consolidated", "parent_only", "parent_only"],
        )
        self.assertEqual(
            [fact["column_role"] for fact in revenue],
            ["current", "comparative", "current", "comparative"],
        )
        self.assertEqual([fact["period_basis"] for fact in revenue], ["ytd"] * 4)
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in revenue],
            [
                ("2025-01-01", "2025-09-30"),
                ("2024-01-01", "2024-09-30"),
                ("2025-01-01", "2025-09-30"),
                ("2024-01-01", "2024-09-30"),
            ],
        )

    def test_q3_first_three_quarters_labels_are_ytd_columns(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并利润表</word></line>
<line yMin="20"><word xMin="80" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30">
  <word xMin="250" xMax="330" yMin="30" yMax="40">2026年前三季度</word>
  <word xMin="400" xMax="480" yMin="30" yMax="40">2025年前三季度</word>
</line>
<line yMin="50">
  <word xMin="80" xMax="140" yMin="50" yMax="60">营业收入</word>
  <word xMin="250" xMax="330" yMin="50" yMax="60">1000</word>
  <word xMin="400" xMax="480" yMin="50" yMax="60">900</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-q3-first-three",
            "document_version_id": "version-q3-first-three",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2026-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]

        self.assertEqual(len(revenue), 2)
        self.assertEqual(
            [fact["column_role"] for fact in revenue],
            ["current", "comparative"],
        )
        self.assertEqual([fact["period_basis"] for fact in revenue], ["ytd", "ytd"])
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in revenue],
            [
                ("2026-01-01", "2026-09-30"),
                ("2025-01-01", "2025-09-30"),
            ],
        )

    def test_period_context_survives_long_statement_body_before_metric(self) -> None:
        filler = "".join(
            f'<line yMin="{60 + index * 12}"><word xMin="80" xMax="180" yMin="{60 + index * 12}" yMax="{70 + index * 12}">其他项目说明{index}</word></line>'
            for index in range(10)
        )
        xhtml = f"""<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并利润表</word></line>
<line yMin="20"><word xMin="80" xMax="250" yMin="20" yMax="30">截至2025年9月30日止九个月期间</word></line>
<line yMin="35"><word xMin="80" xMax="150" yMin="35" yMax="45">单位：元</word></line>
<line yMin="45">
  <word xMin="250" xMax="300" yMin="45" yMax="55">2025年</word>
  <word xMin="400" xMax="450" yMin="45" yMax="55">2024年</word>
</line>
{filler}
<line yMin="190">
  <word xMin="80" xMax="140" yMin="190" yMax="200">营业收入</word>
  <word xMin="250" xMax="300" yMin="190" yMax="200">100</word>
  <word xMin="400" xMax="450" yMin="190" yMax="200">90</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-period-context",
            "document_version_id": "version-period-context",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2025-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]

        self.assertEqual(len(revenue), 2)
        self.assertEqual([fact["column_role"] for fact in revenue], ["current", "comparative"])
        self.assertEqual([fact["period_basis"] for fact in revenue], ["ytd", "ytd"])
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in revenue],
            [
                ("2025-01-01", "2025-09-30"),
                ("2024-01-01", "2024-09-30"),
            ],
        )

    def test_q1_chinese_quarter_headers_map_current_and_comparative(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并利润表</word></line>
<line yMin="20"><word xMin="80" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="25"><word xMin="250" xMax="330" yMin="25" yMax="35">2025年1—3月</word></line>
<line yMin="40">
  <word xMin="315" xMax="400" yMin="40" yMax="50">2025年第一季度</word>
  <word xMin="435" xMax="525" yMin="40" yMax="50">2024年第一季度</word>
</line>
<line yMin="60">
  <word xMin="80" xMax="140" yMin="60" yMax="70">营业收入</word>
  <word xMin="396" xMax="417" yMin="60" yMax="70">100</word>
  <word xMin="516" xMax="540" yMin="60" yMax="70">90</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-q1-quarter-label",
            "document_version_id": "version-q1-quarter-label",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2025-03-31",
            "report_type": "q1",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]

        self.assertEqual(len(revenue), 2)
        self.assertEqual(
            [fact["column_role"] for fact in revenue],
            ["current", "comparative"],
        )
        self.assertEqual(
            [fact["period_basis"] for fact in revenue],
            ["standalone_quarter", "standalone_quarter"],
        )
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in revenue],
            [
                ("2025-01-01", "2025-03-31"),
                ("2024-01-01", "2024-03-31"),
            ],
        )

    def test_semiannual_chinese_headers_map_current_and_comparative_ytd(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="360" yMin="10" yMax="20">合并现金流量表</word></line>
<line yMin="20"><word xMin="80" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30">
  <word xMin="240" xMax="330" yMin="30" yMax="40">2025年半年度</word>
  <word xMin="400" xMax="490" yMin="30" yMax="40">2024年半年度</word>
</line>
<line yMin="50">
  <word xMin="80" xMax="190" yMin="50" yMax="60">经营活动产生的现金流量净额</word>
  <word xMin="240" xMax="330" yMin="50" yMax="60">100</word>
  <word xMin="400" xMax="490" yMin="50" yMax="60">90</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-h1-half-year-label",
            "document_version_id": "version-h1-half-year-label",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2025-06-30",
            "report_type": "semiannual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        cash_flow = [fact for fact in facts if fact["metric_id"] == "operating_cash_flow"]

        self.assertEqual(len(cash_flow), 2)
        self.assertEqual(
            [fact["column_role"] for fact in cash_flow],
            ["current", "comparative"],
        )
        self.assertEqual([fact["period_basis"] for fact in cash_flow], ["ytd", "ytd"])
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in cash_flow],
            [
                ("2025-01-01", "2025-06-30"),
                ("2024-01-01", "2024-06-30"),
            ],
        )

    def test_interim_balance_sheet_opening_date_and_wide_numeric_alignment(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="220" xMax="360" yMin="10" yMax="20">合并资产负债表</word></line>
<line yMin="20"><word xMin="80" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30">
  <word xMin="250" xMax="292" yMin="30" yMax="40">2022年06月30日</word>
  <word xMin="438" xMax="480" yMin="30" yMax="40">2022年01月01日</word>
</line>
<line yMin="50"><word xMin="80" xMax="130" yMin="50" yMax="60">货币资金</word></line>
</block></flow>
<flow><block>
<line yMin="48.4"><word xMin="305" xMax="372" yMin="48.4" yMax="58.4">100</word></line>
<line yMin="48.4"><word xMin="465" xMax="533" yMin="48.4" yMax="58.4">90</word></line>
</block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-interim-opening",
            "document_version_id": "version-interim-opening",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2022-06-30",
            "report_type": "semiannual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        funds = [fact for fact in facts if fact["metric_id"] == "monetary_funds"]

        self.assertEqual(len(funds), 2)
        self.assertEqual([fact["column_role"] for fact in funds], ["current", "comparative"])
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in funds],
            [
                ("2022-06-30", "2022-06-30"),
                ("2022-01-01", "2022-01-01"),
            ],
        )

    def test_multiline_metric_labels_attach_to_following_numeric_line(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并利润表</word></line>
<line yMin="20"><word xMin="80" xMax="220" yMin="20" yMax="30">截至2025年9月30日止九个月期间</word></line>
<line yMin="30"><word xMin="80" xMax="150" yMin="30" yMax="40">单位：元</word></line>
<line yMin="40">
  <word xMin="250" xMax="330" yMin="40" yMax="50">本期发生额</word>
  <word xMin="400" xMax="480" yMin="40" yMax="50">上期发生额</word>
</line>
<line yMin="55"><word xMin="80" xMax="180" yMin="55" yMax="65">三、营业利润（亏损以“－”号填</word></line>
<line yMin="61">
  <word xMin="250" xMax="330" yMin="61" yMax="71">100</word>
  <word xMin="400" xMax="480" yMin="61" yMax="71">90</word>
</line>
<line yMin="75"><word xMin="80" xMax="180" yMin="75" yMax="85">四、利润总额（亏损总额以“－”号</word></line>
<line yMin="81">
  <word xMin="250" xMax="330" yMin="81" yMax="91">80</word>
  <word xMin="400" xMax="480" yMin="81" yMax="91">70</word>
</line>
<line yMin="95"><word xMin="80" xMax="180" yMin="95" yMax="105">五、净利润（净亏损以“－”号填</word></line>
<line yMin="101">
  <word xMin="250" xMax="330" yMin="101" yMax="111">60</word>
  <word xMin="400" xMax="480" yMin="101" yMax="111">50</word>
</line>
<line yMin="115"><word xMin="80" xMax="180" yMin="115" yMax="125">1.归属于母公司股东的净利润</word></line>
<line yMin="121">
  <word xMin="250" xMax="330" yMin="121" yMax="131">59</word>
  <word xMin="400" xMax="480" yMin="121" yMax="131">49</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-multiline-metric-labels",
            "document_version_id": "version-multiline-metric-labels",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2025-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        expected = {
            "operating_profit": ["100", "90"],
            "total_profit": ["80", "70"],
            "net_profit": ["60", "50"],
            "parent_net_profit": ["59", "49"],
        }
        for metric_id, expected_values in expected.items():
            metric_facts = [
                fact for fact in facts if fact["metric_id"] == metric_id
            ]
            self.assertEqual(
                [fact["value_raw"] for fact in metric_facts],
                expected_values,
                metric_id,
            )
            self.assertEqual(
                [fact["column_role"] for fact in metric_facts],
                ["current", "comparative"],
                metric_id,
            )
            self.assertEqual(
                [fact["period_basis"] for fact in metric_facts],
                ["ytd", "ytd"],
                metric_id,
            )
            expected_label = {
                "operating_profit": "营业利润",
                "total_profit": "利润总额",
                "net_profit": "净利润",
                "parent_net_profit": "归属于母公司股东的净利润",
            }[metric_id]
            self.assertTrue(
                all(expected_label in fact["source_cell_text"] for fact in metric_facts),
                metric_id,
            )

    def test_metric_label_wrapped_around_numeric_line_is_reconstructed(self) -> None:
        import pandas as pd

        dictionary = pd.read_csv(
            ROOT / "data" / "metadata" / "financial_report_metric_dictionary.csv",
            dtype=str,
        ).fillna("")
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并现金流量表</word></line>
<line yMin="30">
  <word xMin="346" xMax="420" yMin="30" yMax="40">2026年1—6月</word>
  <word xMin="452" xMax="526" yMin="30" yMax="40">2025年1—6月</word>
</line>
<line yMin="45"><word xMin="421" xMax="531" yMin="45" yMax="55">单位：元</word></line>
<line yMin="60"><word xMin="95" xMax="243" yMin="60" yMax="70">一、经营活动产生的现金流量：</word></line>
<line yMin="100"><word xMin="127" xMax="253" yMin="100" yMax="110">经营活动产生的现金流</word></line>
<line yMin="107.5">
  <word xMin="351" xMax="435" yMin="107.5" yMax="121.2">-240,725,641.43</word>
  <word xMin="456" xMax="526" yMin="107.5" yMax="121.2">333,455,525.42</word>
</line>
<line yMin="118"><word xMin="95.5" xMax="127" yMin="118" yMax="128">量净额</word></line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-label-around-values",
            "document_version_id": "version-label-around-values",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2026-06-30",
            "report_type": "semiannual",
        }

        facts = parse_bbox_xhtml(xhtml, document, dictionary)
        operating_cash_flow = [
            fact for fact in facts if fact["metric_id"] == "operating_cash_flow"
        ]

        self.assertEqual(
            [fact["value_raw"] for fact in operating_cash_flow],
            ["-240,725,641.43", "333,455,525.42"],
        )
        self.assertEqual(
            [fact["column_role"] for fact in operating_cash_flow],
            ["current", "comparative"],
        )
        self.assertEqual(
            [fact["statement_scope"] for fact in operating_cash_flow],
            ["consolidated", "consolidated"],
        )
        self.assertEqual(
            [fact["period_basis"] for fact in operating_cash_flow],
            ["ytd", "ytd"],
        )
        self.assertEqual(
            [
                (fact["fact_period_start"], fact["fact_period_end"])
                for fact in operating_cash_flow
            ],
            [
                ("2026-01-01", "2026-06-30"),
                ("2025-01-01", "2025-06-30"),
            ],
        )
        self.assertTrue(
            all(
                "经营活动产生的现金流量净额" in fact["source_cell_text"]
                for fact in operating_cash_flow
            )
        )
        self.assertTrue(
            all(fact["validation_status"] == "quarantined" for fact in operating_cash_flow)
        )
        self.assertTrue(
            all(
                "gold_set_not_manually_verified" in fact["quarantine_reason"]
                for fact in operating_cash_flow
            )
        )

        # A nearby but unrelated suffix must not complete a metric alias.
        negative_xhtml = xhtml.replace("量净额", "小计")
        negative_facts = parse_bbox_xhtml(negative_xhtml, document, dictionary)
        self.assertFalse(
            any(fact["metric_id"] == "operating_cash_flow" for fact in negative_facts)
        )

        # A suffix line that also carries an amount is not a safe label fragment.
        suffix_with_amount_xhtml = xhtml.replace(
            '<line yMin="118"><word xMin="95.5" xMax="127" yMin="118" yMax="128">量净额</word></line>',
            '<line yMin="118"><word xMin="95.5" xMax="127" yMin="118" yMax="128">量净额</word><word xMin="351" xMax="400" yMin="118" yMax="128">7</word></line>',
        )
        suffix_with_amount_facts = parse_bbox_xhtml(
            suffix_with_amount_xhtml, document, dictionary
        )
        self.assertFalse(
            any(
                fact["metric_id"] == "operating_cash_flow"
                for fact in suffix_with_amount_facts
            )
        )

        # A note-column reference between the label fragments and values is not
        # part of the metric name and must not prevent an exact reconstruction.
        note_column_xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并现金流量表</word></line>
<line yMin="30">
  <word xMin="248" xMax="280" yMin="30" yMax="40">附注</word>
  <word xMin="346" xMax="420" yMin="30" yMax="40">2026年1—6月</word>
  <word xMin="452" xMax="526" yMin="30" yMax="40">2025年1—6月</word>
</line>
<line yMin="45"><word xMin="421" xMax="531" yMin="45" yMax="55">单位：元</word></line>
<line yMin="60"><word xMin="95" xMax="243" yMin="60" yMax="70">一、经营活动产生的现金流量：</word></line>
<line yMin="100"><word xMin="127" xMax="253" yMin="100" yMax="110">经营活动产生的现金流</word></line>
<line yMin="107.5">
  <word xMin="248" xMax="280" yMin="107.5" yMax="121.2">七、78</word>
  <word xMin="351" xMax="435" yMin="107.5" yMax="121.2">-240,725,641.43</word>
  <word xMin="456" xMax="526" yMin="107.5" yMax="121.2">333,455,525.42</word>
</line>
<line yMin="118"><word xMin="95.5" xMax="127" yMin="118" yMax="128">量净额</word></line>
</block></flow></page></doc></body></html>"""
        note_column_facts = parse_bbox_xhtml(
            note_column_xhtml, document, dictionary
        )
        note_column_ocf = [
            fact for fact in note_column_facts
            if fact["metric_id"] == "operating_cash_flow"
        ]
        self.assertEqual(
            [fact["value_raw"] for fact in note_column_ocf],
            ["-240,725,641.43", "333,455,525.42"],
        )

        # A note-reference-only row may separate the numeric row from its
        # final label character; the note number must not enter the label.
        note_row_split_xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并现金流量表</word></line>
<line yMin="30">
  <word xMin="248" xMax="280" yMin="30" yMax="40">附注</word>
  <word xMin="346" xMax="420" yMin="30" yMax="40">2026年1—6月</word>
  <word xMin="452" xMax="526" yMin="30" yMax="40">2025年1—6月</word>
</line>
<line yMin="45"><word xMin="421" xMax="531" yMin="45" yMax="55">单位：元</word></line>
<line yMin="60"><word xMin="95" xMax="243" yMin="60" yMax="70">一、经营活动产生的现金流量：</word></line>
<line yMin="100">
  <word xMin="127" xMax="253" yMin="100" yMax="110">经营活动产生的现金流量净</word>
  <word xMin="351" xMax="435" yMin="100" yMax="110">-240,725,641.43</word>
  <word xMin="456" xMax="526" yMin="100" yMax="110">333,455,525.42</word>
</line>
<line yMin="107.5"><word xMin="248" xMax="280" yMin="107.5" yMax="117.5">七、79</word></line>
<line yMin="118"><word xMin="95.5" xMax="127" yMin="118" yMax="128">额</word></line>
</block></flow></page></doc></body></html>"""
        note_row_split_facts = parse_bbox_xhtml(
            note_row_split_xhtml, document, dictionary
        )
        note_row_split_ocf = [
            fact for fact in note_row_split_facts
            if fact["metric_id"] == "operating_cash_flow"
        ]
        self.assertEqual(
            [fact["value_raw"] for fact in note_row_split_ocf],
            ["-240,725,641.43", "333,455,525.42"],
        )
        self.assertTrue(
            all(
                "经营活动产生的现金流量净额" in fact["source_cell_text"]
                for fact in note_row_split_ocf
            )
        )

        # A non-note label between the numeric row and suffix blocks the join.
        unsafe_note_row_xhtml = note_row_split_xhtml.replace(
            '<line yMin="107.5"><word xMin="248" xMax="280" yMin="107.5" yMax="117.5">七、79</word></line>',
            '<line yMin="107.5"><word xMin="248" xMax="280" yMin="107.5" yMax="117.5">七、79</word>'
            '<word xMin="95.5" xMax="127" yMin="107.5" yMax="117.5">其他项目</word></line>',
        )
        unsafe_note_row_facts = parse_bbox_xhtml(
            unsafe_note_row_xhtml, document, dictionary
        )
        self.assertFalse(
            any(
                fact["metric_id"] == "operating_cash_flow"
                for fact in unsafe_note_row_facts
            )
        )

    def test_bbox_layout_joins_separate_flows_and_maps_columns(self) -> None:
        xhtml = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<body><doc><page width="595" height="842">
  <flow><block>
    <line xMin="280" xMax="350" yMin="10" yMax="20">
      <word xMin="280" yMin="10" xMax="350" yMax="20">合并利润表</word>
    </line>
    <line xMin="90" xMax="180" yMin="15" yMax="25">
      <word xMin="90" yMin="15" xMax="180" yMax="25">单位：万元</word>
    </line>
    <line xMin="100" xMax="510" yMin="30" yMax="40">
      <word xMin="100" yMin="30" xMax="120" yMax="40">项目</word>
      <word xMin="360" yMin="30" xMax="410" yMax="40">本期发生额</word>
      <word xMin="460" yMin="30" xMax="510" yMax="40">上期发生额</word>
    </line>
    <line xMin="100" xMax="180" yMin="50" yMax="60">
      <word xMin="100" yMin="50" xMax="180" yMax="60">营业收入</word>
    </line>
  </block></flow>
  <flow><block>
    <line xMin="350" xMax="540" yMin="50" yMax="60">
      <word xMin="350" yMin="50" xMax="400" yMax="60">100.00</word>
      <word xMin="450" yMin="50" xMax="500" yMax="60">80.00</word>
      <word xMin="510" yMin="50" xMax="540" yMax="60">25.00%</word>
    </line>
  </block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-1",
            "document_version_id": "version-1",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2024-12-31",
            "report_type": "annual",
            "extractor_version": "25.07.0",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]

        self.assertEqual(len(revenue), 2)
        self.assertEqual(revenue[0]["statement_scope"], "consolidated")
        self.assertEqual(revenue[0]["table_index"], 1)
        self.assertEqual(revenue[0]["column_role"], "current")
        self.assertEqual(revenue[1]["column_role"], "comparative")
        self.assertEqual(revenue[0]["column_label"], "本期发生额")
        self.assertEqual(revenue[1]["column_label"], "上期发生额")
        self.assertEqual(revenue[0]["unit"], "万元")
        self.assertEqual(revenue[0]["value_decimal"], "1000000.00")
        self.assertEqual(revenue[1]["value_decimal"], "800000.00")
        self.assertEqual(revenue[0]["fact_period_start"], "2024-01-01")
        self.assertEqual(revenue[0]["fact_period_end"], "2024-12-31")
        self.assertEqual(revenue[1]["fact_period_start"], "2023-01-01")
        self.assertEqual(revenue[1]["fact_period_end"], "2023-12-31")
        self.assertNotIn("column_role_unknown", revenue[0]["quarantine_reason"])
        self.assertIn("gold_set_not_manually_verified", revenue[0]["quarantine_reason"])

    def test_bbox_parser_distinguishes_two_statement_scopes_on_one_page(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="280" xMax="350" yMin="10" yMax="20">合并利润表</word></line>
<line yMin="20"><word xMin="90" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30"><word xMin="360" xMax="410" yMin="30" yMax="40">本期发生额</word><word xMin="460" xMax="510" yMin="30" yMax="40">上期发生额</word></line>
<line yMin="40"><word xMin="100" xMax="180" yMin="40" yMax="50">营业收入</word></line>
<line yMin="60"><word xMin="270" xMax="360" yMin="60" yMax="70">母公司利润表</word></line>
<line yMin="70"><word xMin="360" xMax="410" yMin="70" yMax="80">本期发生额</word><word xMin="460" xMax="510" yMin="70" yMax="80">上期发生额</word></line>
<line yMin="80"><word xMin="100" xMax="180" yMin="80" yMax="90">营业收入</word></line>
</block></flow>
<flow><block>
<line yMin="40"><word xMin="350" xMax="400" yMin="40" yMax="50">100</word><word xMin="450" xMax="500" yMin="40" yMax="50">80</word></line>
<line yMin="80"><word xMin="350" xMax="400" yMin="80" yMax="90">50</word><word xMin="450" xMax="500" yMin="80" yMax="90">40</word></line>
</block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-2",
            "document_version_id": "version-2",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2024-12-31",
            "report_type": "annual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]

        self.assertEqual(len(revenue), 4)
        self.assertEqual({fact["table_index"] for fact in revenue}, {1, 2})
        consolidated = [fact for fact in revenue if fact["table_index"] == 1]
        parent = [fact for fact in revenue if fact["table_index"] == 2]
        self.assertTrue(all(fact["statement_scope"] == "consolidated" for fact in consolidated))
        self.assertTrue(all(fact["statement_scope"] == "parent_only" for fact in parent))
        self.assertEqual(parent[0]["value_decimal"], "50")
        self.assertEqual(parent[1]["value_decimal"], "40")

    def test_total_and_detailed_revenue_are_separate_and_statement_type_is_enforced(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="280" xMax="350" yMin="10" yMax="20">合并利润表</word></line>
<line yMin="20"><word xMin="90" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30"><word xMin="360" xMax="410" yMin="30" yMax="40">本期发生额</word><word xMin="460" xMax="510" yMin="30" yMax="40">上期发生额</word></line>
<line yMin="40"><word xMin="90" xMax="190" yMin="40" yMax="50">一、营业总收入</word></line>
<line yMin="50"><word xMin="90" xMax="190" yMin="50" yMax="60">其中：营业收入</word></line>
<line yMin="60"><word xMin="90" xMax="190" yMin="60" yMax="70">二、营业总成本</word></line>
<line yMin="70"><word xMin="90" xMax="190" yMin="70" yMax="80">其中：营业成本</word></line>
<line yMin="80"><word xMin="90" xMax="190" yMin="80" yMax="90">资产合计</word></line>
</block></flow>
<flow><block>
<line yMin="40"><word xMin="350" xMax="400" yMin="40" yMax="50">1000</word><word xMin="450" xMax="500" yMin="40" yMax="50">900</word></line>
<line yMin="50"><word xMin="350" xMax="400" yMin="50" yMax="60">800</word><word xMin="450" xMax="500" yMin="50" yMax="60">700</word></line>
<line yMin="60"><word xMin="350" xMax="400" yMin="60" yMax="70">600</word><word xMin="450" xMax="500" yMin="60" yMax="70">500</word></line>
<line yMin="70"><word xMin="350" xMax="400" yMin="70" yMax="80">400</word><word xMin="450" xMax="500" yMin="70" yMax="80">300</word></line>
<line yMin="80"><word xMin="350" xMax="400" yMin="80" yMax="90">200</word><word xMin="450" xMax="500" yMin="80" yMax="90">100</word></line>
</block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-4",
            "document_version_id": "version-4",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2024-12-31",
            "report_type": "annual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        by_metric = {}
        for fact in facts:
            by_metric.setdefault(fact["metric_id"], []).append(fact)

        self.assertEqual(len(by_metric["total_operating_revenue"]), 2)
        self.assertEqual(len(by_metric["revenue"]), 2)
        self.assertEqual(len(by_metric["total_operating_cost"]), 2)
        self.assertEqual(len(by_metric["operating_cost"]), 2)
        self.assertNotIn("total_assets", by_metric)
        self.assertEqual(
            [fact["value_decimal"] for fact in by_metric["total_operating_revenue"]],
            ["1000", "900"],
        )
        self.assertEqual(
            [fact["value_decimal"] for fact in by_metric["revenue"]],
            ["800", "700"],
        )

    def test_note_reference_is_excluded_and_year_opening_header_is_mapped(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="260" xMax="370" yMin="10" yMax="20">合并资产负债表</word></line>
<line yMin="20"><word xMin="90" xMax="210" yMin="20" yMax="30">单位：（人民币）元</word></line>
<line yMin="30">
  <word xMin="100" xMax="120" yMin="30" yMax="40">项目</word>
  <word xMin="330" xMax="360" yMin="30" yMax="40">附注</word>
  <word xMin="390" xMax="440" yMin="30" yMax="40">期末余额</word>
  <word xMin="470" xMax="520" yMin="30" yMax="40">年初余额</word>
</line>
<line yMin="40">
  <word xMin="100" xMax="180" yMin="40" yMax="50">货币资金</word>
  <word xMin="330" xMax="365" yMin="40" yMax="50">十七、4</word>
  <word xMin="380" xMax="425" yMin="40" yMax="50">1000</word>
  <word xMin="460" xMax="505" yMin="40" yMax="50">900</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-note",
            "document_version_id": "version-note",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2024-12-31",
            "report_type": "annual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        assets = [fact for fact in facts if fact["metric_id"] == "monetary_funds"]

        self.assertEqual(len(assets), 2)
        self.assertEqual([fact["value_raw"] for fact in assets], ["1000", "900"])
        self.assertEqual([fact["column_role"] for fact in assets], ["current", "comparative"])
        self.assertEqual([fact["column_label"] for fact in assets], ["期末余额", "年初余额"])
        self.assertEqual([fact["unit"] for fact in assets], ["元", "元"])
        self.assertNotIn("value_or_unit_not_parseable", assets[0]["quarantine_reason"])

    def test_numbered_heading_and_four_column_q3_periods_are_mapped(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="200" xMax="330" yMin="10" yMax="20">3、合并利润表</word></line>
<line yMin="20"><word xMin="190" xMax="430" yMin="20" yMax="30">（除特别注明外，金额单位均为人民币千元）</word></line>
<line yMin="30"><word xMin="250" xMax="300" yMin="30" yMax="40">本期金额</word></line>
<line yMin="40"><word xMin="324" xMax="374" yMin="40" yMax="50">上期金额</word></line>
<line yMin="50"><word xMin="388" xMax="430" yMin="50" yMax="60">年初至报告期</word></line>
<line yMin="60"><word xMin="398" xMax="448" yMin="60" yMax="70">期末金额</word></line>
<line yMin="70"><word xMin="466" xMax="505" yMin="70" yMax="80">上年年初至报</word></line>
<line yMin="80"><word xMin="466" xMax="540" yMin="80" yMax="90">告期期末金额</word></line>
<line yMin="100">
  <word xMin="90" xMax="160" yMin="100" yMax="110">营业收入</word>
  <word xMin="250" xMax="300" yMin="100" yMax="110">400</word>
  <word xMin="324" xMax="374" yMin="100" yMax="110">350</word>
  <word xMin="398" xMax="448" yMin="100" yMax="110">1200</word>
  <word xMin="466" xMax="516" yMin="100" yMax="110">1100</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-q3",
            "document_version_id": "version-q3",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2024-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]

        self.assertEqual(len(revenue), 4)
        self.assertEqual(
            [fact["column_role"] for fact in revenue],
            ["current", "comparative", "current", "comparative"],
        )
        self.assertEqual(
            [fact["column_label"] for fact in revenue],
            ["本期金额", "上期金额", "期末金额", "告期期末金额"],
        )
        self.assertEqual(
            [fact["period_basis"] for fact in revenue],
            ["standalone_quarter", "standalone_quarter", "ytd", "ytd"],
        )
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in revenue],
            [
                ("2024-07-01", "2024-09-30"),
                ("2023-07-01", "2023-09-30"),
                ("2024-01-01", "2024-09-30"),
                ("2023-01-01", "2023-09-30"),
            ],
        )
        self.assertEqual([fact["unit"] for fact in revenue], ["千元"] * 4)
        self.assertEqual([fact["column_index"] for fact in revenue], [1, 2, 3, 4])

    def test_annual_balance_sheet_maps_restated_prior_year_end_column(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并资产负债表</word></line>
<line yMin="20"><word xMin="231" xMax="253" yMin="20" yMax="30">附注五</word><word xMin="377" xMax="420" yMin="20" yMax="30">年初余额</word></line>
<line yMin="27"><word xMin="144" xMax="165" yMin="27" yMax="37">项目</word><word xMin="285" xMax="327" yMin="27" yMax="37">年末余额</word><word xMin="464" xMax="517" yMin="27" yMax="37">上年末余额</word></line>
<line yMin="40">
  <word xMin="100" xMax="143" yMin="40" yMax="50">货币资金</word>
  <word xMin="239" xMax="245" yMin="40" yMax="50">1</word>
  <word xMin="278" xMax="347" yMin="40" yMax="50">13339868728</word>
  <word xMin="371" xMax="440" yMin="40" yMax="50">9079035759</word>
  <word xMin="463" xMax="532" yMin="40" yMax="50">9079035759</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-annual-restated-prior-year-end",
            "document_version_id": "version-annual-restated-prior-year-end",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2018-12-31",
            "report_type": "annual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        monetary_funds = [
            fact for fact in facts if fact["metric_id"] == "monetary_funds"
        ]
        self.assertEqual(
            [fact["value_raw"] for fact in monetary_funds],
            ["13339868728", "9079035759", "9079035759"],
        )
        self.assertEqual(
            [fact["column_role"] for fact in monetary_funds],
            ["current", "comparative", "comparative"],
        )
        self.assertEqual(
            [fact["column_label"] for fact in monetary_funds],
            ["年末余额", "年初余额", "上年末余额"],
        )
        self.assertEqual(
            [fact["column_index"] for fact in monetary_funds],
            [1, 2, 3],
        )

    def test_annual_income_statement_maps_restated_comparative_amount(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并利润表</word></line>
<line yMin="20"><word xMin="90" xMax="210" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30">
  <word xMin="100" xMax="150" yMin="30" yMax="40">项目</word>
  <word xMin="300" xMax="360" yMin="30" yMax="40">本年金额</word>
  <word xMin="400" xMax="500" yMin="30" yMax="40">上年金额(经重述)</word>
</line>
<line yMin="45">
  <word xMin="100" xMax="160" yMin="45" yMax="55">营业收入</word>
  <word xMin="300" xMax="360" yMin="45" yMax="55">1000</word>
  <word xMin="400" xMax="460" yMin="45" yMax="55">900</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-annual-restated-income",
            "document_version_id": "version-annual-restated-income",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2018-12-31",
            "report_type": "annual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]
        self.assertEqual([fact["value_raw"] for fact in revenue], ["1000", "900"])
        self.assertEqual(
            [fact["column_role"] for fact in revenue],
            ["current", "comparative"],
        )
        self.assertEqual(
            [fact["column_label"] for fact in revenue],
            ["本年金额", "上年金额(经重述)"],
        )
        self.assertEqual([fact["period_basis"] for fact in revenue], ["annual", "annual"])

    def test_q3_cash_flow_maps_truncated_comparative_ytd_header(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="340" yMin="10" yMax="20">合并现金流量表</word></line>
<line yMin="20"><word xMin="90" xMax="180" yMin="20" yMax="30">2017年1—9月</word></line>
<line yMin="30">
  <word xMin="294" xMax="400" yMin="30" yMax="40">年初至报告期期末金额</word>
  <word xMin="421" xMax="527" yMin="30" yMax="40">上年年初至报告期期末</word>
</line>
<line yMin="37">
  <word xMin="322" xMax="372" yMin="37" yMax="47">（1-9月）</word>
  <word xMin="438" xMax="510" yMin="37" yMax="47">（1-9月）</word>
</line>
<line yMin="55">
  <word xMin="90" xMax="250" yMin="55" yMax="65">经营活动产生的现金流量净额</word>
  <word xMin="294" xMax="360" yMin="55" yMax="65">100</word>
  <word xMin="421" xMax="487" yMin="55" yMax="65">90</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-q3-truncated-comparative-ytd",
            "document_version_id": "version-q3-truncated-comparative-ytd",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2017-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        operating_cash_flow = [
            fact for fact in facts if fact["metric_id"] == "operating_cash_flow"
        ]
        self.assertEqual(
            [fact["value_raw"] for fact in operating_cash_flow],
            ["100", "90"],
        )
        self.assertEqual(
            [fact["column_role"] for fact in operating_cash_flow],
            ["current", "comparative"],
        )
        self.assertEqual(
            [fact["period_basis"] for fact in operating_cash_flow],
            ["ytd", "ytd"],
        )

    def test_date_and_scope_headers_map_four_column_balance_sheet(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="250" xMax="380" yMin="10" yMax="20">资产负债表</word></line>
<line yMin="20"><word xMin="90" xMax="210" yMin="20" yMax="30">单位:人民币千元</word></line>
<line yMin="30">
  <word xMin="300" xMax="390" yMin="30" yMax="40">2018年9月30日</word>
  <word xMin="400" xMax="490" yMin="30" yMax="40">2017年12月31日</word>
  <word xMin="500" xMax="590" yMin="30" yMax="40">2018年9月30日</word>
  <word xMin="600" xMax="690" yMin="30" yMax="40">2017年12月31日</word>
</line>
<line yMin="40">
  <word xMin="300" xMax="340" yMin="40" yMax="50">合并</word>
  <word xMin="400" xMax="440" yMin="40" yMax="50">合并</word>
  <word xMin="500" xMax="540" yMin="40" yMax="50">公司</word>
  <word xMin="600" xMax="640" yMin="40" yMax="50">公司</word>
</line>
<line yMin="60">
  <word xMin="90" xMax="160" yMin="60" yMax="70">货币资金</word>
  <word xMin="300" xMax="350" yMin="60" yMax="70">100</word>
  <word xMin="400" xMax="450" yMin="60" yMax="70">90</word>
  <word xMin="500" xMax="550" yMin="60" yMax="70">80</word>
  <word xMin="600" xMax="650" yMin="60" yMax="70">70</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-scope",
            "document_version_id": "version-scope",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2018-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        funds = [fact for fact in facts if fact["metric_id"] == "monetary_funds"]

        self.assertEqual(len(funds), 4)
        self.assertEqual(
            [fact["statement_scope"] for fact in funds],
            ["consolidated", "consolidated", "parent_only", "parent_only"],
        )
        self.assertEqual(
            [fact["column_role"] for fact in funds],
            ["current", "comparative", "current", "comparative"],
        )
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in funds],
            [
                ("2018-09-30", "2018-09-30"),
                ("2017-12-31", "2017-12-31"),
                ("2018-09-30", "2018-09-30"),
                ("2017-12-31", "2017-12-31"),
            ],
        )
        self.assertEqual([fact["unit"] for fact in funds], ["千元"] * 4)

    def test_split_numeric_date_headers_are_reconstructed(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="76" xMax="166" yMin="10" yMax="20">1．合并资产负债表</word></line>
<line yMin="20">
  <word xMin="346" xMax="401" yMin="20" yMax="30">人民币百万元</word>
  <word xMin="460" xMax="514" yMin="20" yMax="30">人民币百万元</word>
</line>
<line yMin="30">
  <word xMin="332" xMax="350" yMin="30" yMax="40">2026</word>
  <word xMin="363" xMax="368" yMin="30" yMax="40">3</word>
  <word xMin="381" xMax="390" yMin="30" yMax="40">31</word>
  <word xMin="436" xMax="454" yMin="30" yMax="40">2025</word>
  <word xMin="467" xMax="476" yMin="30" yMax="40">12</word>
  <word xMin="489" xMax="498" yMin="30" yMax="40">31</word>
  <word xMin="509" xMax="514" yMin="30" yMax="40">注</word>
</line>
<line yMin="50">
  <word xMin="91" xMax="128" yMin="50" yMax="60">货币资金</word>
  <word xMin="372" xMax="401" yMin="50" yMax="60">261,503</word>
  <word xMin="485" xMax="514" yMin="50" yMax="60">238,909</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-split-date",
            "document_version_id": "version-split-date",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2026-03-31",
            "report_type": "q1",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        funds = [fact for fact in facts if fact["metric_id"] == "monetary_funds"]

        self.assertEqual(len(funds), 2)
        self.assertEqual([fact["column_role"] for fact in funds], ["current", "comparative"])
        self.assertEqual([fact["unit"] for fact in funds], ["百万元", "百万元"])
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in funds],
            [
                ("2026-03-31", "2026-03-31"),
                ("2025-12-31", "2025-12-31"),
            ],
        )

    def test_q3_date_range_headers_are_ytd_and_scope_specific(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="250" xMax="320" yMin="10" yMax="20">利润表</word></line>
<line yMin="20"><word xMin="90" xMax="210" yMin="20" yMax="30">单位:人民币千元</word></line>
<line yMin="30">
  <word xMin="300" xMax="350" yMin="30" yMax="40">2018年1-9月</word>
  <word xMin="400" xMax="450" yMin="30" yMax="40">2017年1-9月</word>
  <word xMin="500" xMax="550" yMin="30" yMax="40">2018年1-9月</word>
  <word xMin="600" xMax="650" yMin="30" yMax="40">2017年1-9月</word>
</line>
<line yMin="40">
  <word xMin="300" xMax="340" yMin="40" yMax="50">合并</word>
  <word xMin="400" xMax="440" yMin="40" yMax="50">合并</word>
  <word xMin="500" xMax="540" yMin="40" yMax="50">公司</word>
  <word xMin="600" xMax="640" yMin="40" yMax="50">公司</word>
</line>
<line yMin="60">
  <word xMin="90" xMax="160" yMin="60" yMax="70">营业收入</word>
  <word xMin="300" xMax="350" yMin="60" yMax="70">100</word>
  <word xMin="400" xMax="450" yMin="60" yMax="70">90</word>
  <word xMin="500" xMax="550" yMin="60" yMax="70">80</word>
  <word xMin="600" xMax="650" yMin="60" yMax="70">70</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-q3-dates",
            "document_version_id": "version-q3-dates",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2018-09-30",
            "report_type": "q3",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        revenue = [fact for fact in facts if fact["metric_id"] == "revenue"]

        self.assertEqual(len(revenue), 4)
        self.assertEqual(
            [fact["statement_scope"] for fact in revenue],
            ["consolidated", "consolidated", "parent_only", "parent_only"],
        )
        self.assertEqual(
            [fact["column_role"] for fact in revenue],
            ["current", "comparative", "current", "comparative"],
        )
        self.assertEqual([fact["period_basis"] for fact in revenue], ["ytd"] * 4)
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in revenue],
            [
                ("2018-01-01", "2018-09-30"),
                ("2017-01-01", "2017-09-30"),
                ("2018-01-01", "2018-09-30"),
                ("2017-01-01", "2017-09-30"),
            ],
        )

    def test_balance_sheet_header_maps_end_and_opening_balances(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="260" xMax="370" yMin="10" yMax="20">合并资产负债表</word></line>
<line yMin="20"><word xMin="90" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30"><word xMin="350" xMax="400" yMin="30" yMax="40">期末余额</word><word xMin="460" xMax="510" yMin="30" yMax="40">期初余额</word></line>
<line yMin="40"><word xMin="100" xMax="180" yMin="40" yMax="50">资产总计</word></line>
</block></flow>
<flow><block><line yMin="40"><word xMin="340" xMax="400" yMin="40" yMax="50">1000</word><word xMin="450" xMax="510" yMin="40" yMax="50">900</word></line></block></flow>
</page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-3",
            "document_version_id": "version-3",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2024-12-31",
            "report_type": "annual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        assets = [fact for fact in facts if fact["metric_id"] == "total_assets"]

        self.assertEqual(len(assets), 2)
        self.assertEqual(assets[0]["column_role"], "current")
        self.assertEqual(assets[1]["column_role"], "comparative")
        self.assertEqual(assets[0]["fact_period_start"], "2024-12-31")
        self.assertEqual(assets[1]["fact_period_start"], "2023-12-31")
        self.assertEqual(assets[0]["period_basis"], "instant")


    def test_ending_cash_equivalents_is_an_instant_even_in_cash_flow_table(self) -> None:
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="240" xMax="360" yMin="10" yMax="20">合并现金流量表</word></line>
<line yMin="20"><word xMin="80" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30">
  <word xMin="250" xMax="330" yMin="30" yMax="40">本期发生额</word>
  <word xMin="400" xMax="480" yMin="30" yMax="40">上期发生额</word>
</line>
<line yMin="50">
  <word xMin="80" xMax="210" yMin="50" yMax="60">六、期末现金及现金等价物余额</word>
  <word xMin="250" xMax="330" yMin="50" yMax="60">240</word>
  <word xMin="400" xMax="480" yMin="50" yMax="60">200</word>
</line>
</block></flow></page></doc></body></html>"""
        document = {
            "announcement_id": "bbox-ann-ending-cash-instant",
            "document_version_id": "version-ending-cash-instant",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2024-12-31",
            "report_type": "annual",
        }

        facts = parse_bbox_xhtml(xhtml, document)
        ending_cash = [
            fact for fact in facts
            if fact["metric_id"] == "ending_cash_equivalents"
        ]

        self.assertEqual(len(ending_cash), 2)
        self.assertEqual(
            [fact["column_label"] for fact in ending_cash],
            ["本期发生额", "上期发生额"],
        )
        self.assertEqual(
            [fact["period_basis"] for fact in ending_cash],
            ["instant", "instant"],
        )
        self.assertEqual(
            [(fact["fact_period_start"], fact["fact_period_end"]) for fact in ending_cash],
            [
                ("2024-12-31", "2024-12-31"),
                ("2023-12-31", "2023-12-31"),
            ],
        )

    def test_equity_alias_with_parenthesized_shareholder_name(self) -> None:
        import pandas as pd
        from a_share_research.financial_reports import _match_metric_alias
        dictionary = pd.read_csv(
            ROOT / "data" / "metadata" / "financial_report_metric_dictionary.csv",
            dtype=str,
        ).fillna("")
        row = dictionary.loc[dictionary["metric_id"].eq("total_equity")].iloc[0]
        aliases = row["label_aliases"].split("|")
        self.assertEqual(
            _match_metric_alias("所有者权益（或股东权益）合计", aliases, allow_qualifier=True)[0],
            "所有者权益（或股东权益）合计",
        )
        self.assertEqual(
            _match_metric_alias("归属于母公司所有者权益合计", aliases, allow_qualifier=True)[0],
            "",
        )

    def test_wrapped_equity_labels_join_when_amounts_are_on_first_line(self) -> None:
        import pandas as pd
        dictionary = pd.read_csv(
            ROOT / "data" / "metadata" / "financial_report_metric_dictionary.csv",
            dtype=str,
        ).fillna("")
        xhtml = """<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page>
<flow><block>
<line yMin="10"><word xMin="200" xMax="360" yMin="10" yMax="20">合并资产负债表</word></line>
<line yMin="20"><word xMin="80" xMax="150" yMin="20" yMax="30">单位：元</word></line>
<line yMin="30"><word xMin="330" xMax="390" yMin="30" yMax="40">期末余额</word><word xMin="460" xMax="520" yMin="30" yMax="40">期初余额</word></line>
<line yMin="50"><word xMin="80" xMax="245" yMin="50" yMax="60">归属于母公司所有者权益（或股</word><word xMin="330" xMax="390" yMin="50" yMax="60">500</word><word xMin="460" xMax="520" yMin="50" yMax="60">400</word></line>
<line yMin="62"><word xMin="80" xMax="160" yMin="62" yMax="72">东权益）合计</word></line>
<line yMin="90"><word xMin="80" xMax="245" yMin="90" yMax="100">所有者权益（或股东权益）合</word><word xMin="330" xMax="390" yMin="90" yMax="100">600</word><word xMin="460" xMax="520" yMin="90" yMax="100">450</word></line>
<line yMin="102"><word xMin="80" xMax="120" yMin="102" yMax="112">计</word></line>
</block></flow></page></doc></body></html>"""
        doc = {
            "announcement_id": "wrapped-equity",
            "document_version_id": "wrapped-equity-v1",
            "canonical_security_id": "600346",
            "report_period_candidate": "2025-03-31",
            "report_type": "q1",
            "identity_status": "adjudicated",
        }
        facts = parse_bbox_xhtml(xhtml, doc, dictionary)
        parent = [r for r in facts if r["metric_id"] == "parent_equity"]
        total = [r for r in facts if r["metric_id"] == "total_equity"]
        self.assertEqual([r["value_decimal"] for r in parent], ["500", "400"])
        self.assertEqual([r["value_decimal"] for r in total], ["600", "450"])
        self.assertTrue(all(r["statement_scope"] == "consolidated" for r in parent + total))


    def test_date_prefixed_accounting_statement_note_heading_stops_fact_parsing(self) -> None:
        cash_flow_heading = "\u73b0\u91d1\u6d41\u91cf\u8868"
        current_label = "\u672c\u671f\u53d1\u751f\u989d"
        prior_label = "\u4e0a\u671f\u53d1\u751f\u989d"
        metric_label = "\u7ecf\u8425\u6d3b\u52a8\u4ea7\u751f\u7684\u73b0\u91d1\u6d41\u91cf\u51c0\u989d"
        note_heading = "2019\u5e74\u4e0a\u534a\u5e74\u5ea6\u4f1a\u8ba1\u62a5\u8868\u6ce8\u91ca"
        document = {
            "announcement_id": "bbox-ann-note-boundary",
            "document_version_id": "version-note-boundary",
            "canonical_security_id": "000001",
            "identity_status": "adjudicated",
            "report_period_candidate": "2019-06-30",
            "report_type": "semiannual",
        }

        def parse_with_note_line(note_line: str):
            xhtml = f"""<html xmlns="http://www.w3.org/1999/xhtml"><body><doc><page><flow><block>
<line yMin="10"><word xMin="280" xMax="350" yMin="10" yMax="20">{cash_flow_heading}</word></line>
<line yMin="20"><word xMin="360" xMax="410" yMin="20" yMax="30">{current_label}</word><word xMin="460" xMax="510" yMin="20" yMax="30">{prior_label}</word></line>
<line yMin="40"><word xMin="90" xMax="220" yMin="40" yMax="50">{metric_label}</word><word xMin="360" xMax="410" yMin="40" yMax="50">100</word><word xMin="460" xMax="510" yMin="40" yMax="50">80</word></line>
<line yMin="60"><word xMin="80" xMax="300" yMin="60" yMax="70">{note_line}</word></line>
<line yMin="80"><word xMin="360" xMax="410" yMin="80" yMax="90">{current_label}</word><word xMin="460" xMax="510" yMin="80" yMax="90">{prior_label}</word></line>
<line yMin="100"><word xMin="90" xMax="220" yMin="100" yMax="110">{metric_label}</word><word xMin="360" xMax="410" yMin="100" yMax="110">100</word><word xMin="460" xMax="510" yMin="100" yMax="110">80</word></line>
</block></flow></page></doc></body></html>"""
            return [
                fact for fact in parse_bbox_xhtml(xhtml, document)
                if fact["metric_id"] == "operating_cash_flow"
            ]

        facts = parse_with_note_line(note_heading)
        self.assertEqual(len(facts), 2)
        self.assertEqual([fact["value_raw"] for fact in facts], ["100", "80"])

        bare_heading = "\u4f1a\u8ba1\u62a5\u8868\u6ce8\u91ca"
        bare = parse_with_note_line(bare_heading)
        self.assertEqual(len(bare), 2)

        statement_note_subheading = "29\u73b0\u91d1\u6d41\u91cf\u8868\u6ce8\u91ca"
        subheading = parse_with_note_line(statement_note_subheading)
        self.assertEqual(len(subheading), 4)

        narrative = parse_with_note_line("\u8bf7\u53c2\u9605" + note_heading)
        self.assertEqual(len(narrative), 4)

if __name__ == "__main__":
    unittest.main()
