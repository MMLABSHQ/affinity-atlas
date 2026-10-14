"""Contract tests: objective must change decisions, safeguards must hold."""
import unittest
from decision_engine import compile_proposals, parse_objective
from engine import venue_assessment


def ent(name, kind):
    obj = {"name": name, "type": kind, "entity_id": name.lower().replace(" ", "-"),
           "source": "Qloo /v2/insights"}
    if kind == "place":
        obj["venue_review"] = venue_assessment(name)
    return obj


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.artist = {"name": "Nils Frahm", "type": "artist", "entity_id": "a1", "source": "Qloo /search"}
        self.branches = {
            "movie": [ent("Phantom Thread", "movie"), ent("Roma", "movie")],
            "brand": [ent("Sonos", "brand"), ent("Devialet", "brand")],
            "place": [ent("El Rastro", "place"), ent("Círculo de Bellas Artes", "place"), ent("Goethe-Institut Madrid", "place"), ent("Museo Nacional del Prado", "place")],
        }

    def test_goal_is_not_cosmetic(self):
        film, fd = compile_proposals(self.artist, self.branches, "Madrid", "film and cinema screenings")
        sound, sd = compile_proposals(self.artist, self.branches, "Madrid", "immersive audio sound installation")
        learn, ld = compile_proposals(self.artist, self.branches, "Madrid", "educational learning workshop")
        self.assertEqual(film[0]["title"], "Cinema in Resonance")
        self.assertEqual(sound[0]["title"], "Architecture of Listening")
        self.assertEqual(learn[0]["title"], "Listening Lab")
        self.assertNotEqual(film[0]["title"], sound[0]["title"])
        self.assertEqual(fd["intent"]["primary"], "cinema")
        self.assertEqual(sd["intent"]["primary"], "audio")
        self.assertEqual(ld["intent"]["primary"], "education")

    def test_education_prefers_institution_but_never_claims_booking(self):
        concepts, review = compile_proposals(self.artist, self.branches, "Madrid", "educational workshop")
        self.assertIn("Museo Nacional del Prado", concepts[0]["description"])
        self.assertIn("unverified", concepts[0]["description"].lower())
        self.assertTrue(any("El Rastro" == r["item"] for r in review["rejected"]))

    def test_public_places_excluded_and_constraints_are_not_facts(self):
        concepts, decision = compile_proposals(self.artist, self.branches, "Madrid", "Low-budget accessible music event")
        self.assertTrue(concepts)
        self.assertFalse(any("El Rastro" in c["description"] for c in concepts))
        self.assertTrue(all("NOT verified by Qloo" in " ".join(c["checks_required"]) for c in concepts))
        self.assertIn("budget_unverified", decision["intent"]["constraints"])
        self.assertIn("accessibility_unverified", decision["intent"]["constraints"])

    def test_no_places_means_no_venues_concocted(self):
        only = {"movie": self.branches["movie"], "brand": self.branches["brand"], "place": []}
        concepts, decision = compile_proposals(self.artist, only, "Madrid", "immersive audio installation")
        self.assertEqual(concepts, [])
        self.assertEqual(decision["selected"], 0)

    def test_one_branch_does_not_hallucinate_other(self):
        only = {"movie": [], "brand": self.branches["brand"], "place": self.branches["place"]}
        concepts, decision = compile_proposals(self.artist, only, "Madrid", "audio installation")
        self.assertTrue(concepts)
        self.assertFalse(any(any(e["type"] == "movie" for e in c["evidence"]) for c in concepts))
        self.assertEqual(decision["selected"], len(concepts))

    def test_missing_entity_id_rejected(self):
        bad = dict(self.branches)
        bad["brand"] = [dict(self.branches["brand"][0], entity_id="")]
        concepts, decision = compile_proposals(self.artist, bad, "Madrid", "audio")
        self.assertFalse(any(any(e["type"] == "brand" for e in c["evidence"]) for c in concepts))
        self.assertTrue(any("Missing source-backed" in r["reason"] for r in decision["rejected"]))

    def test_spanish_goal(self):
        self.assertEqual(parse_objective("Taller educativo para aprender de cine y musica")["primary"], "education")
        self.assertEqual(parse_objective("Instalación sonora inmersiva en Madrid")["primary"], "audio")


if __name__ == "__main__":
    unittest.main()
