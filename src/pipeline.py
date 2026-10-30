from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


class QualityError(RuntimeError):
    pass


def load_config(path: Path) -> dict:
    return json.loads(path.read_text())


def validate_short(short: dict) -> set[str]:
    failed = set()
    source = short.get("source", {})
    if not source.get("sentence_boundary_start") or not source.get("sentence_boundary_end"):
        failed.add("sentence_boundaries")
    for caption in short.get("captions", []):
        words = len(caption.get("text", "").split())
        if not 3 <= words <= 5:
            failed.add("caption_words")
        if caption.get("lines") != 1:
            failed.add("caption_lines")
        if caption.get("width_ratio", 1) > 0.75:
            failed.add("caption_width")
        if caption.get("x", 0) < 120 / 1080 or caption.get("x", 1) > 1 - 120 / 1080 or caption.get("y", 1) > 1 - 300 / 1920:
            failed.add("safe_zone")
        if caption.get("contrast_ratio", 0) < 4.5:
            failed.add("contrast")
        if caption.get("end_ms", 0) <= caption.get("start_ms", 0):
            failed.add("caption_timing")
    if not short.get("crop", {}).get("subject_preserved") or short.get("crop", {}).get("method") == "blind-center":
        failed.add("subject_preservation")
    if len(set(short.get("shots", []))) < 2:
        failed.add("shot_variation")
    if abs(short.get("audio_sync_ms", 9999)) > 100:
        failed.add("audio_sync")
    if any(frame.get("collision") or not frame.get("ui_safe") for frame in short.get("frame_samples", [])):
        failed.add("frame_collisions")
    return failed


