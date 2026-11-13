import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='prestock-showcase-')
        cls.output = Path(cls.temp.name) / 'results'
        cls.completed = subprocess.run(
            [sys.executable, str(ROOT / 'demo.py'), '--output', str(cls.output)],
            cwd=cls.temp.name, capture_output=True, text=True, encoding='utf-8',
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def load(self, case, kind):
        self.assertEqual(self.completed.returncode, 0, self.completed.stdout + self.completed.stderr)
        return json.loads((self.output / case / f'{kind}.json').read_text(encoding='utf-8'))

    def test_complete_case_preserves_values_periods_and_source(self):
        quality = self.load('complete', 'quality')
        self.assertEqual(quality['quality_status'], 'complete')
        self.assertEqual(len(quality['current_consolidated_metric_ids']), 23)
        facts = self.load('complete', 'facts')
        revenue = [f for f in facts if f['metric_id'] == 'revenue']
        self.assertEqual(len(revenue), 2)
        self.assertEqual([f['value_decimal'] for f in revenue], ['1000', '900'])
        self.assertEqual([f['column_role'] for f in revenue], ['current', 'comparative'])
        self.assertEqual([f['fact_period_end'] for f in revenue], ['2025-12-31', '2024-12-31'])
        self.assertTrue(all(f['statement_scope'] == 'consolidated' for f in revenue))
        digest = hashlib.sha256((ROOT / 'samples/complete.xhtml').read_bytes()).hexdigest()
        self.assertTrue(all(f['source_input_sha256'] == digest for f in facts))
        self.assertTrue(all(f['page_number'] > 0 and f['source_cell_text'] for f in facts))

    def test_missing_anchor_is_identified_despite_sufficient_metric_count(self):
        quality = self.load('missing_anchor', 'quality')
        self.assertEqual(quality['quality_status'], 'invalid')
        self.assertEqual(len(quality['current_consolidated_metric_ids']), 22)
        self.assertEqual(quality['rejection_reasons'], ['mandatory_three_statement_anchors_missing'])
        self.assertIn('operating_cash_flow', quality['missing_metric_ids'])

    def test_unsupported_heading_has_zero_facts(self):
        quality = self.load('heading_gap', 'quality')
        self.assertEqual(quality['quality_status'], 'invalid')
        self.assertEqual(quality['candidate_fact_count'], 0)
        self.assertEqual(quality['rejection_reasons'], ['no_candidate_facts'])

    def test_summary_and_fact_identities(self):
        self.assertEqual(self.completed.returncode, 0, self.completed.stdout + self.completed.stderr)
        summary = json.loads((self.output / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(len(summary['cases']), 3)
        for case in ('complete', 'missing_anchor', 'heading_gap'):
            facts = self.load(case, 'facts')
            self.assertEqual(len(facts), len({f['fact_id'] for f in facts}))
            self.assertTrue(all(f['data_origin'] == 'synthetic_bbox_fixture' for f in facts))


if __name__ == '__main__':
    unittest.main()

