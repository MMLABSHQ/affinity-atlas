"""Offline unit checks. Run: python3 -m unittest -v"""
import unittest
from unittest.mock import patch
from engine import venue_assessment, entity_brief, build_concepts, run_research

SEED = "0D8EAFA4-CEEA-44D5-8E1F-26A8A9F49A77"


def sample_entity(name):
    return {"name": name, "entity_id": "sample-id", "query": {
        "explainability": {"signal.interests.entities": [{"entity_id": SEED, "score": 1}]}
    }}


class EngineTests(unittest.TestCase):
    def test_public_space_not_assumed_venue(self):
        self.assertEqual(venue_assessment("El Rastro")["tier"], "space_requires_permits")
        self.assertEqual(venue_assessment("Plaza de la Armería")["tier"], "space_requires_permits")

    def test_score_not_transformed_to_percentage(self):
        brief = entity_brief(sample_entity("Círculo de Bellas Artes"), "place", SEED)
        self.assertTrue(brief["seed_signal_referenced"])
        self.assertNotIn("score", brief)
        self.assertNotIn("100%", str(brief))

    def test_no_proposals_without_evidence(self):
        self.assertEqual(build_concepts({"name": "Nils", "entity_id": SEED},
                                       {"movie": [], "brand": [], "place": []}, "Madrid", "test"), [])

    @patch("engine.QlooClient")
    def test_mock_pipeline_three_proposals(self, MockClient):
        client = MockClient.return_value
        client.search_artist.return_value = {"name": "Nils Frahm", "entity_id": SEED}
        def fake_insights(seed_id, kind, city):
            examples = {"movie": ["Phantom Thread", "Roma"],
                        "brand": ["Sonos", "Devialet"],
                        "place": ["El Rastro", "Círculo de Bellas Artes", "Goethe-Institut Madrid"]}
            return [sample_entity(x) for x in examples[kind]], []
        client.insights.side_effect = fake_insights
        result = run_research("test-key", "Nils Frahm", "Madrid", "Cultural programming")
        self.assertEqual(len(result["concepts"]), 3)
        self.assertEqual(len(result["branches"]["place"]), 3)
        self.assertTrue(all(len(c["evidence"]) >= 3 for c in result["concepts"]))
        self.assertFalse(any("El Rastro" in c["description"] for c in result["concepts"]))
        self.assertEqual(len(result["trace"]), 7)


if __name__ == "__main__":
    unittest.main()
