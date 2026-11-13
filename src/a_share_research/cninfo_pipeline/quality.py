"""Report coverage policy, independent of candidate fact verification status."""
import csv
import hashlib
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from ..financial_reports import UNIT_MULTIPLIERS

MIN_METRICS = {'annual_report': 20, 'semiannual_report': 17, 'q1_report': 14, 'q3_report': 14}
ANCHORS = ({'revenue', 'total_operating_revenue'}, {'total_assets'}, {'operating_cash_flow'})
DEFAULT_DICTIONARY = Path(__file__).resolve().parents[3] / 'data/metadata/financial_report_metric_dictionary.csv'


class QualityPolicy:
    def __init__(self, dictionary=DEFAULT_DICTIONARY):
        blob = Path(dictionary).read_bytes()
        rows = list(csv.DictReader(blob.decode('utf-8-sig').splitlines()))
        self.definitions = {row['metric_id']: row for row in rows}
        if len(rows) != 23 or len(self.definitions) != 23:
            raise ValueError('expected exactly 23 unique core metrics')
        self.rule_version = 'cninfo-quality-1:' + hashlib.sha256(blob).hexdigest()

    def classify(self, facts, *, announcement_id, source_sha256, security_id, report_period,
                 category, statement_heading_count):
        if category not in MIN_METRICS:
            raise ValueError('unknown report category')
        date.fromisoformat(report_period)
        ids, current, missing_fields = set(), set(), []
        for fact in facts:
            fid = fact.get('fact_id')
            if not isinstance(fid, str) or not re.fullmatch('[0-9a-f]{64}', fid) or fid in ids:
                raise ValueError('missing or duplicate fact identity')
            ids.add(fid)
            for field, expected in [('announcement_id', announcement_id), ('source_pdf_sha256', source_sha256),
                                    ('canonical_security_id', security_id), ('document_report_period', report_period)]:
                if fact.get(field) != expected:
                    raise ValueError('fact source identity conflict: ' + field)
            if (fact.get('validation_status') != 'quarantined' or fact.get('gold_match_status') != 'not_reviewed'
                    or not fact.get('quarantine_reason') or fact.get('PIT_ready', False) is not False
                    or fact.get('pit_ready', False) is not False):
                raise ValueError('candidate verification state conflict')
            metric = fact.get('metric_id')
            if metric not in self.definitions:
                raise ValueError('unknown metric identity')
            if fact.get('statement_type') != self.definitions[metric]['statement_type']:
                raise ValueError('metric statement identity conflict')
            for field in ('statement_scope', 'column_role', 'period_basis', 'unit', 'currency', 'value_decimal'):
                if not isinstance(fact.get(field), str):
                    raise ValueError('invalid fact field schema: ' + field)
                if fact[field] in ('', 'unknown'):
                    missing_fields.append(fid + '.' + field)
            if fact['value_decimal']:
                try:
                    if not Decimal(fact['value_decimal']).is_finite():
                        raise ValueError('nonfinite fact number')
                except InvalidOperation as error:
                    raise ValueError('invalid normalized fact number') from error
            for field, allowed in [('statement_scope', {'', 'unknown', 'consolidated', 'parent_only'}),
                                   ('column_role', {'', 'unknown', 'current', 'comparative'}),
                                   ('period_basis', {'', 'unknown', 'instant', 'annual', 'ytd', 'standalone_quarter'})]:
                if fact[field] not in allowed:
                    raise ValueError('noncanonical fact field: ' + field)
            if fact['unit'] not in ('', 'unknown') and fact['unit'] not in UNIT_MULTIPLIERS:
                raise ValueError('noncanonical fact unit')
            currency = self.definitions[metric]['currency']
            if fact['currency'] not in ('', 'unknown') and currency and fact['currency'] != currency:
                raise ValueError('fact currency conflicts with metric dictionary')
            for field in ('fact_period_start', 'fact_period_end'):
                if fact.get(field):
                    date.fromisoformat(fact[field])
            if fact.get('fact_period_start') and fact.get('fact_period_end') and fact['fact_period_start'] > fact['fact_period_end']:
                raise ValueError('reversed fact period')
            if fact['statement_scope'] == 'consolidated' and fact['column_role'] == 'current':
                current.add(metric)
        missing = sorted(set(self.definitions) - current)
        reasons = []
        if not facts:
            reasons.append('no_candidate_facts')
        else:
            if len(current) < MIN_METRICS[category]:
                reasons.append('report_type_metric_coverage_insufficient')
            if not all(current & group for group in ANCHORS):
                reasons.append('mandatory_three_statement_anchors_missing')
            if statement_heading_count < 1:
                reasons.append('statement_headings_missing')
        status = 'invalid' if reasons else 'incomplete' if missing or missing_fields else 'complete'
        return {'quality_status': status, 'missing_metric_ids': missing, 'missing_fields': sorted(missing_fields),
                'quality_rule_version': self.rule_version, 'rejection_reasons': reasons,
                'candidate_fact_count': len(facts), 'current_consolidated_metric_ids': sorted(current),
                'required_metric_count': 23, 'pit_ready': False}
