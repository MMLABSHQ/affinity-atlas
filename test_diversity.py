"""Offline regression cases for education-versus-cinema live findings."""
import unittest
from decision_engine import compile_proposals
from engine import venue_assessment


def entity(name, kind):
    obj = {"name": name, "type": kind, "entity_id": kind + ':' + name,
           "source": "Qloo /v2/insights"}
    if kind == 'place':
        obj['venue_review'] = venue_assessment(name)
    return obj


class DiversityTests(unittest.TestCase):
    def setUp(self):
        self.anchor = {"name": "Nils Frahm", "entity_id": "artist:nils", "type": "artist", "source": "Qloo /search"}
        self.branches = {
            "movie": [entity(n, 'movie') for n in ("Phantom Thread", "The Shape of Water", "Roma", "Lady Bird", "Moonlight")],
            "brand": [entity(n, 'brand') for n in ("Sonos", "Bang & Olufsen", "Bowers & Wilkins", "Harman Kardon", "Devialet")],
            "place": [entity(n, 'place') for n in ("Museo Nacional del Prado", "Círculo de Bellas Artes", "Goethe-Institut Madrid", "El Rastro", "Plaza de la Armería")],
        }

    def test_education_has_distinct_venues_and_no_double_movie(self):
        concepts, audit = compile_proposals(self.anchor, self.branches, 'Madrid', 'Educational workshops for students with learning activities')
        self.assertEqual([x['title'] for x in concepts], ['Listening Lab', 'Cross-Sense Salon', 'Sound and Form'])
        self.assertEqual(len(concepts), 3)
        venues = [next(e['entity_id'] for e in c['evidence'] if e['type'] == 'place') for c in concepts]
        self.assertEqual(len(set(venues)), 3)
        movies = [e['entity_id'] for c in concepts for e in c['evidence'] if e['type'] == 'movie']
        self.assertEqual(len(movies), len(set(movies)))
        self.assertFalse(any(x['reused'] for x in audit['diversity_audit']))
        self.assertNotIn('El Rastro', ' '.join(c['description'] for c in concepts))

    def test_cinema_uses_three_distinct_movies_when_possible(self):
        concepts, audit = compile_proposals(self.anchor, self.branches, 'Madrid', 'Film screenings and cinema')
        self.assertEqual([x['title'] for x in concepts], ['Cinema in Resonance', 'Cross-Sense Salon', 'Listening Lab'])
        movies = [e['entity_id'] for c in concepts for e in c['evidence'] if e['type'] == 'movie']
        self.assertEqual(len(movies), 3)
        self.assertEqual(len(set(movies)), 3)
        venues = [next(e['entity_id'] for e in c['evidence'] if e['type'] == 'place') for c in concepts]
        self.assertEqual(len(set(venues)), 3)

    def test_reuse_is_disclosed_when_alternatives_exhausted(self):
        less = {k: v[:1] for k, v in self.branches.items()}
        concepts, audit = compile_proposals(self.anchor, less, 'Madrid', 'Educational workshop')
        self.assertEqual(len(concepts), 3)
        self.assertTrue(any(x['reused'] for x in audit['diversity_audit'][1:]))
        self.assertIn('Reused', concepts[1]['decision_reason'])


if __name__ == '__main__':
    unittest.main()
