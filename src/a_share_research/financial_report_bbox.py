from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

from a_share_research.financial_reports import (
    UNIT_MULTIPLIERS,
    _derive_fact_period,
    _extract_numeric_tokens,
    _metric_rows,
    _quarantine_reasons,
    _resolve_metric_unit,
    _match_metric_alias,
    build_fact_id,
    detect_period_basis,
    detect_unit_scale,
    normalize_text,
    parse_decimal_value,
)

BBOX_PARSER_VERSION = "0.16.4"
XHTML_NS = {"h": "http://www.w3.org/1999/xhtml"}
HEADER_ROLE_MAP = {
    "本期发生额": "current",
    "本期金额": "current",
    "本年发生额": "current",
    "本年金额": "current",
    "本年数": "current",
    "期末余额": "current",
    "期末数": "current",
    "期末金额": "current",
    "年初至报告期期末金额": "current",
    "年末余额": "current",
    "年末数": "current",
    "本期期末": "current",
    "本期末": "current",
    "本期数": "current",
    "上期发生额": "comparative",
    "上期金额": "comparative",
    "上年发生额": "comparative",
    "上年金额": "comparative",
    "上年金额(经重述)": "comparative",
    "上年金额（经重述）": "comparative",
    "上年数": "comparative",
    "期初余额": "comparative",
    "期初数": "comparative",
    "年初余额": "comparative",
    "年初数": "comparative",
    "上期期末": "comparative",
    "上期末": "comparative",
    "上期数": "comparative",
    "上年同期金额": "comparative",
    "上年年末余额": "comparative",
    "上年末余额": "comparative",
    "告期期末金额": "comparative",
    "上年年初至报告期期末金额": "comparative",
    "上年年初至报告期期末": "comparative",
}
STATEMENT_NOTE_END_PATTERN = re.compile('^(?:20\\d{2}(?:年(?:上半年度|上半年|半年度)?|年度))?会计报表注释$|财务报表附注|会计报表附注|重要会计政策及会计估计')
PERIOD_CONTEXT_PATTERN = re.compile(
    r"本报告期|年初(?:至|到)报告期(?:期)?\s*末|九个月期间|前三季度|"
    r"1\s*[-—–－至]\s*9\s*月|1\s*[-—–－至]\s*3\s*月|"
    r"单季度|本季度|本季金额|单季金额|本年累计|累计金额|累计数|"
    r"1\s*[-—–－至]\s*12\s*月|年度金额|本年度金额|全年金额"
)
DATE_HEADER_PATTERN = re.compile(
    r"^(?P<year>20\d{2})年(?:度)?(?:(?P<start_month>\d{1,2})月?[-—–－]"
    r"(?P<end_month>\d{1,2})月|(?P<month>\d{1,2})月"
    r"(?:(?P<day>\d{1,2})日)?)?(?:度)?$"
)
MONTH_DAY_HEADER_PATTERN = re.compile(r"^(?P<month>\d{1,2})月(?P<day>\d{1,2})日$")
MONTH_RANGE_HEADER_PATTERN = re.compile(
    r"^(?P<start_month>\d{1,2})月?[-—–－](?P<end_month>\d{1,2})月$"
)
Q3_PERIOD_HEADER_PATTERN = re.compile(r"^(?P<year>20\d{2})年(?:前三季度|前三季)$")
QUARTER_PERIOD_HEADER_PATTERN = re.compile(
    r"^(?P<year>20\d{2})年(?:第)?(?P<quarter>[一二三四1-4])季度$"
)
HALF_YEAR_PERIOD_HEADER_PATTERN = re.compile(
    r"^(?P<year>20\d{2})年(?:半年度|上半年)$"
)
QUARTER_MONTH_RANGES = {
    "一": (1, 3), "1": (1, 3),
    "二": (4, 6), "2": (4, 6),
    "三": (7, 9), "3": (7, 9),
    "四": (10, 12), "4": (10, 12),
}
HEADER_SCOPE_MAP = {
    "合并": "consolidated",
    "公司": "parent_only",
    "母公司": "parent_only",
    "本公司": "parent_only",
    "银行": "parent_only",
    "本集团": "consolidated",
    "本行": "parent_only",
}
HEADING_PREFIX_PATTERN = re.compile(
    r"^(?P<scope>合并及(?:公司|母公司|银行)|合并|母公司|本公司|公司|银行)?"
    r"(?P<period>本报告期|年初到报告期末|年初至报告期末)?"
    r"(?P<statement>资产负债表|利润表|现金流量表)$"
)
HEADING_STATEMENT_TYPES = {
    "资产负债表": "balance_sheet",
    "利润表": "income_statement",
    "现金流量表": "cash_flow",
}


def _has_leading_report_date(line_text: str) -> bool:
    text = "".join((line_text or "").split())
    text = re.sub(
        r"^(?:(?:\d+|[一二三四五六七八九十]+)[、.．)]|"
        r"[（(](?:\d+|[一二三四五六七八九十]+)[）)])",
        "",
        text,
    )
    return bool(re.match(r"^20\d{2}年", text))


def _is_duplicate_date_prefixed_heading(
    previous_text: str,
    current_text: str,
    previous_heading: tuple[str, str] | None,
    current_heading: tuple[str, str],
    line_gap: int,
) -> bool:
    return (
        previous_heading is not None
        and previous_heading == current_heading
        and 0 < line_gap <= 3
        and _has_leading_report_date(previous_text)
        != _has_leading_report_date(current_text)
    )


