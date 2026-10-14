"""No-network tests for the optional LLM selector and critic gates."""
import io
import json
import os
import unittest
from unittest.mock import patch

from agent_reviewer import eligible_formats, review_formats, validate_choice, _safe_endpoint
from engine import run_research, venue_assessment


class FakeResponse:
    def __init__(self, content):
        self._raw = json.dumps({'choices': [{'message': {'content': content}}]}).encode()
        self.headers = {'Content-Length': str(len(self._raw))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=-1):
        return self._raw[:n]


class ReviewerTests(unittest.TestCase):
    def setUp(self):
        self.anchor = {'name': 'Nils Frahm', 'entity_id': 'a1', 'source': 'Qloo /search', 'type': 'artist'}
        self.branches = {
            kind: [{'name': name, 'entity_id': kind + str(idx), 'source': 'Qloo /v2/insights',
                    'type': kind, **({'venue_review': venue_assessment(name)} if kind == 'place' else {})}
                   for idx, name in enumerate(items)]
            for kind, items in {
                'movie': ['Phantom Thread', 'The Shape of Water', 'Roma'],
                'brand': ['Sonos', 'Devialet', 'Bang & Olufsen'],
                'place': ['El Rastro', 'Museo Nacional del Prado', 'Círculo de Bellas Artes', 'Goethe-Institut Madrid'],
            }.items()
        }
        self.env = {'ATLAS_LLM_URL': 'https://model.example/v1/chat/completions',
                    'ATLAS_LLM_MODEL': 'test-model', 'ATLAS_LLM_API_KEY': 'test-llm-secret'}

    def test_no_model_configured_no_request(self):
        with patch.dict(os.environ, {'ATLAS_LLM_URL': '', 'ATLAS_LLM_MODEL': ''}), \
             patch('agent_reviewer.urllib.request.urlopen') as opener:
            selection, status = review_formats(self.anchor, self.branches, 'Madrid', 'educational workshop')
            self.assertIsNone(selection)
            self.assertEqual(status, 'not_configured')
            opener.assert_not_called()

    def test_valid_format_choice(self):
        result = '{"formats":["workshop","exhibition","salon"]}'
        with patch.dict(os.environ, self.env), \
             patch('agent_reviewer.urllib.request.urlopen', return_value=FakeResponse(result)) as opener:
            selected, status = review_formats(self.anchor, self.branches, 'Madrid', 'educational workshop')
            self.assertEqual(selected, ['workshop', 'exhibition', 'salon'])
            self.assertEqual(status, 'validated')
            req = opener.call_args.args[0]
            serialized = req.data.decode()
            self.assertNotIn('test-llm-secret', serialized)
            self.assertNotIn('hack_', serialized)
            self.assertEqual(req.headers['Authorization'], 'Bearer test-llm-secret')
            self.assertIn('Phantom Thread', serialized)

    def test_model_cannot_invent_format(self):
        with patch.dict(os.environ, self.env), \
             patch('agent_reviewer.urllib.request.urlopen', return_value=FakeResponse('{"formats":["workshop","pop-up-spaceship","salon"]}')):
            chosen, status = review_formats(self.anchor, self.branches, 'Madrid', 'educational workshop')
            self.assertIsNone(chosen)
            self.assertEqual(status, 'choice_rejected_by_critic')

    def test_model_cannot_duplicate_or_return_two(self):
        allowed = eligible_formats(self.branches)
        self.assertIsNone(validate_choice({'formats': ['workshop', 'workshop', 'salon']}, allowed))
        self.assertIsNone(validate_choice({'formats': ['workshop', 'salon']}, allowed))
        self.assertIsNone(validate_choice({'formats': ['workshop', 'salon', 'dance']}, allowed))
        self.assertEqual(validate_choice({'formats': ['workshop', 'salon', 'exhibition']}, allowed),
                         ['workshop', 'salon', 'exhibition'])

    def test_ai_review_cannot_lead_with_off_goal_format(self):
        elig = eligible_formats(self.branches)
        self.assertIsNone(validate_choice({'formats': ['exhibition', 'salon', 'screening']},
                                          elig, 'film screening programme'))
        self.assertEqual(validate_choice({'formats': ['screening', 'salon', 'exhibition']},
                                         elig, 'film screening programme'),
                         ['screening', 'salon', 'exhibition'])

    def test_missing_movie_cannot_select_cinema(self):
        no_movie = {**self.branches, 'movie': []}
        self.assertNotIn('screening', eligible_formats(no_movie))
        self.assertNotIn('workshop', eligible_formats(no_movie))
        self.assertNotIn('salon', eligible_formats(no_movie))
        self.assertEqual(eligible_formats(no_movie), ['listening', 'exhibition'])
        with patch.dict(os.environ, self.env), \
             patch('agent_reviewer.urllib.request.urlopen') as opener:
            self.assertEqual(review_formats(self.anchor, no_movie, 'Madrid', 'cinema'),
                             (None, 'insufficient_evidence'))
            opener.assert_not_called()

    def test_public_spaces_alone_are_ineligible(self):
        only_public = {**self.branches, 'place': [self.branches['place'][0]]}
        self.assertEqual(eligible_formats(only_public), [])

    def test_reject_unsafe_url(self):
        for url in ('http://example.com/chat', 'file:///tmp/a',
                    'http://user:pass@example.com/chat', 'https://example.com/chat?a=1'):
            self.assertFalse(_safe_endpoint(url))
        self.assertTrue(_safe_endpoint('https://example.com/v1/chat/completions'))
        self.assertTrue(_safe_endpoint('http://127.0.0.1:4000/v1/chat/completions'))

    def test_valid_llm_choice_reallocates_evidence_without_reuse(self):
        # Full pipeline uses the LLM ONLY for format ordering; all entity IDs
        # are assembled deterministically from the Qloo client.
        with patch('engine.QlooClient') as MockClient, \
             patch('engine.review_formats', return_value=(['workshop', 'exhibition', 'salon'], 'validated')), \
             patch('engine.llm_configured', return_value=True):
            client = MockClient.return_value
            client.search_artist.return_value = {'name': 'Nils Frahm', 'entity_id': 'a1'}
            def insights(seed, kind, city):
                return ([{'name': x['name'], 'entity_id': x['entity_id'], 'query': {}}
                         for x in self.branches[kind]], [])
            client.insights.side_effect = insights
            result = run_research('qloo-secret-is-not-for-llm', 'Nils Frahm', 'Madrid', 'educational workshop')
            self.assertEqual(result['agent_review']['mode'], 'bounded_llm')
            self.assertEqual([c['title'] for c in result['concepts']],
                             ['Listening Lab', 'Sound and Form', 'Cross-Sense Salon'])
            venues = [next(e['entity_id'] for e in c['evidence'] if e['type'] == 'place')
                      for c in result['concepts']]
            self.assertEqual(len(set(venues)), 3)
            self.assertTrue(all(e['source'].startswith('Qloo ') for c in result['concepts'] for e in c['evidence']))
            self.assertEqual(result['trace'][4]['phase'], 'Agent review')

    def test_network_error_falls_back(self):
        from urllib.error import URLError
        with patch.dict(os.environ, self.env), \
             patch('agent_reviewer.urllib.request.urlopen', side_effect=URLError('offline')):
            chosen, reason = review_formats(self.anchor, self.branches, 'Madrid', 'film programme')
            self.assertIsNone(chosen)
            self.assertEqual(reason, 'transport_error')


if __name__ == '__main__':
    unittest.main()
