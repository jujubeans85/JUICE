"""Contract tests for graph routing and rejecting requests that cannot mean what they say."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


_PATH = Path(__file__).resolve().parents[1] / "music" / "workflows.py"
_SPEC = importlib.util.spec_from_file_location("music_workflows_under_test", _PATH)
workflows = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(workflows)


class MusicWorkflowsTests(unittest.TestCase):
    def request(self, **changes):
        data = {"style": "Soulful funk, dry drums, warm brass", "seed": 42}
        data.update(changes)
        return data

    def graph(self, **changes):
        return workflows.build_workflow(
            self.request(**changes), "job-123", workflows.DEFAULT_CHECKPOINT
        )

    def test_validation_selects_seed_once_without_mutating_input(self):
        raw = {"style": "  warm jazz  ", "lyrics": "[Verse]\nHello"}
        original = copy.deepcopy(raw)
        with patch.object(workflows.secrets, "randbelow", return_value=123) as choose:
            normalized = workflows.validate_request(raw)
            normalized_again = workflows.validate_request(normalized)
        self.assertEqual(raw, original)
        self.assertEqual(normalized["seed"], 123)
        self.assertEqual(normalized["duration"], 60)
        self.assertEqual(normalized["style"], "warm jazz")
        self.assertEqual(normalized, normalized_again)
        choose.assert_called_once_with(2**31)

    def test_full_song_routes_same_score_seed_and_actual_duration(self):
        graph = self.graph(duration=90)
        self.assertEqual(graph["3"]["inputs"]["abc"], ["2", 0])
        self.assertEqual(graph["9"]["inputs"]["source"], ["2", 0])
        self.assertEqual(graph["5"]["inputs"]["seconds"], ["3", 1])
        self.assertEqual(graph["3"]["inputs"]["max_duration"], 90)
        self.assertEqual([graph[n]["inputs"]["seed"] for n in ("2", "3", "6")], [42] * 3)
        self.assertEqual(graph["6"]["inputs"]["positive"], ["3", 0])
        self.assertEqual(graph["6"]["inputs"]["negative"], ["4", 0])
        self.assertEqual(graph["6"]["inputs"]["latent_image"], ["5", 0])
        self.assertEqual(graph["7"]["inputs"]["vae"], ["1", 2])

    def test_direct_mode_omits_score_generation_and_nonexistent_off_option(self):
        graph = self.graph(composition="off")
        self.assertNotIn("2", graph)
        self.assertNotIn("9", graph)
        self.assertEqual(graph["3"]["inputs"]["abc"], "")
        self.assertEqual(graph["3"]["inputs"]["mode"], "full")
        self.assertNotIn("YuE2GenerateABC", workflows.required_nodes(self.request(composition="off")))

    def test_cover_uses_transcribed_score_with_matching_planning_mode(self):
        for mode in ("melody", "full"):
            with self.subTest(mode=mode):
                req = self.request(task="cover", source_id="source-123", composition=mode)
                graph = workflows.build_workflow(req, "cover-123", workflows.DEFAULT_CHECKPOINT,
                                                  reference_name="juice/source-123.wav")
                self.assertNotIn("2", graph)
                self.assertEqual(graph["11"]["inputs"]["audio"], "juice/source-123.wav")
                self.assertEqual(graph["13"]["inputs"]["audio_encoder"], ["12", 0])
                self.assertEqual(graph["13"]["inputs"]["audio"], ["11", 0])
                self.assertEqual(graph["3"]["inputs"]["abc"], ["13", 0])
                self.assertEqual(graph["3"]["inputs"]["mode"], mode)
                self.assertEqual(graph["13"]["inputs"]["mode"], mode)
                self.assertEqual(graph["9"]["inputs"]["source"], ["13", 0])
                self.assertEqual(set(workflows.required_nodes(req)),
                                 {node["class_type"] for node in graph.values()})

    def test_outputs_are_permanent_master_and_phone_preview(self):
        graph = self.graph()
        self.assertEqual(graph["8"]["class_type"], "SaveAudio")
        self.assertEqual(graph["10"]["class_type"], "SaveAudioMP3")
        self.assertEqual(graph["8"]["inputs"]["audio"], ["7", 0])
        self.assertEqual(graph["10"]["inputs"]["audio"], ["7", 0])
        self.assertEqual(graph["10"]["inputs"]["quality"], "320k")
        self.assertEqual(graph["8"]["inputs"]["filename_prefix"], "JUICE_Music/job-123/master")
        self.assertEqual(graph["10"]["inputs"]["filename_prefix"], "JUICE_Music/job-123/preview")
        self.assertNotIn("PreviewAudio", {node["class_type"] for node in graph.values()})

    def test_rejects_invalid_ranges_types_and_unsupported_features(self):
        cases = [
            {"duration": True}, {"duration": "60"}, {"duration": 29.9},
            {"duration": 360.1}, {"duration": float("nan")}, {"duration": float("inf")},
            {"duration": 10**1000},
            {"seed": True}, {"seed": "42"}, {"seed": 1.5}, {"seed": -1},
            {"seed": 2**31}, {"seed": None}, {"task": "remix"}, {"task": []},
            {"composition": "chords"}, {"composition": []}, {"style": "  "},
            {"style": "x" * 4001}, {"lyrics": "x" * 12001}, {"title": "x" * 121},
            {"lyrics": None}, {"style": "x\x00y"}, {"instrumental": True},
            {"source_id": "source-123"}, {"task": "cover"},
            {"task": "cover", "source_id": "source-123", "composition": "off"},
            {"task": "cover", "source_id": "../secret"},
        ]
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    workflows.validate_request(self.request(**change))
        for raw in (None, [], "request", {1: "value"}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                workflows.validate_request(raw)

    def test_accepts_boundaries_and_empty_lyrics_without_claiming_instrumental(self):
        for duration in (30, 360, 60.5):
            for seed in (0, 2**31 - 1):
                result = workflows.validate_request(self.request(duration=duration, seed=seed, lyrics=""))
                self.assertEqual(result["duration"], duration)
                self.assertEqual(result["seed"], seed)
                self.assertEqual(result["lyrics"], "")
        result = workflows.validate_request(self.request(title="t" * 120, style="s" * 4000, lyrics="l" * 12000))
        self.assertEqual(len(result["lyrics"]), 12000)

    def test_rejects_paths_outside_comfy_input_output_or_model_directories(self):
        for unsafe in ("../bad", "/absolute", "a/../bad", "a//b", "C:\\file", "bad\x00file"):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(ValueError):
                    workflows.build_workflow(self.request(), unsafe, workflows.DEFAULT_CHECKPOINT)
                with self.assertRaises(ValueError):
                    workflows.build_workflow(self.request(), "job", unsafe)
                with self.assertRaises(ValueError):
                    workflows.build_workflow(self.request(task="cover", source_id="source"), "job",
                                              workflows.DEFAULT_CHECKPOINT, reference_name=unsafe)
        with self.assertRaises(ValueError):
            workflows.build_workflow(self.request(task="cover", source_id="source"), "job", workflows.DEFAULT_CHECKPOINT)
        with self.assertRaises(ValueError):
            workflows.build_workflow(self.request(), "job", workflows.DEFAULT_CHECKPOINT, reference_name="valid.wav")

    def test_all_connections_exist_and_graph_has_no_cycle(self):
        scenarios = [self.request(), self.request(composition="off"),
                     self.request(task="cover", source_id="source", composition="melody")]
        for request in scenarios:
            graph = workflows.build_workflow(request, "job", workflows.DEFAULT_CHECKPOINT,
                                              reference_name="reference.wav" if request.get("task") == "cover" else None)
            visited, active = set(), set()
            def visit(node_id):
                self.assertIn(node_id, graph)
                self.assertNotIn(node_id, active, "Workflow contains a cycle")
                if node_id in visited:
                    return
                active.add(node_id)
                for value in graph[node_id]["inputs"].values():
                    if isinstance(value, list):
                        self.assertEqual(len(value), 2)
                        self.assertIsInstance(value[1], int)
                        visit(value[0])
                active.remove(node_id)
                visited.add(node_id)
            for node_id in graph:
                visit(node_id)


if __name__ == "__main__":
    unittest.main()
