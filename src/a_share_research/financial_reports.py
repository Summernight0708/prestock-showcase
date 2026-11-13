from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

PARSER_VERSION = "0.2.0"
METRIC_DICTIONARY_VERSION = "1.1.0"

DEFAULT_METRIC_DICTIONARY = [
    {"metric_id": "revenue", "metric_name_zh": "营业收入", "statement_type": "income_statement", "label_aliases": "营业收入", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "total_operating_revenue", "metric_name_zh": "营业总收入", "statement_type": "income_statement", "label_aliases": "营业总收入", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "operating_cost", "metric_name_zh": "营业成本", "statement_type": "income_statement", "label_aliases": "营业成本", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "total_operating_cost", "metric_name_zh": "营业总成本", "statement_type": "income_statement", "label_aliases": "营业总成本", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "operating_profit", "metric_name_zh": "营业利润", "statement_type": "income_statement", "label_aliases": "营业利润", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "total_profit", "metric_name_zh": "利润总额", "statement_type": "income_statement", "label_aliases": "利润总额", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "net_profit", "metric_name_zh": "净利润", "statement_type": "income_statement", "label_aliases": "净利润", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "parent_net_profit", "metric_name_zh": "归属于母公司股东的净利润", "statement_type": "income_statement", "label_aliases": "归属于母公司股东的净利润|归属于上市公司股东的净利润|归属于母公司所有者的净利润", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "eps_basic", "metric_name_zh": "基本每股收益", "statement_type": "income_statement", "label_aliases": "基本每股收益", "canonical_unit": "CNY/share", "currency": "CNY"},
    {"metric_id": "eps_diluted", "metric_name_zh": "稀释每股收益", "statement_type": "income_statement", "label_aliases": "稀释每股收益", "canonical_unit": "CNY/share", "currency": "CNY"},
    {"metric_id": "total_assets", "metric_name_zh": "资产总计", "statement_type": "balance_sheet", "label_aliases": "资产总计|资产合计", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "total_liabilities", "metric_name_zh": "负债合计", "statement_type": "balance_sheet", "label_aliases": "负债合计|负债总计", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "total_equity", "metric_name_zh": "所有者权益合计", "statement_type": "balance_sheet", "label_aliases": "所有者权益合计|股东权益合计", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "parent_equity", "metric_name_zh": "归属于母公司所有者权益合计", "statement_type": "balance_sheet", "label_aliases": "归属于母公司所有者权益合计|归属于母公司股东权益合计", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "monetary_funds", "metric_name_zh": "货币资金", "statement_type": "balance_sheet", "label_aliases": "货币资金", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "accounts_receivable", "metric_name_zh": "应收账款", "statement_type": "balance_sheet", "label_aliases": "应收账款", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "inventory", "metric_name_zh": "存货", "statement_type": "balance_sheet", "label_aliases": "存货", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "operating_cash_flow", "metric_name_zh": "经营活动产生的现金流量净额", "statement_type": "cash_flow", "label_aliases": "经营活动产生的现金流量净额", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "investing_cash_flow", "metric_name_zh": "投资活动产生的现金流量净额", "statement_type": "cash_flow", "label_aliases": "投资活动产生的现金流量净额", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "financing_cash_flow", "metric_name_zh": "筹资活动产生的现金流量净额", "statement_type": "cash_flow", "label_aliases": "筹资活动产生的现金流量净额", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "ending_cash_equivalents", "metric_name_zh": "期末现金及现金等价物余额", "statement_type": "cash_flow", "label_aliases": "期末现金及现金等价物余额", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "current_assets", "metric_name_zh": "流动资产合计", "statement_type": "balance_sheet", "label_aliases": "流动资产合计|流动资产总计", "canonical_unit": "CNY", "currency": "CNY"},
    {"metric_id": "current_liabilities", "metric_name_zh": "流动负债合计", "statement_type": "balance_sheet", "label_aliases": "流动负债合计|流动负债总计", "canonical_unit": "CNY", "currency": "CNY"},
]