def _parse_statement_heading(line_text: str) -> tuple[str, str] | None:
    text = "".join((line_text or "").split())
    text = re.sub(
        r"^(?:(?:\d+|[一二三四五六七八九十]+)[、.．)]|"
        r"[（(](?:\d+|[一二三四五六七八九十]+)[）)])",
        "",
        text,
    )
    text = re.sub(r"[（(](?:未经审计|经审计|1[-—–－]3月|1[-—–－]9月)[）)]$", "", text)
    # Some issuer statements prefix the exact heading with its balance date or
    # reporting period. Strip only these anchored forms; the remaining text
    # must still match a complete statement heading below.
    text = re.sub(
        r"^20\d{2}年(?:"
        r"1月1日至\d{1,2}月\d{1,2}日止(?:半年度|六个月期间|期间)|"
        r"\d{1,2}月\d{1,2}日|度)",
        "",
        text,
    )

    # A few bank reports use one heading for the consolidated and parent
    # statements. Column headers, not this combined title, determine fact scope.
    pair_match = re.fullmatch(
        r"(?:合并)?(?P<first>资产负债表|利润表|现金流量表)和"
        r"(?P<second>资产负债表|利润表|现金流量表)",
        text,
    )
    if pair_match and pair_match.group("first") == pair_match.group("second"):
        return HEADING_STATEMENT_TYPES[pair_match.group("first")], "unknown"

    match = HEADING_PREFIX_PATTERN.fullmatch(text)
    if not match:
        return None
    prefix = match.group("scope") or ""
    statement_type = HEADING_STATEMENT_TYPES[match.group("statement")]
    if prefix.startswith("合并及"):
        scope = "unknown"
    elif prefix == "合并":
        scope = "consolidated"
    elif prefix in {"母公司", "本公司", "公司", "银行"}:
        scope = "parent_only"
    else:
        scope = "unknown"
    return statement_type, scope


def _parse_xhtml_root(xhtml: str | bytes) -> ET.Element:
    if isinstance(xhtml, bytes):
        xhtml = xhtml.decode("utf-8", errors="replace")
    cleaned = re.sub(r"<!DOCTYPE[^>]*>", "", xhtml, count=1, flags=re.IGNORECASE | re.DOTALL)
    return ET.fromstring(cleaned)


def _page_lines(page: ET.Element, y_tolerance: float = 1.5) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for element in page.findall(".//h:word", XHTML_NS):
        text = "".join(element.itertext()).strip()
        if not text:
            continue
        try:
            x_min = float(element.attrib["xMin"])
            x_max = float(element.attrib["xMax"])
            y_min = float(element.attrib["yMin"])
            y_max = float(element.attrib["yMax"])
        except (KeyError, ValueError):
            continue
        words.append({
            "text": text,
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
        })

    words.sort(key=lambda item: (item["y_min"], item["x_min"]))
    groups: list[dict[str, Any]] = []
    for word in words:
        same_visual_line = False
        if groups:
            previous = groups[-1]
            overlap = max(
                0.0,
                min(word["y_max"], previous["y_max"])
                - max(word["y_min"], previous["y_min"]),
            )
            minimum_height = max(
                1.0,
                min(
                    word["y_max"] - word["y_min"],
                    previous["y_max"] - previous["y_min"],
                ),
            )
            overlap_ratio = overlap / minimum_height
            same_visual_line = (
                abs(word["y_min"] - previous["y_mean"]) <= y_tolerance
                or overlap_ratio >= 0.65
            )
        if same_visual_line:
            group = groups[-1]
            group["words"].append(word)
            group["y_mean"] = sum(item["y_min"] for item in group["words"]) / len(group["words"])
            group["y_min"] = min(group["y_min"], word["y_min"])
            group["y_max"] = max(group["y_max"], word["y_max"])
            group["x_min"] = min(group["x_min"], word["x_min"])
            group["x_max"] = max(group["x_max"], word["x_max"])
        else:
            groups.append({
                "words": [word],
                "y_mean": word["y_min"],
                "y_min": word["y_min"],
                "y_max": word["y_max"],
                "x_min": word["x_min"],
                "x_max": word["x_max"],
            })

    lines: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        ordered = sorted(group["words"], key=lambda item: item["x_min"])
        group["words"] = ordered
        group["line_text"] = "".join(item["text"] for item in ordered)
        group["line_number"] = index
        lines.append(group)
    return lines


class PreparedBBox:
    """Per-document page lines shared after the caller's strict XML validation.

    No cross-document cache or XML repair is performed. Legacy byte/string APIs
    keep their existing parsing behavior.
    """

    def __init__(self, root: ET.Element):
        self.pages = root.findall(".//h:page", XHTML_NS)
        self._heading_count: int | None = None

    def iter_page_lines(self):
        """Release each page's lines after consumption; retain only heading count."""
        heading_count = 0
        for page in self.pages:
            lines = _page_lines(page)
            previous_heading = None
            previous_heading_text = ""
            previous_heading_line_number = None
            for line in lines:
                heading = _parse_statement_heading(line["line_text"])
                if heading is None:
                    continue
                line_number = int(line["line_number"])
                duplicate = (
                    previous_heading_line_number is not None
                    and _is_duplicate_date_prefixed_heading(
                        previous_heading_text,
                        line["line_text"],
                        previous_heading,
                        heading,
                        line_number - previous_heading_line_number,
                    )
                )
                if not duplicate:
                    heading_count += 1
                previous_heading = heading
                previous_heading_text = line["line_text"]
                previous_heading_line_number = line_number
            yield lines
        # An interrupted/failed parse must never expose a partial count.
        self._heading_count = heading_count


