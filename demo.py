"""Run the Prestock parser and quality policy on synthetic BBox examples."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))

from a_share_research.financial_report_bbox import count_statement_headings, parse_bbox_xhtml
from a_share_research.cninfo_pipeline.quality import QualityPolicy
import pandas as pd

CASES = ('complete', 'missing_anchor', 'heading_gap')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run(output):
    dictionary_path = ROOT / 'data/metadata/financial_report_metric_dictionary.csv'
    dictionary = pd.read_csv(dictionary_path, dtype=str).fillna('')
    policy = QualityPolicy(dictionary_path)
    summary = {'sample_kind': 'synthetic_bbox_fixture', 'cases': []}
    output.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        sample = ROOT / 'samples' / f'{case}.xhtml'
        blob = sample.read_bytes()
        digest = hashlib.sha256(blob).hexdigest()
        document = {
            'announcement_id': 'synthetic-' + case,
            'document_version_id': 'synthetic-' + digest,
            'canonical_security_id': 'DEMO',
            'identity_status': 'synthetic_fixture',
            'pdf_sha256': digest,
            'report_period_candidate': '2025-12-31',
            'report_type': 'annual',
            'category_key': 'annual_report',
            'extractor_version': 'synthetic_bbox_fixture',
        }
        facts = parse_bbox_xhtml(blob, document, dictionary)
        for fact in facts:
            fact.update(source_pdf_sha256=digest, source_input_sha256=digest,
                        source_input=sample.name, data_origin='synthetic_bbox_fixture',
                        gold_match_status='not_reviewed', validation_status='quarantined',
                        quarantine_reason='synthetic_demonstration')
        quality = policy.classify(
            facts, announcement_id=document['announcement_id'], source_sha256=digest,
            security_id='DEMO', report_period='2025-12-31', category='annual_report',
            statement_heading_count=count_statement_headings(blob),
        )
        folder = output / case
        folder.mkdir(exist_ok=True)
        write_json(folder / 'facts.json', facts)
        write_json(folder / 'quality.json', quality)
        summary['cases'].append({
            'case': case, 'quality_status': quality['quality_status'],
            'candidate_fact_count': len(facts),
            'current_metric_count': len(quality['current_consolidated_metric_ids']),
            'reasons': quality['rejection_reasons'], 'source_input_sha256': digest,
        })
        print(f"{case}: {quality['quality_status']}, facts={len(facts)}, "
              f"current_metrics={len(quality['current_consolidated_metric_ids'])}")
    write_json(output / 'summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'demo-output')
    args = parser.parse_args()
    run(args.output.resolve())