UNIT_MULTIPLIERS = {
    "元": Decimal("1"),
    "人民币元": Decimal("1"),
    "千元": Decimal("1000"),
    "万元": Decimal("10000"),
    "百万元": Decimal("1000000"),
    "亿元": Decimal("100000000"),
    "股": Decimal("1"),
    "万股": Decimal("10000"),
    "元/股": Decimal("1"),
}
UNIT_PATTERN = re.compile(
    r"(?:单位|金额单位)\s*(?:[：:]|(?:均?\s*为))\s*"
    r"(?:(?:人民币)|(?:[（(]人民币[）)]))?\s*"
    r"(百万元|亿元|万元|千元|元／股|元/股|万股|股|元)"
)
CURRENCY_UNIT_PATTERN = re.compile(r"人民币\s*(百万元|亿元|万元|千元)")
NUMBER_PATTERN = re.compile(
    r"（\s*[-+−－]?\d[\d,，]*(?:\.\d+)?\s*）"
    r"|\(\s*[-+−－]?\d[\d,，]*(?:\.\d+)?\s*\)"
    r"|[-+−－]?\d[\d,，]*(?:\.\d+)?"
)
MISSING_CELL_PATTERN = re.compile(r"(?<!\S)[—–－-](?!\S)")
CANCELLATION_PATTERN = re.compile(r"取消|撤销|作废|终止披露")
RESTATEMENT_PATTERN = re.compile(r"重述|追溯调整|前期差错")
REISSUE_PATTERN = re.compile(r"重新披露|重新发布|重新出具|重发")
SUPPLEMENT_PATTERN = re.compile(r"补充|补遗")
CORRECTION_PATTERN = re.compile(r"更正|修订|修正|调整|更新")
STATEMENT_HEADING_PATTERN = re.compile(
    r"^\s*(合并|母公司|本公司)?\s*(资产负债表|利润表|现金流量表)\s*$"
)
STATEMENT_NOTE_END_PATTERN = re.compile(r"财务报表附注|会计报表附注|重要会计政策及会计估计")
COLUMN_HEADER_PATTERN = re.compile(
    r"本期发生额|本期金额|本期数|本年金额|本年数|本年累计|本期期末|本期末|期末余额|期末金额|"
    r"上期发生额|上期金额|上期数|上年同期|上年金额|上年数|上期期末|上期末|期初余额|上年年末余额|告期期末金额"
)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_bool(value: Any) -> bool:
    return normalize_text(value).lower() in {"true", "1", "yes", "y"}