def count_statement_headings(xhtml: str | bytes | PreparedBBox) -> int:
    prepared = xhtml if isinstance(xhtml, PreparedBBox) else PreparedBBox(_parse_xhtml_root(xhtml))
    if prepared._heading_count is None:
        for _ in prepared.iter_page_lines():
            pass
    return prepared._heading_count


YTD_COLUMN_LABELS = {
    "期末金额",
    "告期期末金额",
    "年初至报告期期末金额",
    "上年年初至报告期期末金额",
    "上年年初至报告期期末",
}


def _parse_date_header(text: str) -> dict[str, int] | None:
    normalized = "".join((text or "").split()).replace("－", "-").replace("—", "-").replace("–", "-")
    match = DATE_HEADER_PATTERN.fullmatch(normalized)
    if not match:
        return None
    result: dict[str, int] = {"year": int(match.group("year"))}
    for name in ("start_month", "end_month", "month", "day"):
        value = match.group(name)
        if value:
            result[name] = int(value)
    return result


def _date_header_role(
    date_label: str, report_period: str, statement_type: str
) -> str:
    parsed = _parse_date_header(date_label)
    try:
        report_date = date.fromisoformat(report_period[:10])
    except (ValueError, TypeError):
        return "unknown"
    if not parsed:
        return "unknown"
    year = parsed["year"]
    if statement_type == "balance_sheet":
        if "month" not in parsed or "day" not in parsed:
            return "unknown"
        try:
            header_date = date(year, parsed["month"], parsed["day"])
        except ValueError:
            return "unknown"
        if header_date == report_date:
            return "current"
        prior_year_end = date(report_date.year - 1, 12, 31)
        try:
            prior_year_same_day = report_date.replace(year=report_date.year - 1)
        except ValueError:
            prior_year_same_day = report_date.replace(year=report_date.year - 1, day=28)
        interim_year_opening = (
            date(report_date.year, 1, 1) if report_date.month < 12 else None
        )
        if header_date in {prior_year_end, prior_year_same_day, interim_year_opening}:
            return "comparative"
        return "unknown"
    if year == report_date.year:
        return "current"
    if year == report_date.year - 1:
        return "comparative"
    return "unknown"


