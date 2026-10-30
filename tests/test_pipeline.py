import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline import Pipeline, QualityError, load_config, validate_short


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = load_config(Path("config/pipeline.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_job_has_master_three_localizations_and_policy_limited_shorts(self):
        job = Pipeline(self.root, self.config).create_job("How Roman roads shaped Europe")
        self.assertEqual(["es", "fr", "de"], list(job["localizations"]))
        self.assertEqual(6, len(job["shorts"]))
        self.assertEqual("private", job["upload"]["privacy_status"])

    def test_approved_niche_and_provisional_paris_schedule(self):
        self.assertEqual("approved", self.config["editorial"]["approval_status"])
        self.assertEqual(["Spain", "France", "Germany"], self.config["editorial"]["countries"])
        schedule = self.config["schedule"]
        self.assertEqual("Europe/Paris", schedule["timezone"])
        self.assertEqual("19:00", schedule["long_video_time"])
        self.assertEqual("12:30", schedule["short_time"])
        self.assertTrue(schedule["provisional_until_audience_analytics"])
        self.assertEqual("fr", schedule["language_rotation"]["monday"])
        self.assertEqual("best_performing_theme", schedule["language_rotation"]["sunday"])

    def test_multilanguage_audio_is_pending_with_rotation_fallback(self):
        strategy = self.config["youtube"]["publication_strategy"]
        self.assertEqual("pending_manual_studio_verification", strategy["multi_language_audio"])
        self.assertEqual("language_rotation", strategy["fallback"])
        self.assertFalse(strategy["publish_enabled"])

    def test_job_records_editorial_and_schedule_controls(self):
        job = Pipeline(self.root, self.config).create_job("How Roman roads shaped Europe")
        self.assertEqual("Europe/Paris", job["schedule"]["timezone"])
        self.assertEqual("policy-approved-distinct-only", job["publication"]["rule"])
        self.assertTrue(job["publication"]["variants_to_backlog"])

    def test_master_and_caption_contracts_are_configured(self):
        self.assertEqual([60, 120], self.config["master_video"]["duration_seconds"])
        self.assertEqual(2, self.config["master_video"]["subtitles"]["max_lines"])
        captions = self.config["shorts"]["captions"]
        self.assertEqual(1, captions["max_lines"])
        self.assertEqual([3, 5], captions["words_per_event"])
        self.assertEqual(120, captions["safe_sides_px"])
        self.assertEqual(300, captions["safe_bottom_px"])
        self.assertEqual(0.75, captions["max_width_ratio"])
        self.assertEqual("shadow_only", captions["background"])
        master_subtitles = self.config["master_video"]["subtitles"]
        self.assertEqual("film_style_long_phrases", master_subtitles["chunking"])
        self.assertEqual("shadow_only", master_subtitles["background"])
        self.assertEqual(135, self.config["master_video"]["narration_words_per_minute"])

    def test_short_qa_rejects_overflow_unsafe_and_mid_sentence_cut(self):
        bad = {
            "source": {"start_ms": 100, "end_ms": 900, "sentence_boundary_start": False, "sentence_boundary_end": True},
            "captions": [{"text": "too many words in this caption event", "start_ms": 100, "end_ms": 900, "lines": 2, "x": 0.5, "y": 0.95, "width_ratio": 0.9, "contrast_ratio": 2.0}],
            "crop": {"subject_preserved": False, "method": "blind-center"},
            "shots": ["same", "same"], "audio_sync_ms": 300, "frame_samples": [{"collision": True, "ui_safe": False}]
        }
        failed = validate_short(bad)
        self.assertTrue({"sentence_boundaries", "caption_words", "caption_lines", "caption_width", "safe_zone", "contrast", "subject_preservation", "shot_variation", "audio_sync", "frame_collisions"}.issubset(failed))

    def test_smoke_short_passes_visual_contract_and_has_traceable_source(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        result = pipeline.run(job["id"], smoke=True)
        self.assertTrue(all(not validate_short(short) for short in result["shorts"]))
        self.assertTrue(all("source" in short for short in result["shorts"]))
        self.assertTrue((self.root / "review" / f'{job["id"]}-contact-sheet.html').exists())

    def test_resume_skips_completed_stages(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        first = pipeline.run(job["id"], smoke=True)
        second = pipeline.run(job["id"], smoke=True)
        self.assertEqual(first["events"], second["events"])
        self.assertEqual("ready_for_review", second["status"])

    def test_gate_rejects_missing_sources_and_duplicate_script(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        job["research"]["sources"] = []
        pipeline.save(job)
        with self.assertRaisesRegex(QualityError, "factual_sources"):
            pipeline.run(job["id"], smoke=True)

    def test_upload_is_dry_run_and_never_public(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        pipeline.run(job["id"], smoke=True)
        receipt = pipeline.upload(job["id"])
        self.assertTrue(receipt["dry_run"])
        self.assertEqual("private", receipt["privacy_status"])

    def test_scene_manifest_preserves_provenance_readiness_and_revision_state(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        result = pipeline.run(job["id"], smoke=True)
        scene = result["master"]["scenes"][0]
        self.assertEqual("scene-01", scene["id"])
        self.assertEqual("simulated", scene["asset"]["reality"])
        self.assertEqual("ready", scene["narration"]["status"])
        self.assertTrue(scene["claims"][0]["source_ids"])
        self.assertEqual(1, scene["revision"])

    def test_shorts_retain_parent_scene_lineage(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        result = pipeline.run(job["id"], smoke=True)
        self.assertTrue(all(short["parent_job_id"] == job["id"] for short in result["shorts"]))
        self.assertTrue(all(short["source_scene_ids"] for short in result["shorts"]))

    def test_review_and_upload_boundary_fail_closed(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        result = pipeline.run(job["id"], smoke=True)
        self.assertEqual({"editorial": "pending", "publication": "pending"}, result["review"])
        receipt = pipeline.upload(job["id"])
        self.assertEqual("simulation_only", receipt["state"])
        self.assertFalse(receipt["account_accessed"])
        self.assertFalse(receipt["reconciliation_required"])

    def test_quality_rejects_stale_narration_or_unverified_claim(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        pipeline._stage_master(job, smoke=True)
        pipeline._stage_shorts(job, smoke=True)
        job["master"]["scenes"][0]["narration"]["status"] = "stale"
        job["master"]["scenes"][1]["claims"][0]["verified"] = False
        with self.assertRaises(QualityError):
            pipeline._stage_quality(job, smoke=True)

    def test_scene_repair_invalidates_only_scene_and_downstream_stages(self):
        pipeline = Pipeline(self.root, self.config)
        job = pipeline.create_job("How Roman roads shaped Europe")
        pipeline.run(job["id"], smoke=True)
        repaired = pipeline.repair_scene(job["id"], "scene-02", narration="Corrected evidence beat")
        scene = repaired["master"]["scenes"][1]
        self.assertEqual(2, scene["revision"])
        self.assertEqual("stale", scene["narration"]["status"])
        self.assertEqual("queued", repaired["status"])
        self.assertEqual(["research", "master"], repaired["completed"])


if __name__ == "__main__":
    unittest.main()
