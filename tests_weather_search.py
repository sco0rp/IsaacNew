"""Weather web lookup: routing helpers + live-API integration shape."""
from __future__ import annotations

import asyncio
import unittest

from search import (
    extract_weather_location,
    looks_like_weather_query,
    looks_like_place_only_refinement,
    MultiSearch,
    SearchHit,
    _geocode_query_candidates,
)


class TestWeatherSearchHelpers(unittest.TestCase):
    def test_looks_like_weather_positive(self):
        self.assertTrue(looks_like_weather_query("Wie wird das Wetter morgen?"))
        self.assertTrue(looks_like_weather_query("Suche: Wetter Berlin morgen"))
        self.assertTrue(looks_like_weather_query("Recherchiere Temperatur in Hamburg"))
        self.assertTrue(looks_like_weather_query("Wie wird das Wetter morgen in Mühlhausen?"))

    def test_looks_like_weather_explanatory_negative(self):
        self.assertFalse(
            looks_like_weather_query(
                "Erkläre mir das Wetter als sprachliches Motiv in Literatur"
            )
        )

    def test_extract_location_muehlhausen_and_plz(self):
        self.assertIn(
            "Mühlhausen",
            extract_weather_location("Wie wird das Wetter morgen in Mühlhausen?"),
        )
        loc = extract_weather_location("Wetter 99974 Mühlhausen Thüringen morgen")
        self.assertTrue("99974" in loc or "Mühlhausen" in loc)
        loc2 = extract_weather_location("Ich wollte für 99974 Mühlhausen Thüringen")
        self.assertTrue("99974" in loc2 or "Mühlhausen" in loc2)
        self.assertEqual(extract_weather_location("Suche: Wetter Berlin morgen"), "Berlin")

    def test_place_only_refinement(self):
        self.assertTrue(looks_like_place_only_refinement("Ich wollte für 99974 Mühlhausen Thüringen"))
        self.assertTrue(looks_like_place_only_refinement("99974 Mühlhausen"))
        self.assertFalse(looks_like_place_only_refinement("Wie wird das Wetter morgen?"))
        self.assertFalse(
            looks_like_place_only_refinement(
                "Erkläre mir das Wetter als sprachliches Motiv in Literatur"
            )
        )

    def test_geocode_candidates_include_ascii_and_city(self):
        c = _geocode_query_candidates("99974 Mühlhausen Thüringen")
        self.assertTrue(any("Mühlhausen" in x or "Muhlhausen" in x for x in c))
        self.assertTrue(any("Muhlhausen" in x for x in c))  # ascii fold

    def test_search_prefers_weather_api_hits(self):
        ms = MultiSearch()

        async def fake_weather(query: str):
            return (
                [
                    SearchHit(
                        titel="Open-Meteo Vorhersage: Mühlhausen/Thüringen",
                        snippet="2026-07-18: Regen, 16–22°C",
                        url="https://api.open-meteo.com/example",
                        quelle="open-meteo",
                        score=10.0,
                    )
                ],
                "Wettervorhersage für Mühlhausen/Thüringen (Thüringen), DE (Open-Meteo, live):\n"
                "2026-07-18: Regen, 16–22°C",
            )

        async def empty_engine(*_a, **_k):
            return []

        ms._weather_forecast = fake_weather
        ms._ddg = empty_engine
        ms._brave = empty_engine
        ms._searxng = empty_engine
        ms._wikipedia = empty_engine
        ms._reddit = empty_engine
        ms._arxiv = empty_engine
        ms.cache._c.clear()

        result = asyncio.run(
            ms.search("Wie wird das Wetter morgen in Mühlhausen?", max_hits=5, load_fulltext=False)
        )
        self.assertIn("weather_api", result.quellen)
        self.assertIn("Mühlhausen", result.abstract)
        self.assertNotIn("Berlin", result.abstract)
        self.assertEqual(result.hits[0].quelle, "open-meteo")

    def test_tool_request_weather_maps_to_search_intent(self):
        from low_complexity import classify_interaction_result, InteractionClass
        from isaac_core import IsaacKernel, Intent, detect_intent

        text = "Wie wird das Wetter morgen?"
        cls = classify_interaction_result(text)
        self.assertEqual(cls.interaction_class, InteractionClass.TOOL_REQUEST)
        kernel = object.__new__(IsaacKernel)
        intent = kernel._resolve_intent_from_classification(
            text, detect_intent(text), cls.interaction_class
        )
        self.assertEqual(intent, Intent.SEARCH)

    def test_regelwerk_skips_weather_place_terms(self):
        from regelwerk import Regelwerk
        rw = Regelwerk.__new__(Regelwerk)
        rw._regeln = {}
        rw._fragen = []
        # should not flag place names in weather questions
        self.assertEqual(rw._erkenne_unbekannte_begriffe("Wetter morgen in Mühlhausen"), "")
        self.assertEqual(rw._erkenne_unbekannte_begriffe("99974 Mühlhausen Thüringen"), "")


if __name__ == "__main__":
    unittest.main()