def _paired_entity_scope_columns(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infer paired group/parent columns from matching issuer-name headers."""
    candidates = []
    legal_suffixes = ("股份有限公司", "有限责任公司", "有限公司", "股份公司")
    for word in words:
        if float(word["x_min"]) < 200:
            continue
        label = normalize_text(word["text"])
        if not label or re.search(r"\d", label):
            continue
        if label in HEADER_ROLE_MAP or label in HEADER_SCOPE_MAP or label in {"项目", "注释"}:
            continue
        base = label
        for suffix in legal_suffixes:
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break
        candidates.append((base, label, word))

    if len(candidates) != 2:
        return []
    group = [item for item in candidates if item[0].endswith("集团")]
    parent = [item for item in candidates if not item[0].endswith("集团")]
    if len(group) != 1 or len(parent) != 1 or group[0][0][:-2] != parent[0][0]:
        return []

    result = []
    for item, scope in ((group[0], "consolidated"), (parent[0], "parent_only")):
        word = item[2]
        result.append({
            "center": (float(word["x_min"]) + float(word["x_max"])) / 2,
            "role": "",
            "scope": scope,
            "label": item[1],
            "date_label": "",
            "date_year": None,
            "month_day": None,
            "month_range": None,
        })
    return result


def _header_columns(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []

    def add_column(
        x_min: float,
        x_max: float,
        label: str,
        role: str = "",
        scope: str = "",
        date_label: str = "",
        date_year: int | None = None,
        month_day: tuple[int, int] | None = None,
        month_range: tuple[int, int] | None = None,
    ) -> None:
        columns.append({
            "center": (x_min + x_max) / 2,
            "role": role,
            "scope": scope,
            "label": date_label or label,
            "date_label": date_label,
            "date_year": date_year,
            "month_day": month_day,
            "month_range": month_range,
        })

    ordered = sorted(words, key=lambda item: item["x_min"])
    for index, word in enumerate(ordered):
        text = "".join(word["text"].split())
        if word["x_min"] >= 200:
            role = HEADER_ROLE_MAP.get(text)
            scope = HEADER_SCOPE_MAP.get(text, "")
            date_info = _parse_date_header(text)
            complete_date = bool(
                date_info
                and (
                    ("month" in date_info and "day" in date_info)
                    or ("start_month" in date_info and "end_month" in date_info)
                )
            )
            month_day_match = MONTH_DAY_HEADER_PATTERN.fullmatch(text)
            month_range_match = MONTH_RANGE_HEADER_PATTERN.fullmatch(text)
            q3_period_match = Q3_PERIOD_HEADER_PATTERN.fullmatch(text)
            quarter_period_match = QUARTER_PERIOD_HEADER_PATTERN.fullmatch(text)
            half_year_period_match = HALF_YEAR_PERIOD_HEADER_PATTERN.fullmatch(text)
            if role:
                add_column(word["x_min"], word["x_max"], text, role=role)
            elif scope:
                add_column(word["x_min"], word["x_max"], text, scope=scope)
            elif q3_period_match:
                year = int(q3_period_match.group("year"))
                add_column(
                    word["x_min"], word["x_max"], text,
                    date_label=f"{year}年1-9月",
                    date_year=year,
                    month_range=(1, 9),
                )
            elif quarter_period_match:
                year = int(quarter_period_match.group("year"))
                start_month, end_month = QUARTER_MONTH_RANGES[
                    quarter_period_match.group("quarter")
                ]
                add_column(
                    word["x_min"], word["x_max"], text,
                    date_label=f"{year}年{start_month}-{end_month}月",
                    date_year=year,
                    month_range=(start_month, end_month),
                )
            elif half_year_period_match:
                year = int(half_year_period_match.group("year"))
                add_column(
                    word["x_min"], word["x_max"], text,
                    date_label=f"{year}年1-6月",
                    date_year=year,
                    month_range=(1, 6),
                )
            elif complete_date:
                add_column(word["x_min"], word["x_max"], text, date_label=text)
            elif date_info and set(date_info) == {"year"}:
                add_column(
                    word["x_min"], word["x_max"], text,
                    date_year=date_info["year"],
                )
            elif month_day_match:
                add_column(
                    word["x_min"], word["x_max"], text,
                    month_day=(
                        int(month_day_match.group("month")),
                        int(month_day_match.group("day")),
                    ),
                )
            elif month_range_match:
                add_column(
                    word["x_min"], word["x_max"], text,
                    month_range=(
                        int(month_range_match.group("start_month")),
                        int(month_range_match.group("end_month")),
                    ),
                )

        combined = text
        end_index = index
        for next_index in range(index + 1, min(len(ordered), index + 7)):
            previous = ordered[next_index - 1]
            current = ordered[next_index]
            if current["x_min"] - previous["x_max"] > 14:
                break
            combined += "".join(current["text"].split())
            end_index = next_index
            role = HEADER_ROLE_MAP.get(combined)
            date_info = _parse_date_header(combined)
            complete_date = bool(
                date_info
                and (
                    ("month" in date_info and "day" in date_info)
                    or ("start_month" in date_info and "end_month" in date_info)
                )
            )
            month_day_match = MONTH_DAY_HEADER_PATTERN.fullmatch(combined)
            month_range_match = MONTH_RANGE_HEADER_PATTERN.fullmatch(combined)
            q3_period_match = Q3_PERIOD_HEADER_PATTERN.fullmatch(combined)
            quarter_period_match = QUARTER_PERIOD_HEADER_PATTERN.fullmatch(combined)
            half_year_period_match = HALF_YEAR_PERIOD_HEADER_PATTERN.fullmatch(combined)
            if role or complete_date:
                add_column(
                    word["x_min"],
                    ordered[end_index]["x_max"],
                    combined,
                    role=role or "",
                    date_label=combined if complete_date else "",
                )
            elif q3_period_match:
                year = int(q3_period_match.group("year"))
                add_column(
                    word["x_min"],
                    ordered[end_index]["x_max"],
                    combined,
                    date_label=f"{year}年1-9月",
                    date_year=year,
                    month_range=(1, 9),
                )
            elif quarter_period_match:
                year = int(quarter_period_match.group("year"))
                start_month, end_month = QUARTER_MONTH_RANGES[
                    quarter_period_match.group("quarter")
                ]
                add_column(
                    word["x_min"], ordered[end_index]["x_max"], combined,
                    date_label=f"{year}年{start_month}-{end_month}月",
                    date_year=year,
                    month_range=(start_month, end_month),
                )
            elif half_year_period_match:
                year = int(half_year_period_match.group("year"))
                add_column(
                    word["x_min"], ordered[end_index]["x_max"], combined,
                    date_label=f"{year}年1-6月",
                    date_year=year,
                    month_range=(1, 6),
                )
            elif date_info and set(date_info) == {"year"}:
                add_column(
                    word["x_min"],
                    ordered[end_index]["x_max"],
                    combined,
                    date_year=date_info["year"],
                )
            elif month_day_match:
                add_column(
                    word["x_min"],
                    ordered[end_index]["x_max"],
                    combined,
                    month_day=(
                        int(month_day_match.group("month")),
                        int(month_day_match.group("day")),
                    ),
                )
            elif month_range_match:
                add_column(
                    word["x_min"],
                    ordered[end_index]["x_max"],
                    combined,
                    month_range=(
                        int(month_range_match.group("start_month")),
                        int(month_range_match.group("end_month")),
                    ),
                )
    # Some PDFs omit the Chinese date characters from the BBox word layer,
    # leaving only adjacent year/month/day number tokens. Reconstruct only
    # strict three-token date groups in the header area.
    for index, word in enumerate(ordered):
        year_text = "".join(word["text"].split())
        if word["x_min"] < 200 or not re.fullmatch(r"20\d{2}", year_text):
            continue
        group = [word]
        for next_index in range(index + 1, min(len(ordered), index + 3)):
            previous = group[-1]
            current = ordered[next_index]
            token = "".join(current["text"].split())
            if current["x_min"] - previous["x_max"] > 22 or not token.isdigit():
                break
            group.append(current)
        if len(group) == 3:
            try:
                year, month, day_value = (
                    int(year_text),
                    int("".join(group[1]["text"].split())),
                    int("".join(group[2]["text"].split())),
                )
                date(year, month, day_value)
            except ValueError:
                continue
            date_label = f"{year}年{month}月{day_value}日"
            add_column(
                group[0]["x_min"],
                group[-1]["x_max"],
                date_label,
                date_label=date_label,
            )

    columns.sort(key=lambda item: item["center"])
    return columns


def _merge_header_columns(
    existing: list[dict[str, Any]], detected: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = [dict(column) for column in existing]
    for column in detected:
        if column.get("scope"):
            scope_match = next(
                (
                    previous for previous in merged
                    if previous.get("scope") == column["scope"]
                    and abs(previous["center"] - column["center"]) <= 12
                ),
                None,
            )
            if scope_match is None:
                merged.append(dict(column))
            elif column.get("header_y") is not None:
                scope_match["header_y"] = column["header_y"]
            continue

        is_date_part = bool(
            column.get("date_year")
            or column.get("month_day")
            or column.get("month_range")
        )
        match = next(
            (
                previous for previous in merged
                if not previous.get("scope")
                and abs(previous["center"] - column["center"]) <= 40
                and (
                    is_date_part
                    or column.get("date_label")
                    or column.get("role")
                )
            ),
            None,
        )
        if match is None:
            merged.append(dict(column))
            continue

        if column.get("header_y") is not None:
            match["header_y"] = column["header_y"]
        if column.get("role"):
            match["role"] = column["role"]
            if not match.get("date_label"):
                match["label"] = column["label"]
        if column.get("date_label"):
            match["date_label"] = column["date_label"]
            match["label"] = column["date_label"]
        if column.get("date_year"):
            match["date_year"] = column["date_year"]
        if column.get("month_day"):
            match["month_day"] = column["month_day"]
        if column.get("month_range"):
            match["month_range"] = column["month_range"]
        if match.get("date_year") and match.get("month_day"):
            year = int(match["date_year"])
            month, day_value = match["month_day"]
            try:
                match["date_label"] = f"{year}年{month}月{day_value}日"
                match["label"] = match["date_label"]
            except ValueError:
                match["date_label"] = ""
                match["label"] = ""
        elif match.get("date_year") and match.get("month_range"):
            year = int(match["date_year"])
            start_month, end_month = match["month_range"]
            match["date_label"] = f"{year}年{start_month}-{end_month}月"
            match["label"] = match["date_label"]
    merged.sort(key=lambda item: item["center"])
    return merged


def _column_period_basis(
    column_label: str,
    header_columns: list[dict[str, Any]],
    statement_type: str,
    report_type: str,
    context: str,
    date_label: str = "",
) -> str:
    if statement_type == "balance_sheet":
        return "instant"
    date_info = _parse_date_header(date_label)
    if date_info:
        start_month = date_info.get("start_month")
        end_month = date_info.get("end_month")
        if start_month is not None and end_month is not None:
            if start_month == 1 and end_month == 12:
                return "annual"
            if end_month == start_month + 2:
                return "standalone_quarter"
            if start_month == 1:
                return "ytd"
    if column_label in YTD_COLUMN_LABELS:
        return "ytd"
    if report_type == "annual":
        return "annual"
    if report_type == "semiannual":
        return "ytd"
    if report_type == "q1":
        return "standalone_quarter"
    if report_type == "q3":
        short_period_labels = {"本期金额", "上期金额", "本期发生额", "上期发生额"}
        has_explicit_ytd_columns = any(
            column["label"] in YTD_COLUMN_LABELS for column in header_columns
        )
        if statement_type == "cash_flow" and column_label in short_period_labels:
            return "ytd"
        if (
            statement_type == "income_statement"
            and has_explicit_ytd_columns
            and column_label in short_period_labels
        ):
            return "standalone_quarter"
    return detect_period_basis(context, statement_type, report_type)


def _assign_column(
    word: dict[str, Any],
    header_columns: list[dict[str, Any]],
    ordinal: int,
    report_period: str,
    statement_type: str,
) -> tuple[int, str, str, str, str]:
    data_columns = [
        column for column in header_columns
        if (
            column.get("role")
            or column.get("date_label")
            or (column.get("date_year") and statement_type != "balance_sheet")
        )
    ]
    if not data_columns:
        data_columns = [
            column for column in header_columns if not column.get("scope")
        ]
    if not data_columns:
        return ordinal, "unknown", "", "", ""
    center = (word["x_min"] + word["x_max"]) / 2
    nearest_index, nearest = min(
        enumerate(data_columns, start=1),
        key=lambda pair: abs(pair[1]["center"] - center),
    )
    distance = abs(nearest["center"] - center)
    neighbor_gaps = [
        abs(nearest["center"] - column["center"])
        for column in data_columns
        if column is not nearest
    ]
    distance_limit = min(80.0, min(neighbor_gaps) / 2) if neighbor_gaps else 80.0
    if distance > distance_limit:
        return ordinal, "unknown", "", "", ""
    date_label = nearest.get("date_label", "")
    if not date_label and nearest.get("date_year"):
        date_label = f"{nearest['date_year']}年"
    role = nearest.get("role") or _date_header_role(
        date_label, report_period, statement_type
    )
    scope_columns = [column for column in header_columns if column.get("scope")]
    if scope_columns:
        nearest_scope = min(
            scope_columns,
            key=lambda column: abs(column["center"] - center),
        )
        column_scope = nearest_scope["scope"]
    else:
        column_scope = nearest.get("scope", "")
    return (
        nearest_index,
        role or "unknown",
        nearest.get("label", ""),
        column_scope,
        date_label,
    )


def _is_note_column_word(
    word: dict[str, Any],
    note_column_centers: list[float],
) -> bool:
    center = (word["x_min"] + word["x_max"]) / 2
    return any(abs(center - note_center) <= 45 for note_center in note_column_centers)


def _left_label_fragment(
    line: dict[str, Any],
    value_x_min: float,
    note_column_centers: list[float],
) -> str:
    return "".join(
        word["text"]
        for word in line["words"]
        if word["x_min"] < value_x_min
        and not _is_note_column_word(word, note_column_centers)
    )


def _has_numeric_value_column(
    line: dict[str, Any],
    value_x_min: float,
    note_column_centers: list[float],
) -> bool:
    return any(
        word["x_min"] >= value_x_min
        and not _is_note_column_word(word, note_column_centers)
        and _extract_numeric_tokens(word["text"])
        for word in line["words"]
    )


def _is_note_only_line(
    line: dict[str, Any],
    note_column_centers: list[float],
) -> bool:
    words = line["words"]
    return bool(words) and bool(note_column_centers) and all(
        _is_note_column_word(word, note_column_centers) for word in words
    )


def parse_bbox_xhtml(
    xhtml: str | bytes | PreparedBBox,
    document: dict[str, Any],
    metric_dictionary=None,
) -> list[dict[str, Any]]:
    prepared = xhtml if isinstance(xhtml, PreparedBBox) else PreparedBBox(_parse_xhtml_root(xhtml))
    metrics = _metric_rows(metric_dictionary)
    announcement_id = normalize_text(document.get("announcement_id"))
    pdf_sha256 = normalize_text(document.get("pdf_sha256")).lower()
    document_version_id = normalize_text(document.get("document_version_id"))
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

    active_statement_type = ""
    active_scope = "unknown"
    active_table_index = 0
    active_combined_scope_heading = False
    active_header_columns: list[dict[str, Any]] = []
    active_note_column_centers: list[float] = []
    active_unit_scale = "unknown"
    active_period_context: list[str] = []
    facts: list[dict[str, Any]] = []
    last_heading: tuple[str, str] | None = None
    last_heading_text = ""
    last_heading_page: int | None = None
    last_heading_line_number: int | None = None
    last_heading_fact_count: int | None = None

    for page_number, lines in enumerate(prepared.iter_page_lines(), start=1):
        page_text = "\n".join(line["line_text"] for line in lines)
        page_unit_scale = detect_unit_scale(page_text)
        if page_unit_scale != "unknown" and active_statement_type:
            active_unit_scale = page_unit_scale

        recent_context: list[str] = []
        pending_metric_label = ""
        pending_metric_label_y: float | None = None
        for line_index, line in enumerate(lines):
            line_text = line["line_text"]
            if STATEMENT_NOTE_END_PATTERN.search(line_text):
                active_statement_type = ""
                active_scope = "unknown"
                active_header_columns = []
                active_combined_scope_heading = False
                active_note_column_centers = []
                active_unit_scale = "unknown"
                active_period_context = []
                recent_context = []
                pending_metric_label = ""
                pending_metric_label_y = None
                last_heading = None
                last_heading_text = ""
                last_heading_page = None
                last_heading_line_number = None
                last_heading_fact_count = None
                continue
            heading = _parse_statement_heading(line_text)
            if heading:
                line_number = int(line["line_number"])
                duplicate_heading = (
                    last_heading_page == page_number
                    and last_heading_line_number is not None
                    and len(facts) == last_heading_fact_count
                    and _is_duplicate_date_prefixed_heading(
                        last_heading_text,
                        line_text,
                        last_heading,
                        heading,
                        line_number - last_heading_line_number,
                    )
                )
                if not duplicate_heading:
                    active_table_index += 1
                active_statement_type, active_scope = heading
                normalized_heading = normalize_text(line_text)
                active_combined_scope_heading = bool(
                    re.search(
                        r"合并及(?:公司|母公司|银行)|合并(?:资产负债表|利润表|现金流量表)和",
                        normalized_heading,
                    )
                )
                last_heading = heading
                last_heading_text = line_text
                last_heading_page = page_number
                last_heading_line_number = line_number
                last_heading_fact_count = len(facts)
                active_header_columns = []
                active_note_column_centers = []
                active_unit_scale = page_unit_scale
                active_period_context = [line_text]
                recent_context = [line_text]
                pending_metric_label = ""
                pending_metric_label_y = None
                continue

            if not active_statement_type:
                continue

            if PERIOD_CONTEXT_PATTERN.search(line_text):
                active_period_context.append(line_text)
                active_period_context = active_period_context[-8:]

            detected_headers = _header_columns(line["words"])
            if active_combined_scope_heading:
                detected_headers.extend(_paired_entity_scope_columns(line["words"]))
            for detected_header in detected_headers:
                detected_header["header_y"] = float(line["y_min"])
            note_centers = [
                (word["x_min"] + word["x_max"]) / 2
                for word in line["words"]
                if (
                    "".join(word["text"].split()).startswith("附注")
                    or "".join(word["text"].split()) in {"附注号", "注释"}
                )
            ]
            if note_centers:
                active_note_column_centers = note_centers
            if detected_headers:
                pending_metric_label = ""
                pending_metric_label_y = None
                detected_data_headers = [
                    column for column in detected_headers
                    if (
                        column.get("role")
                        or column.get("date_label")
                        or column.get("date_year")
                        or column.get("month_day")
                        or column.get("month_range")
                    )
                ]
                if len(detected_data_headers) >= 2:
                    detected_centers = [
                        float(column["center"]) for column in detected_data_headers
                    ]
                    header_left = min(detected_centers) - 40
                    header_right = max(detected_centers) + 40
                    current_header_y = float(line["y_min"])
                    active_header_columns = [
                        column for column in active_header_columns
                        if column.get("scope")
                        or (
                            header_left <= float(column["center"]) <= header_right
                            and (
                                column.get("header_y") is None
                                or abs(
                                    current_header_y - float(column["header_y"])
                                ) <= 36
                            )
                        )
                    ]
                active_header_columns = _merge_header_columns(
                    active_header_columns, detected_headers
                )
                recent_context.append(line_text)
                recent_context = recent_context[-8:]
                continue

            if page_unit_scale != "unknown":
                active_unit_scale = page_unit_scale

            value_x_min = (
                max(150.0, min(column["center"] for column in active_header_columns) - 85.0)
                if active_header_columns else 300.0
            )
            label_text = "".join(
                word["text"] for word in line["words"]
                if word["x_min"] < value_x_min
            )

            numeric_words: list[dict[str, Any]] = []
            for word in line["words"]:
                if word["x_min"] < value_x_min:
                    continue
                word_center = (word["x_min"] + word["x_max"]) / 2
                if any(abs(word_center - center) <= 45 for center in active_note_column_centers):
                    continue
                tokens = _extract_numeric_tokens(word["text"])
                if not tokens:
                    continue
                for token in tokens:
                    numeric_words.append({**word, "value_raw": token})
            numeric_words.sort(key=lambda item: item["x_min"])

            # A metric label may wrap after the numeric row. A single
            # note-reference-only line may intervene between the row and suffix.
            wrapped_metric_label = ""
            wrapped_metric_source_text = ""
            if numeric_words and label_text:
                for offset in (1, 2):
                    follower_index = line_index + offset
                    if follower_index >= len(lines):
                        break
                    follower = lines[follower_index]
                    dy = float(follower["y_min"]) - float(line["y_min"])
                    if not 0 < dy <= 18:
                        break
                    if (
                        STATEMENT_NOTE_END_PATTERN.search(follower["line_text"])
                        or _parse_statement_heading(follower["line_text"])
                        or _header_columns(follower["words"])
                    ):
                        break

                    suffix = _left_label_fragment(
                        follower, value_x_min, active_note_column_centers
                    )
                    if suffix:
                        has_follower_values = _has_numeric_value_column(
                            follower, value_x_min, active_note_column_centers
                        )
                        joined_label = label_text + suffix
                        for metric in metrics:
                            if metric["statement_type"] != active_statement_type:
                                continue
                            alias, position = _match_metric_alias(
                                joined_label,
                                metric["label_aliases"],
                                allow_qualifier=True,
                            )
                            if not alias:
                                continue
                            if offset == 2 and normalize_text(
                                joined_label[position + len(alias):]
                            ):
                                continue
                            if not has_follower_values:
                                wrapped_metric_label = joined_label
                                wrapped_metric_source_text = (
                                    f"{joined_label} {line_text}".strip()
                                )
                                break
                        break

                    if _is_note_only_line(follower, active_note_column_centers):
                        continue
                    break

            # Some BBox layouts split a metric label into a prefix, a numeric
            # line, and a trailing suffix. Reconstruct only an exact dictionary
            # alias, with empty adjacent value columns and tight vertical gaps.
            if (
                not wrapped_metric_label
                and numeric_words
                and 0 < line_index < len(lines) - 1
            ):
                previous = lines[line_index - 1]
                follower = lines[line_index + 1]
                previous_label = _left_label_fragment(
                    previous, value_x_min, active_note_column_centers
                )
                middle_label = _left_label_fragment(
                    line, value_x_min, active_note_column_centers
                )
                suffix = _left_label_fragment(
                    follower, value_x_min, active_note_column_centers
                )
                previous_gap = float(line["y_min"]) - float(previous["y_min"])
                follower_gap = float(follower["y_min"]) - float(line["y_min"])

                previous_has_values = _has_numeric_value_column(
                    previous, value_x_min, active_note_column_centers
                )
                follower_has_values = _has_numeric_value_column(
                    follower, value_x_min, active_note_column_centers
                )
                adjacent_lines_are_fragments = (
                    previous_label
                    and suffix
                    and 0 < previous_gap <= 18
                    and 0 < follower_gap <= 18
                    and not previous_has_values
                    and not follower_has_values
                    and not STATEMENT_NOTE_END_PATTERN.search(previous["line_text"])
                    and not STATEMENT_NOTE_END_PATTERN.search(follower["line_text"])
                    and not _parse_statement_heading(previous["line_text"])
                    and not _parse_statement_heading(follower["line_text"])
                    and not _header_columns(previous["words"])
                    and not _header_columns(follower["words"])
                )
                if adjacent_lines_are_fragments:
                    joined_label = previous_label + middle_label + suffix
                    exact_metric_matches = []
                    for metric in metrics:
                        if metric["statement_type"] != active_statement_type:
                            continue
                        alias, position = _match_metric_alias(
                            joined_label,
                            metric["label_aliases"],
                            allow_qualifier=True,
                        )
                        if (
                            alias
                            and not normalize_text(joined_label[position + len(alias):])
                        ):
                            exact_metric_matches.append(metric)
                    unique_matches = {
                        metric["metric_id"]: metric for metric in exact_metric_matches
                    }
                    if len(unique_matches) == 1:
                        wrapped_metric_label = joined_label
                        wrapped_metric_source_text = f"{joined_label} {line_text}".strip()

            if not numeric_words:
                is_metric_label = bool(label_text) and any(
                    metric["statement_type"] == active_statement_type
                    and _match_metric_alias(
                        label_text, metric["label_aliases"], allow_qualifier=True
                    )[0]
                    for metric in metrics
                )
                if is_metric_label:
                    current_y = float(line["y_min"])
                    if (
                        pending_metric_label
                        and pending_metric_label_y is not None
                        and abs(current_y - pending_metric_label_y) <= 18
                    ):
                        pending_metric_label += label_text
                    else:
                        pending_metric_label = label_text
                    pending_metric_label_y = current_y
                else:
                    pending_metric_label = ""
                    pending_metric_label_y = None
                recent_context.append(line_text)
                recent_context = recent_context[-8:]
                continue

            effective_label_text = wrapped_metric_label or label_text
            current_y = float(line["y_min"])
            if (
                not effective_label_text
                and pending_metric_label
                and pending_metric_label_y is not None
                and abs(current_y - pending_metric_label_y) <= 18
            ):
                effective_label_text = pending_metric_label
            pending_metric_label = ""
            pending_metric_label_y = None
            if not effective_label_text:
                recent_context.append(line_text)
                recent_context = recent_context[-8:]
                continue
            source_evidence_text = (
                wrapped_metric_source_text
                or (
                    f"{wrapped_metric_label} {line_text}".strip()
                    if wrapped_metric_label else (
                        line_text if label_text else f"{effective_label_text} {line_text}".strip()
                    )
                )
            )

            if numeric_words:
                for metric in metrics:
                    if metric["statement_type"] != active_statement_type:
                        continue
                    matched_alias, label_position = _match_metric_alias(
                        effective_label_text, metric["label_aliases"], allow_qualifier=True
                    )
                    if not matched_alias:
                        continue

                    metric_unit, unit_compatible = _resolve_metric_unit(
                        metric, active_unit_scale, line_text
                    )
                    context = "\n".join(active_period_context[-8:] + recent_context[-7:] + [line_text])
                    for ordinal, value_word in enumerate(numeric_words, start=1):
                        raw_value = value_word["value_raw"]
                        value_decimal = parse_decimal_value(raw_value, metric_unit)
                        (
                            column_index,
                            column_role,
                            column_label,
                            column_scope,
                            column_date_label,
                        ) = _assign_column(
                            value_word,
                            active_header_columns,
                            ordinal,
                            report_period,
                            metric["statement_type"],
                        )
                        period_basis = _column_period_basis(
                            column_label,
                            active_header_columns,
                            metric["statement_type"],
                            report_type,
                            context,
                            column_date_label,
                        )
                        # Ending cash and cash equivalents is a point-in-time
                        # balance even though the cash-flow statement labels
                        # its current/comparative columns as 本期发生额/上期发生额.
                        if metric["metric_id"] == "ending_cash_equivalents":
                            period_basis = "instant"
                        period_start, period_end = _derive_fact_period(
                            report_period, period_basis, column_role
                        )
                        date_info = _parse_date_header(column_date_label)
                        if (
                            metric["statement_type"] == "balance_sheet"
                            and date_info
                            and "month" in date_info
                            and "day" in date_info
                        ):
                            exact_date = date(
                                date_info["year"], date_info["month"], date_info["day"]
                            ).isoformat()
                            period_start = exact_date
                            period_end = exact_date
                        fact_scope = column_scope or active_scope
                        reasons = _quarantine_reasons(
                            document,
                            report_period,
                            fact_scope,
                            metric_unit,
                            period_basis,
                            column_role,
                            unit_compatible,
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
                            document_version_id or f"{announcement_id}:{pdf_sha256}",
                            fact_scope,
                            metric["statement_type"],
                            page_number,
                            active_table_index,
                            line["line_number"],
                            metric["metric_id"],
                            ordinal,
                        )
                        multiplier = UNIT_MULTIPLIERS.get(metric_unit)
                        metric_currency = normalize_text(metric.get("currency"))
                        if not metric_currency and metric_unit in {
                            "元", "人民币元", "千元", "万元", "百万元", "亿元", "元/股"
                        }:
                            metric_currency = "CNY"

                        facts.append({
                            "fact_id": fact_id,
                            "document_version_id": document_version_id,
                            "announcement_id": announcement_id,
                            "canonical_security_id": normalize_text(document.get("canonical_security_id")),
                            "source_symbol": normalize_text(document.get("source_symbol")),
                            "document_report_period": report_period,
                            "fact_period_start": period_start,
                            "fact_period_end": period_end,
                            "statement_type": metric["statement_type"],
                            "statement_scope": fact_scope,
                            "table_index": active_table_index,
                            "page_number": page_number,
                            "row_index": line["line_number"],
                            "column_index": column_index,
                            "column_label": column_label,
                            "column_role": column_role,
                            "period_basis": period_basis,
                            "metric_id": metric["metric_id"],
                            "line_item_code": "",
                            "line_item_name_raw": matched_alias,
                            "value_raw": raw_value,
                            "value_decimal": str(value_decimal) if value_decimal is not None else "",
                            "currency": metric_currency,
                            "unit": metric_unit,
                            "scale": str(multiplier) if multiplier is not None else "",
                            "sign_convention": "negative_parentheses_or_sign",
                            "source_cell_text": source_evidence_text,
                            "source_x_min": round(value_word["x_min"], 3),
                            "source_x_max": round(value_word["x_max"], 3),
                            "source_y_min": round(line["y_min"], 3),
                            "extractor_name": "Poppler pdftotext -bbox-layout",
                            "extractor_version": normalize_text(document.get("extractor_version")),
                            "parser_version": BBOX_PARSER_VERSION,
                            "validation_status": "quarantined",
                            "quarantine_reason": "|".join(dict.fromkeys(reasons)),
                        })

            recent_context.append(line_text)
            recent_context = recent_context[-8:]

    return facts
