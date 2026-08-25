from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import tempfile
import threading
import time
from time import perf_counter
from pathlib import Path
from typing import Any

from aiohttp import web

from core.api.base_handler import BaseHandler
from core.companion.importers.compiler import PersonaCompiler
from core.companion.importers.dot_skill import DotSkillAdapter
from core.companion.importers.validator import PersonaSpecValidator
from core.companion.models import PersonaSpec
from core.companion.persona.evaluator import evaluate_persona
from core.companion.observability import metrics
from core.companion.persona.judge import PersonaJudge
from core.companion.persona.semantic_extractor import PersonaSemanticExtractor
from core.companion.persona.conversation_evaluator import evaluate_conversation_samples
from core.companion.runtime import companion_runtime_health, evict_companion_persona


COMPILER_VERSION = "cyber-persona-compiler/6"
MAX_CLOCK_SKEW_SECONDS = 60
MAX_JSON_BYTES = 16 * 1024 * 1024
SAFE_TEXT_RE = re.compile(r"[^a-zA-Z0-9._:/@+\- ]+")


class PersonaCompilerHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        companion = config.get("companion", {})
        manager_api = config.get("manager-api", {})
        self.enabled = bool(companion.get("persona_admin_enabled", True))
        self.secret = str(companion.get("compiler_secret") or manager_api.get("secret") or "")
        self._nonces: dict[str, float] = {}
        self._nonce_lock = threading.Lock()
        self.judge = PersonaJudge(companion.get("persona_judge"))
        self.semantic_extractor = PersonaSemanticExtractor(
            companion.get("persona_semantic_extractor")
        )

    def _safe_error(self, error: Exception) -> str:
        text = SAFE_TEXT_RE.sub(" ", str(error)).strip()
        return text[:500] or "Persona 编译失败"

    def _verify(self, request: web.Request, body: bytes):
        if not self.enabled:
            raise web.HTTPNotFound()
        if not self.secret or "你" in self.secret:
            raise web.HTTPServiceUnavailable(text="Persona Compiler 尚未配置共享密钥")
        timestamp = request.headers.get("X-Companion-Timestamp", "")
        nonce = request.headers.get("X-Companion-Nonce", "")
        signature = request.headers.get("X-Companion-Signature", "")
        try:
            timestamp_value = int(timestamp)
        except ValueError as exc:
            metrics.increment("companion_hmac_reject_total", reason="timestamp")
            raise web.HTTPUnauthorized(text="无效时间戳") from exc
        now = int(time.time())
        if abs(now - timestamp_value) > MAX_CLOCK_SKEW_SECONDS:
            metrics.increment("companion_hmac_reject_total", reason="expired")
            raise web.HTTPUnauthorized(text="签名已过期")
        if not nonce or len(nonce) > 128:
            metrics.increment("companion_hmac_reject_total", reason="nonce")
            raise web.HTTPUnauthorized(text="无效 nonce")
        body_hash = hashlib.sha256(body).hexdigest()
        canonical = "\n".join((timestamp, nonce, request.method.upper(), request.path, body_hash))
        expected = hmac.new(self.secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            metrics.increment("companion_hmac_reject_total", reason="signature")
            raise web.HTTPUnauthorized(text="签名校验失败")
        with self._nonce_lock:
            expired_before = time.time() - MAX_CLOCK_SKEW_SECONDS
            self._nonces = {key: value for key, value in self._nonces.items() if value >= expired_before}
            if nonce in self._nonces:
                metrics.increment("companion_hmac_reject_total", reason="replay")
                raise web.HTTPUnauthorized(text="签名已重放")
            self._nonces[nonce] = time.time()

    async def _payload(self, request: web.Request) -> dict[str, Any]:
        body = await request.read()
        if len(body) > MAX_JSON_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=MAX_JSON_BYTES, actual_size=len(body))
        self._verify(request, body)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise web.HTTPBadRequest(text="请求必须是 UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="JSON 根节点必须是对象")
        return payload

    @staticmethod
    def _artifact(payload: dict[str, Any]) -> bytes:
        encoded = payload.get("artifactBase64")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("缺少 artifactBase64")
        try:
            value = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("artifactBase64 不是合法 Base64") from exc
        if len(value) > 10 * 1024 * 1024:
            raise ValueError("Persona ZIP 超过 10MB 限制")
        if not value.startswith(b"PK\x03\x04"):
            raise ValueError("Persona 制品必须是 ZIP")
        return value

    @staticmethod
    def _apply_trusted_metadata(spec: PersonaSpec, metadata: Any):
        if not isinstance(metadata, dict):
            return
        source = spec.source
        mappings = {
            "sourceUrl": "source_url",
            "sourceCommit": "source_commit",
        }
        for incoming, target in mappings.items():
            if incoming in metadata and metadata[incoming] is not None:
                source[target] = metadata[incoming]
        truthy = lambda value: value is True or str(value).lower() in {"true", "1", "yes"}
        existing_real = truthy(source.get("is_real_person"))
        existing_public = truthy(source.get("is_public_figure"))
        incoming_real = metadata.get("isRealPerson") is True
        incoming_public = metadata.get("isPublicFigure") is True
        source["is_real_person"] = existing_real or incoming_real or existing_public or incoming_public
        source["is_public_figure"] = existing_public or incoming_public
        if source["is_real_person"]:
            source["is_fictional"] = False
        elif "isFictional" in metadata:
            source["is_fictional"] = metadata.get("isFictional") is True
        if source.get("is_public_figure"):
            source["family"] = "celebrity"
            spec.relationship_policy["recommended_mode"] = "friend"
            spec.relationship_policy["source"] = "agent-binding"
            spec.relationship_policy["initial_stage"] = "familiar"
            if spec.id.startswith("persona.colleague."):
                spec.id = "persona.celebrity." + spec.id.removeprefix("persona.colleague.")

    def _compile_artifact(self, artifact: bytes, metadata: Any) -> dict[str, Any]:
        with tempfile.NamedTemporaryFile(prefix="persona-upload-", suffix=".zip") as handle:
            handle.write(artifact)
            handle.flush()
            result = DotSkillAdapter().convert(handle.name)
        self._apply_trusted_metadata(result.spec, metadata)
        semantic_report = getattr(
            self, "semantic_extractor", PersonaSemanticExtractor(None)
        ).enrich(result.spec)
        result.spec.conversion_coverage["semantic_analysis"] = semantic_report
        result.report = PersonaSpecValidator().validate(result.spec)
        runtime_prompt = PersonaCompiler().compile(result.spec)
        test_report = evaluate_persona(result.spec, runtime_prompt)
        judge_report = getattr(self, "judge", PersonaJudge(None)).evaluate(result.spec, runtime_prompt)
        judge_passed = judge_report["status"] in {"passed", "skipped", "unavailable"}
        return {
            "compilerVersion": COMPILER_VERSION,
            "personaId": result.spec.id,
            "displayName": result.spec.display_name,
            "suggestedVersion": str(result.spec.source.get("upstream_version") or "v1"),
            "artifactHash": result.artifact_sha256,
            "sourceInventory": result.source_files,
            "canonicalSpec": result.spec.to_dict(),
            "runtimePrompt": runtime_prompt,
            "tokenCount": max(1, len(runtime_prompt) // 4),
            "validationReport": result.report.to_dict(),
            "testReport": test_report,
            "judgeReport": judge_report,
            "semanticAnalysis": semantic_report,
            "publishable": result.report.valid and test_report["status"] == "passed" and judge_passed,
        }

    async def handle_info(self, request: web.Request):
        payload = await self._payload(request)
        del payload
        return web.json_response({"compilerVersion": COMPILER_VERSION, "enabled": True})

    async def handle_health(self, request: web.Request):
        payload = await self._payload(request)
        del payload
        return web.json_response(
            {
                "status": "up",
                "compilerVersion": COMPILER_VERSION,
                "personaAdminEnabled": self.enabled,
                "runtime": companion_runtime_health(),
                "metrics": metrics.snapshot(),
            },
            dumps=lambda value: json.dumps(value, ensure_ascii=False),
        )

    async def handle_inspect(self, request: web.Request):
        try:
            payload = await self._payload(request)
            artifact = self._artifact(payload)
            with tempfile.NamedTemporaryFile(prefix="persona-inspect-", suffix=".zip") as handle:
                handle.write(artifact)
                handle.flush()
                inspection = DotSkillAdapter().inspect(handle.name)
            return web.json_response(
                {
                    "adapter": inspection.adapter,
                    "detected": inspection.detected,
                    "metadata": inspection.metadata,
                    "warnings": inspection.warnings,
                    # This must use the same normalized source digest as convert().
                    # A raw ZIP hash changes with archive metadata and cannot be
                    # compared with ai_persona_version.artifact_hash.
                    "artifactHash": inspection.artifact_sha256,
                },
                dumps=lambda value: json.dumps(value, ensure_ascii=False),
            )
        except web.HTTPException:
            raise
        except Exception as error:
            return web.json_response({"error": self._safe_error(error)}, status=400)

    async def handle_cache_evict(self, request: web.Request):
        try:
            payload = await self._payload(request)
            persona_id = str(payload.get("personaId") or "").strip()
            if not persona_id or len(persona_id) > 160:
                raise ValueError("缺少合法的 personaId")
            return web.json_response(
                {
                    "personaId": persona_id,
                    "evictedEntries": evict_companion_persona(persona_id),
                },
                dumps=lambda value: json.dumps(value, ensure_ascii=False),
            )
        except web.HTTPException:
            raise
        except Exception as error:
            return web.json_response({"error": self._safe_error(error)}, status=400)

    async def handle_compile(self, request: web.Request):
        started = perf_counter()
        try:
            payload = await self._payload(request)
            value = self._compile_artifact(self._artifact(payload), payload.get("sourceMetadata"))
            for issue in value.get("validationReport", {}).get("issues", []):
                if issue.get("severity") == "error":
                    metrics.increment(
                        "companion_persona_validation_fail_total",
                        code=issue.get("code", "unknown"),
                    )
            metrics.observe_ms("companion_persona_compile_duration_ms", (perf_counter() - started) * 1000,
                               adapter="dot-skill", status="success")
            return web.json_response(value, dumps=lambda item: json.dumps(item, ensure_ascii=False))
        except web.HTTPException:
            raise
        except Exception as error:
            metrics.observe_ms("companion_persona_compile_duration_ms", (perf_counter() - started) * 1000,
                               adapter="dot-skill", status="failed")
            return web.json_response({"error": self._safe_error(error)}, status=400)

    async def handle_test(self, request: web.Request):
        started = perf_counter()
        try:
            payload = await self._payload(request)
            raw_spec = payload.get("canonicalSpec")
            if not isinstance(raw_spec, dict):
                raise ValueError("缺少 canonicalSpec")
            spec = PersonaSpec.from_dict(raw_spec)
            validation = PersonaSpecValidator().validate(spec)
            normalized_prompt = PersonaCompiler().compile(spec)
            report = evaluate_persona(spec, normalized_prompt)
            conversation_report = evaluate_conversation_samples(
                spec, payload.get("conversationSamples")
            )
            judge_report = getattr(self, "judge", PersonaJudge(None)).evaluate(
                spec, normalized_prompt
            )
            report["judgeReport"] = judge_report
            report["conversationReport"] = conversation_report
            report["validationReport"] = validation.to_dict()
            report["normalizedRuntimePrompt"] = normalized_prompt
            if (
                judge_report["status"] == "failed"
                or conversation_report["status"] == "failed"
                or not validation.valid
            ):
                report["status"] = "failed"
            metrics.observe_ms(
                "companion_persona_test_duration_ms",
                (perf_counter() - started) * 1000,
                status=report["status"],
            )
            return web.json_response(report, dumps=lambda item: json.dumps(item, ensure_ascii=False))
        except web.HTTPException:
            raise
        except Exception as error:
            metrics.observe_ms(
                "companion_persona_test_duration_ms",
                (perf_counter() - started) * 1000,
                status="failed",
            )
            return web.json_response({"error": self._safe_error(error)}, status=400)