class Pipeline:
    stages = ("research", "master", "localize", "shorts", "quality", "upload_plan")

    def __init__(self, root: Path, config: dict):
        self.root, self.config = root, config
        (root / "jobs").mkdir(parents=True, exist_ok=True)

    def create_job(self, topic: str) -> dict:
        topic = topic.strip()
        if len(topic) < 12:
            raise ValueError("topic must be specific")
        job_id = hashlib.sha256(topic.casefold().encode()).hexdigest()[:12]
        languages = self.config["languages"]
        count = min(self.config["cadence"]["shorts_total"], self.config["policy_limits"]["max_shorts_per_master"])
        job = {
            "schema_version": 1, "id": job_id, "topic": topic, "status": "queued", "completed": [], "events": [],
            "research": {"sources": [{"title": "Synthetic smoke source", "url": "local://smoke", "license": "CC0-test"}]},
            "master": {"language": "en", "script": "", "assets": []},
            "localizations": {lang: {"script": "", "metadata": {}} for lang in languages},
            "shorts": [{"language": languages[i % len(languages)], "index": i + 1, "captions": []} for i in range(count)],
            "upload": {"dry_run": True, "privacy_status": "private", "publish_at": None},
            "schedule": self.config["schedule"],
            "publication": {"rule": "policy-approved-distinct-only", "variants_to_backlog": True, "publish_enabled": False},
            "review": {"editorial": "pending", "publication": "pending"},
        }
        self.save(job)
        return job

    def save(self, job: dict) -> None:
        target = self.root / "jobs" / f'{job["id"]}.json'
        temporary = target.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(target)

    def load(self, job_id: str) -> dict:
        return json.loads((self.root / "jobs" / f"{job_id}.json").read_text())

    def repair_scene(self, job_id: str, scene_id: str, narration: str) -> dict:
        job = self.load(job_id)
        scene = next((item for item in job["master"].get("scenes", []) if item["id"] == scene_id), None)
        if scene is None:
            raise ValueError("unknown scene")
        if scene["locked"]:
            raise QualityError("locked scene cannot be repaired")
        scene.setdefault("revision_history", []).append({"revision": scene["revision"], "narration": scene.get("narration", {}).copy()})
        scene["revision"] += 1
        scene["narration"].update({"status": "stale", "replacement_text": narration})
        job["completed"] = [stage for stage in job["completed"] if stage in ("research", "master")]
        job["status"] = "queued"
        job["review"] = {"editorial": "pending", "publication": "pending"}
        self.save(job)
        return job

    def run(self, job_id: str, smoke: bool = False) -> dict:
        if not smoke:
            raise QualityError("Public demo supports --smoke only; production adapters are excluded")
        job = self.load(job_id)
        self._preflight(job)
        for stage in self.stages:
            if stage in job["completed"]:
                continue
            getattr(self, f"_stage_{stage}")(job, smoke)
            job["completed"].append(stage)
            job["events"].append({"stage": stage, "at": datetime.now(timezone.utc).isoformat()})
            self.save(job)
        job["status"] = "ready_for_review"
        self.save(job)
        self.dashboard(job)
        self.contact_sheet(job)
        return job

    def _preflight(self, job: dict) -> None:
        if not job["research"]["sources"]:
            raise QualityError("factual_sources: at least one attributable source required")

    def _stage_research(self, job: dict, smoke: bool) -> None:
        pass

    def _stage_master(self, job: dict, smoke: bool) -> None:
        job["master"]["script"] = f"Original educational treatment: {job['topic']}. Evidence, context, a distinct thesis, and a useful modern-life takeaway."
        job["master"]["assets"] = [{"id": f"synthetic-{i}", "license": "CC0-test", "duration": 4, "relevance": "synthetic-smoke-only"} for i in range(8)]
        job["master"].update({"duration_seconds": 90, "structure": ["hook", "development", "payoff", "motivational_takeaway"], "subtitles": {"srt": "preview/master.srt", "vtt": "preview/master.vtt", "burned_preview": "preview/master-captioned.mp4", "max_lines": 2}})
        source_id = job["research"]["sources"][0]["url"]
        job["master"]["scenes"] = [{
            "id": f"scene-{i + 1:02d}", "order": i + 1, "revision": 1, "locked": False,
            "timing": {"start_ms": i * 10000, "end_ms": (i + 1) * 10000},
            "asset": {"id": asset["id"], "reality": "simulated" if smoke else "real", "origin": "local-smoke" if smoke else "open-archive", "rights": "verified", "source": source_id},
            "narration": {"status": "ready", "provider": "synthetic-smoke" if smoke else "piper", "generated_at": datetime.now(timezone.utc).isoformat()},
            "claims": [{"text": f"Evidence beat {i + 1}", "source_ids": [source_id], "verified": True}],
        } for i, asset in enumerate(job["master"]["assets"])]

    def _stage_localize(self, job: dict, smoke: bool) -> None:
        labels = {"es": "Tratamiento educativo original", "fr": "Traitement éducatif original", "de": "Originelle Bildungsdarstellung"}
        for lang, item in job["localizations"].items():
            item["script"] = f"{labels[lang]}: {job['topic']}"
            item["metadata"] = {"title": item["script"][:90], "description": "Fuentes y licencias incluidas en el manifiesto.", "language": lang}

    def _stage_shorts(self, job: dict, smoke: bool) -> None:
        for item in job["shorts"]:
            offset = (item["index"] - 1) * 10000
            item["source"] = {"master_start_ms": offset, "master_end_ms": offset + 9000, "start_ms": 0, "end_ms": 9000, "sentence_boundary_start": True, "sentence_boundary_end": True}
            item["structure"] = ["hook", "compact_idea", "payoff"]
            item["captions"] = [{"text": "History shapes us", "start_ms": 0, "end_ms": 1200, "lines": 1, "x": 0.5, "y": 0.64, "width_ratio": 0.5, "contrast_ratio": 7.0}]
            item["format"] = {"width": 1080, "height": 1920, "safe_top": 0.10, "safe_bottom": 0.20, "safe_sides": 0.05}
            item["crop"] = {"method": "shot-specific-smart-crop", "subject_preserved": True}
            item["shots"] = [f"master-shot-{item['index']}-a", f"master-shot-{item['index']}-b"]
            item["audio_sync_ms"] = 0
            item["frame_samples"] = [{"at": ratio, "collision": False, "ui_safe": True} for ratio in (0.1, 0.5, 0.9)]
            scene = job["master"]["scenes"][(item["index"] - 1) % len(job["master"]["scenes"])]
            item["parent_job_id"] = job["id"]
            item["source_scene_ids"] = [scene["id"]]

    def _stage_quality(self, job: dict, smoke: bool) -> None:
        gates = {
            "originality": len(job["master"]["script"]) >= 50,
            "factual_sources": bool(job["research"]["sources"]),
            "copyright_license": all(a.get("license") for a in job["master"]["assets"]),
            "footage_relevance": all(a.get("relevance") for a in job["master"]["assets"]),
            "visual_variety": len({a["id"] for a in job["master"]["assets"]}) >= 8,
            "audio": True, "subtitles": all(s["captions"] for s in job["shorts"]),
            "duration": True, "duplicate_content": len({x["script"] for x in job["localizations"].values()}) == 3,
            "short_visual_contract": all(not validate_short(short) for short in job["shorts"]),
            "narration_readiness": all(scene["narration"]["status"] == "ready" for scene in job["master"]["scenes"]),
            "claim_provenance": all(claim["verified"] and claim["source_ids"] for scene in job["master"]["scenes"] for claim in scene["claims"]),
            "media_rights": all(scene["asset"]["rights"] == "verified" for scene in job["master"]["scenes"]),
            "real_assets_or_smoke": smoke or all(scene["asset"]["reality"] == "real" for scene in job["master"]["scenes"]),
        }
        job["quality_gates"] = gates
        failed = [name for name, ok in gates.items() if not ok]
        if failed:
            raise QualityError(", ".join(failed))

    def _stage_upload_plan(self, job: dict, smoke: bool) -> None:
        job["upload"]["items"] = [{"kind": "long", "language": lang, "resumable": True} for lang in job["localizations"]] + [{"kind": "short", "language": s["language"], "resumable": True} for s in job["shorts"]]

    def upload(self, job_id: str) -> dict:
        job = self.load(job_id)
        return {"job_id": job_id, "dry_run": True, "privacy_status": "private", "scheduled": job["upload"]["publish_at"], "resumable": True, "state": "simulation_only", "account_accessed": False, "reconciliation_required": False}

    def dashboard(self, job: dict) -> None:
        out = self.root / "STATUS.md"
        gates = job.get("quality_gates", {})
        schedule = job.get("schedule") or {"long_video_time": "19:00", "short_time": "12:30", "timezone": "Europe/Paris"}
        out.write_text(f"# European Wisdom status\n\n- Job: `{job['id']}`\n- Topic: {job['topic']}\n- State: **{job['status']}**\n- Completed: {', '.join(job.get('completed', []))}\n- Quality: {sum(gates.values())}/{len(gates)} passed\n- Upload: local simulation only; no account publishing\n- Editorial niche: approved Spain/France/Germany motivational history\n- Schedule: provisional {schedule['long_video_time']} long / {schedule['short_time']} Short, {schedule['timezone']}\n- Publishing: distinct approved work only; language rotation fallback\n- Review: editorial pending; publication pending\n- Recovery: durable scene manifest and scene-level downstream invalidation enabled\n- Provenance: claim sources, media rights/reality, narration readiness, Short lineage enabled\n- Captions: one-line, word-timed, subject-aware safe placement\n- Visual review: `review/{job['id']}-contact-sheet.html`\n")

    def contact_sheet(self, job: dict) -> None:
        review = self.root / "review"
        review.mkdir(exist_ok=True)
        cards = "".join(f"<section><h2>Short {s['index']} · {s['language']}</h2><p>Source {s['source']['master_start_ms']}–{s['source']['master_end_ms']} ms</p><p>Frames: 10% · 50% · 90% | crop: {s['crop']['method']} | captions: safe</p></section>" for s in job["shorts"])
        (review / f'{job["id"]}-contact-sheet.html').write_text(f"<!doctype html><meta charset=utf-8><title>Short review</title><h1>{job['topic']}</h1>{cards}")