def build_document_version_id(announcement_id: str, pdf_sha256: str) -> str:
    payload = f"{normalize_text(announcement_id)}:{normalize_text(pdf_sha256).lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_fact_id(
    document_version_id: str,
    statement_scope: str,
    statement_type: str,
    page_number: int,
    table_index: int | None,
    row_index: int,
    metric_id: str,
    duplicate_ordinal: int,
) -> str:
    payload = [
        document_version_id,
        statement_scope or "unknown",
        statement_type,
        int(page_number),
        table_index if table_index is not None else -1,
        int(row_index),
        metric_id,
        int(duplicate_ordinal),
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def classify_document_version(document: dict[str, Any]) -> str:
    title = normalize_text(document.get("announcement_title") or document.get("title"))
    category = normalize_text(document.get("category_key"))
    is_full_report = parse_bool(document.get("is_full_report_candidate")) or category in {
        "annual_report", "semiannual_report", "q1_report", "q3_report"
    }
    if parse_bool(document.get("is_cancelled")) or CANCELLATION_PATTERN.search(title):
        return "cancellation"
    # A clearly labelled pre-update/pre-correction full report is the predecessor,
    # not a correction notice. Keep it eligible as an original relation candidate.
    if re.search(r"修订前|更正前|调整前|补充前|更新前", title):
        return "original"
    if RESTATEMENT_PATTERN.search(title):
        return "restatement"
    if REISSUE_PATTERN.search(title):
        return "reissue"
    if is_full_report and (
        parse_bool(document.get("is_amended"))
        or re.search(r"修订版|修订稿|更新后|更新版|更正后|更正版|补充版|补充稿", title)
    ):
        return "amended_full_report"
    if SUPPLEMENT_PATTERN.search(title):
        return "supplement"
    if CORRECTION_PATTERN.search(title):
        return "correction"
    if not title:
        return "unknown"
    return "original"


def resolve_document_relations(documents: pd.DataFrame) -> pd.DataFrame:
    result = documents.copy().fillna("")
    if result.empty:
        for column in (
            "version_role", "relation_status", "supersedes_document_version_id",
            "relation_candidate_ids", "relation_evidence",
        ):
            result[column] = pd.Series(dtype="object")
        return result

    required = {
        "document_version_id", "canonical_security_id",
        "report_period_candidate", "category_key", "announcement_id",
    }
    missing = sorted(required - set(result.columns))
    if missing:
        raise ValueError(f"版本关系输入缺少字段：{missing}")

    result["version_role"] = result.apply(
        lambda row: normalize_text(row.get("version_role"))
        or classify_document_version(row.to_dict()),
        axis=1,
    )
    result["relation_status"] = "not_applicable"
    result["supersedes_document_version_id"] = ""
    result["relation_candidate_ids"] = ""
    result["relation_evidence"] = ""

    originals = result.loc[result["version_role"].eq("original")].copy()
    for index, row in result.iterrows():
        role = row["version_role"]
        if role == "original":
            continue
        if role == "unknown":
            result.at[index, "relation_status"] = "unresolved_unknown_role"
            continue
        if role == "cancellation":
            result.at[index, "relation_status"] = "cancellation_candidate_unverified"
        else:
            result.at[index, "relation_status"] = "unresolved_no_original"

        same_group = originals.loc[
            originals["canonical_security_id"].astype(str).eq(str(row["canonical_security_id"]))
            & originals["report_period_candidate"].astype(str).eq(str(row["report_period_candidate"]))
            & originals["category_key"].astype(str).eq(str(row["category_key"]))
            & originals["announcement_id"].astype(str).ne(str(row["announcement_id"]))
        ]
        if not same_group.empty:
            candidate_ids = sorted(same_group["document_version_id"].astype(str).tolist())
            result.at[index, "relation_candidate_ids"] = "|".join(candidate_ids)
            if len(candidate_ids) == 1:
                if role != "cancellation":
                    result.at[index, "relation_status"] = "candidate_unverified"
            else:
                result.at[index, "relation_status"] = (
                    "cancellation_candidate_ambiguous"
                    if role == "cancellation" else "ambiguous_candidate"
                )
        # Title and group similarity are discovery signals only. No relation is
        # confirmed and supersedes_document_version_id remains blank.
    return result


def parse_decimal_value(raw_text: str, unit_scale: str) -> Decimal | None:
    raw = normalize_text(raw_text)
    if not raw:
        return None
    if raw in {"—", "–", "-", "－", "--", "---", "不适用", "不适用", "N/A", "n/a", "NA", "无"}:
        return None

    scale_name = normalize_text(unit_scale)
    multiplier = UNIT_MULTIPLIERS.get(scale_name)
    if multiplier is None:
        try:
            multiplier = Decimal(scale_name)
        except (InvalidOperation, ValueError):
            return None

    value = raw.replace("，", ",").replace("−", "-").replace("－", "-")
    value = value.replace("人民币", "").replace("元/股", "").replace("万元", "")
    value = value.replace("亿元", "").replace("千元", "").replace("百万元", "")
    value = value.replace("元", "").replace("股", "").replace(",", "").replace(" ", "")
    negative = False
    if (value.startswith("(") and value.endswith(")")) or (
        value.startswith("（") and value.endswith("）")
    ):
        negative = True
        value = value[1:-1]
    value = value.replace("（", "").replace("）", "").replace("(", "").replace(")", "")
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if negative:
        number = -abs(number)
    return number * multiplier


def detect_unit_scale(text: str) -> str:
    source = text or ""
    matches = UNIT_PATTERN.findall(source)
    if not matches:
        matches = CURRENCY_UNIT_PATTERN.findall(source)
    unique = sorted(set(matches), key=lambda value: (-len(value), value))
    if len(unique) == 1:
        return unique[0]
    return "unknown"


def _statement_heading(line: str) -> tuple[str, str] | None:
    normalized = " ".join((line or "").split())
    normalized = re.sub(
        r"^(?:(?:\d+|[一二三四五六七八九十]+)[、.．)]|"
        r"[（(](?:\d+|[一二三四五六七八九十]+)[）)])\s*",
        "",
        normalized,
    )
    match = STATEMENT_HEADING_PATTERN.fullmatch(normalized)
    if not match:
        return None
    scope_label, statement_label = match.groups()
    statement_type = {
        "资产负债表": "balance_sheet",
        "利润表": "income_statement",
        "现金流量表": "cash_flow",
    }[statement_label]
    scope = (
        "consolidated" if scope_label == "合并"
        else "parent_only" if scope_label in {"母公司", "本公司"}
        else "unknown"
    )
    return statement_type, scope


def detect_statement_scope(page_text: str) -> str:
    scopes = {
        heading[1]
        for raw_line in (page_text or "").splitlines()
        if (heading := _statement_heading(raw_line)) is not None
    }
    return next(iter(scopes)) if len(scopes) == 1 else "unknown"


def _iter_statement_lines(text: str):
    active_statement_type = ""
    active_scope = "unknown"
    active_unit = "unknown"
    context: list[str] = []
    column_header_lines: list[str] = []

    for page_number, page_text in enumerate((text or "").split("\f"), start=1):
        for line_number, raw_line in enumerate(page_text.splitlines(), start=1):
            line = " ".join(raw_line.split())
            if not line:
                continue
            if STATEMENT_NOTE_END_PATTERN.search(line):
                active_statement_type = ""
                active_scope = "unknown"
                active_unit = "unknown"
                context = []
                column_header_lines = []
                continue

            heading = _statement_heading(line)
            if heading is not None:
                active_statement_type, active_scope = heading
                active_unit = "unknown"
                context = [line]
                column_header_lines = []
                continue

            if UNIT_PATTERN.search(raw_line):
                active_unit = detect_unit_scale(raw_line)
            if COLUMN_HEADER_PATTERN.search(line):
                column_header_lines.append(line)
                column_header_lines = column_header_lines[-4:]

            yield {
                "page_number": page_number,
                "line_number": line_number,
                "raw_line": raw_line,
                "line": line,
                "statement_type": active_statement_type,
                "statement_scope": active_scope,
                "unit_scale": active_unit,
                "context": "\n".join(context[-12:] + column_header_lines),
            }
            context.append(line)


def detect_column_role(context: str) -> str:
    text = context or ""
    current = bool(re.search(
        r"本期发生额|本期金额|本期数|本年金额|本年数|本年累计|本期期末|本期末|期末余额",
        text,
    ))
    comparative = bool(re.search(
        r"上期发生额|上期金额|上期数|上年同期|上年金额|上年数|上期期末|上期末|期初余额",
        text,
    ))
    if current and not comparative:
        return "current"
    if comparative and not current:
        return "comparative"
    return "unknown"


def detect_column_roles(context: str, value_count: int) -> list[str]:
    text = context or ""
    current = bool(re.search(
        r"本期发生额|本期金额|本期数|本年金额|本年数|本年累计|本期期末|本期末|期末余额",
        text,
    ))
    comparative = bool(re.search(
        r"上期发生额|上期金额|上期数|上年同期|上年金额|上年数|上期期末|上期末|期初余额",
        text,
    ))
    roles = ["unknown"] * max(0, value_count)
    if current and comparative and value_count:
        roles[0] = "current"
        if value_count > 1:
            roles[1] = "comparative"
    elif current and value_count:
        roles[0] = "current"
    elif comparative and value_count:
        roles[0] = "comparative"
    return roles


def detect_period_basis(
    context: str, statement_type: str, report_type: str = ""
) -> str:
    if statement_type == "balance_sheet":
        return "instant"
    text = context or ""
    if re.search(r"单季度|本季度|本季金额|单季金额|本报告期", text):
        return "standalone_quarter"
    if re.search(r"年初(?:至|到)报告期(?:期)?\s*末|上年年初至报告期(?:期)?\s*末|本年累计|累计金额|累计数|九个月期间|1\s*[-—–－至]\s*9\s*月", text):
        return "ytd"
    if re.search(r"1\s*[—–－-]\s*12\s*月|年度金额|本年度金额|全年金额", text):
        return "annual"
    if report_type == "annual":
        return "annual"
    if report_type == "semiannual":
        return "ytd"
    if report_type == "q1":
        return "standalone_quarter"
    # Q3 reports can expose both the standalone quarter and year-to-date
    # columns. Without a clear table header, do not guess which basis applies.
    return "unknown"


def _derive_fact_period(
    report_period: str, period_basis: str, column_role: str
) -> tuple[str, str]:
    if column_role not in {"current", "comparative"}:
        return "", ""
    try:
        end_date = date.fromisoformat(report_period[:10])
    except (ValueError, TypeError):
        return "", ""
    if column_role == "comparative":
        try:
            end_date = end_date.replace(year=end_date.year - 1)
        except ValueError:
            end_date = end_date.replace(year=end_date.year - 1, day=28)
    if period_basis == "instant":
        return end_date.isoformat(), end_date.isoformat()
    if period_basis in {"annual", "ytd"}:
        return date(end_date.year, 1, 1).isoformat(), end_date.isoformat()
    if period_basis == "standalone_quarter":
        quarter_start_month = ((end_date.month - 1) // 3) * 3 + 1
        return date(end_date.year, quarter_start_month, 1).isoformat(), end_date.isoformat()
    return "", ""


def _metric_rows(metric_dictionary: pd.DataFrame | None) -> list[dict[str, Any]]:
    if metric_dictionary is None:
        rows = [dict(row) for row in DEFAULT_METRIC_DICTIONARY]
    else:
        rows = metric_dictionary.fillna("").to_dict("records")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        aliases = row.get("label_aliases", row.get("keywords", ""))
        if isinstance(aliases, str):
            aliases = [item.strip() for item in aliases.split("|") if item.strip()]
        normalized.append({
            **row,
            "metric_id": normalize_text(row.get("metric_id")),
            "metric_name_zh": normalize_text(row.get("metric_name_zh") or row.get("metric_name")),
            "statement_type": normalize_text(row.get("statement_type")),
            "label_aliases": aliases,
        })
    return normalized


def _extract_numeric_tokens(text_after_label: str) -> list[str]:
    text = text_after_label or ""
    candidates: list[tuple[int, str]] = []
    for match in NUMBER_PATTERN.finditer(text):
        if re.match(r"\s*[％%]", text[match.end():]):
            continue
        if re.search(r"注\s*$", text[max(0, match.start() - 5):match.start()]):
            continue
        candidates.append((match.start(), match.group(0).strip()))

    # A standalone dash is a missing cell, not numeric zero. It is only
    # recognized when separated from surrounding text, so quoted dashes in
    # explanatory labels (e.g. “亏损以‘－’号填列”) are not treated as cells.
    for match in MISSING_CELL_PATTERN.finditer(text):
        candidates.append((match.start(), match.group(0).strip()))

    candidates.sort(key=lambda item: item[0])
    # The core statements normally expose current and comparative columns.
    # Percentages and note references are excluded before this conservative cap.
    return [value for _, value in candidates[:2]]


def _match_metric_alias(
    line: str, aliases: list[str], allow_qualifier: bool = False
) -> tuple[str, int]:
    # Match row labels at the start of a financial-statement row. This rejects
    # narrative mentions and overlapping substrings such as "流动资产合计".
    for alias in sorted(aliases, key=len, reverse=True):
        position = line.find(alias)
        if position < 0:
            continue
        prefix = line[:position].strip()
        if prefix.startswith(("其中：", "其中:")):
            if not allow_qualifier:
                continue
            prefix = re.sub(r"^其中[：:]\s*", "", prefix)
        prefix = re.sub(
            r"^(?:[一二三四五六七八九十]+[、.．)]|"
            r"[（(](?:[一二三四五六七八九十]+|\d+)[）)]|"
            r"\d+[、.．)]|[加减][：:])\s*",
            "",
            prefix,
        ).strip()
        if prefix:
            continue
        return alias, position
    return "", -1


def _resolve_metric_unit(
    metric: dict[str, Any], page_unit: str, line: str
) -> tuple[str, bool]:
    canonical_unit = normalize_text(metric.get("canonical_unit"))
    if canonical_unit == "CNY/share":
        has_per_share_unit = bool(re.search(r"元\s*[／/]\s*股", line))
        if has_per_share_unit or page_unit in {"元", "人民币元", "元/股"}:
            return "元/股", True
        return page_unit, False
    if canonical_unit == "CNY":
        compatible_units = {"元", "人民币元", "千元", "万元", "百万元", "亿元"}
        return page_unit, page_unit in compatible_units
    return page_unit, False


def _quarantine_reasons(
    document: dict[str, Any],
    report_period: str,
    statement_scope: str,
    unit_scale: str,
    period_basis: str,
    column_role: str,
    unit_compatible: bool = True,
) -> list[str]:
    reasons: list[str] = []
    identity_status = normalize_text(document.get("identity_status"))
    if identity_status not in {"adjudicated", "code_history_mapped", "confirmed"}:
        reasons.append("identity_not_manually_confirmed")
    if not report_period:
        reasons.append("report_period_unconfirmed")
    if statement_scope == "unknown":
        reasons.append("statement_scope_unknown")
    if unit_scale == "unknown":
        reasons.append("unit_unknown")
    elif not unit_compatible:
        reasons.append("unit_incompatible_with_metric")
    if period_basis == "unknown":
        reasons.append("period_basis_unknown")
    if column_role == "unknown":
        reasons.append("column_role_unknown")
    reasons.append("gold_set_not_manually_verified")
    return reasons


def parse_financial_report_text(
    document: dict[str, Any],
    text: str,
    metric_dictionary: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    metrics = _metric_rows(metric_dictionary)
    announcement_id = normalize_text(document.get("announcement_id"))
    pdf_sha256 = normalize_text(document.get("pdf_sha256")).lower()
    document_version_id = normalize_text(document.get("document_version_id")) or build_document_version_id(
        announcement_id, pdf_sha256
    )
    report_period = normalize_text(
        document.get("report_period_candidate") or document.get("report_period")
    )
    report_type = normalize_text(document.get("report_type"))
    if not report_type:
        report_type = {
            "annual_report": "annual",
            "semiannual_report": "semiannual",
            "q1_report": "q1",
            "q3_report": "q3",
        }.get(normalize_text(document.get("category_key")), "")

    facts: list[dict[str, Any]] = []
    for item in _iter_statement_lines(text):
        statement_type = item["statement_type"]
        if not statement_type:
            continue
        line = item["line"]

        for metric in metrics:
            if metric["statement_type"] != statement_type:
                continue
            matched_alias, label_position = _match_metric_alias(
                line, metric["label_aliases"]
            )
            if not matched_alias:
                continue

            unit_scale, unit_compatible = _resolve_metric_unit(
                metric, item["unit_scale"], line
            )
            tail = line[label_position + len(matched_alias):]
            numeric_tokens = _extract_numeric_tokens(tail)
            if not numeric_tokens:
                continue

            context = item["context"]
            period_basis = detect_period_basis(
                context, statement_type, report_type
            )
            column_roles = detect_column_roles(context, len(numeric_tokens))
            multiplier = UNIT_MULTIPLIERS.get(unit_scale)
            metric_currency = normalize_text(metric.get("currency"))
            if not metric_currency and unit_scale in {
                "元", "人民币元", "千元", "万元", "百万元", "亿元", "元/股"
            }:
                metric_currency = "CNY"

            for duplicate_ordinal, (raw_value, column_role) in enumerate(
                zip(numeric_tokens, column_roles), start=1
            ):
                value_decimal = parse_decimal_value(raw_value, unit_scale)
                period_start, period_end = _derive_fact_period(
                    report_period, period_basis, column_role
                )
                reasons = _quarantine_reasons(
                    document, report_period, item["statement_scope"], unit_scale,
                    period_basis, column_role, unit_compatible,
                )
                if normalize_text(document.get("report_period_status")) not in {
                    "", "confirmed", "manually_verified"
                }:
                    reasons.append("report_period_not_manually_confirmed")
                if normalize_text(document.get("version_role_candidate")) not in {
                    "", "original"
                }:
                    reasons.append("document_version_relation_unverified")
                if value_decimal is None:
                    reasons.append("value_or_unit_not_parseable")

                fact_id = build_fact_id(
                    document_version_id,
                    item["statement_scope"],
                    statement_type,
                    item["page_number"],
                    None,
                    item["line_number"],
                    metric["metric_id"],
                    duplicate_ordinal,
                )
                facts.append({
                    "fact_id": fact_id,
                    "document_version_id": document_version_id,
                    "announcement_id": announcement_id,
                    "canonical_security_id": normalize_text(document.get("canonical_security_id")),
                    "source_symbol": normalize_text(document.get("source_symbol")),
                    "document_report_period": report_period,
                    "fact_period_start": period_start,
                    "fact_period_end": period_end,
                    "statement_type": statement_type,
                    "statement_scope": item["statement_scope"],
                    "table_index": "",
                    "page_number": item["page_number"],
                    "row_index": item["line_number"],
                    "column_index": duplicate_ordinal,
                    "column_label": column_role,
                    "column_role": column_role,
                    "period_basis": period_basis,
                    "metric_id": metric["metric_id"],
                    "line_item_code": "",
                    "line_item_name_raw": matched_alias,
                    "value_raw": raw_value,
                    "value_decimal": str(value_decimal) if value_decimal is not None else "",
                    "currency": metric_currency,
                    "unit": unit_scale,
                    "scale": str(multiplier) if multiplier is not None else "",
                    "sign_convention": "negative_parentheses_or_sign",
                    "source_cell_text": item["raw_line"],
                    "extractor_name": normalize_text(document.get("extractor_name")) or "Poppler pdftotext",
                    "extractor_version": normalize_text(document.get("extractor_version")),
                    "parser_version": PARSER_VERSION,
                    "validation_status": "quarantined",
                    "quarantine_reason": "|".join(dict.fromkeys(reasons)),
                })
    return facts


def extract_unmapped_statement_rows(
    document: dict[str, Any],
    text: str,
    metric_dictionary: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    metrics = _metric_rows(metric_dictionary)
    rows: list[dict[str, Any]] = []
    for item in _iter_statement_lines(text):
        statement_type = item["statement_type"]
        if not statement_type:
            continue
        line = item["line"]
        if not _extract_numeric_tokens(line):
            continue
        if not re.search(r"[\u4e00-\u9fff]", line):
            continue
        if re.match(r"^\d{4}\s*年.*\d{1,2}\s*月", line):
            continue
        if re.match(r"^\d+\s*/\s*\d+$", line):
            continue
        if any(
            metric["statement_type"] == statement_type
            and _match_metric_alias(line, metric["label_aliases"])[0]
            for metric in metrics
        ):
            continue
        rows.append({
            "announcement_id": normalize_text(document.get("announcement_id")),
            "document_version_id": normalize_text(document.get("document_version_id")),
            "canonical_security_id": normalize_text(document.get("canonical_security_id")),
            "statement_type": statement_type,
            "statement_scope": item["statement_scope"],
            "page_number": item["page_number"],
            "row_index": item["line_number"],
            "line_item_name_raw": line[:200],
            "source_cell_text": item["raw_line"],
            "mapping_status": "unmapped_manual_review",
        })
    return rows
