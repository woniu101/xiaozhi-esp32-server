import hashlib
import hmac
import io
import json
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from pathlib import Path

from aiohttp import web

from core.api.persona_handler import PersonaCompilerHandler


class FakeRequest:
    def __init__(self, headers, method="POST", path="/internal/companion/persona/compiler-info"):
        self.headers = headers
        self.method = method
        self.path = path


def make_archive() -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(
            "skill/meta.json",
            json.dumps(
                {
                    "name": "测试公众人物",
                    "slug": "public-test",
                    "version": "v1",
                    "persona_mode": "public-figure",
                },
                ensure_ascii=False,
            ),
        )
        archive.writestr(
            "skill/persona.md",
            "# 测试公众人物\n\n## Core Rules\n- 保持事实边界\n\n## Boundaries\n- 不虚构共同经历\n",
        )
    return stream.getvalue()


class PersonaCompilerApiTest(unittest.TestCase):
    def setUp(self):
        self.secret = "test-secret-value"
        self.handler = PersonaCompilerHandler.__new__(PersonaCompilerHandler)
        self.handler.enabled = True
        self.handler.secret = self.secret
        self.handler._nonces = {}
        self.handler._nonce_lock = threading.Lock()

    def _signed_request(self, body=b"{}", nonce=None):
        timestamp = str(int(time.time()))
        nonce = nonce or uuid.uuid4().hex
        path = "/internal/companion/persona/compiler-info"
        digest = hashlib.sha256(body).hexdigest()
        canonical = "\n".join((timestamp, nonce, "POST", path, digest))
        signature = hmac.new(self.secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return FakeRequest(
            {
                "X-Companion-Timestamp": timestamp,
                "X-Companion-Nonce": nonce,
                "X-Companion-Signature": signature,
            },
            path=path,
        )

    def test_hmac_replay_is_rejected(self):
        body = b"{}"
        request = self._signed_request(body)
        self.handler._verify(request, body)
        with self.assertRaises(web.HTTPUnauthorized):
            self.handler._verify(request, body)

    def test_compile_returns_publishable_canonical_persona(self):
        result = self.handler._compile_artifact(
            make_archive(),
            {
                "sourceUrl": "https://github.com/example/public-test",
                "sourceCommit": "a" * 40,
                "isRealPerson": True,
                "isPublicFigure": True,
            },
        )
        self.assertEqual(result["personaId"], "persona.celebrity.public-test")
        self.assertTrue(result["validationReport"]["valid"])
        self.assertTrue(result["publishable"])
        self.assertEqual(result["testReport"]["status"], "passed")
        self.assertEqual(
            result["canonicalSpec"]["relationship_policy"]["allowed_stages"],
            ["familiar", "friend", "ambiguous", "lover", "intimate"],
        )
        self.assertEqual(
            result["canonicalSpec"]["relationship_policy"]["recommended_mode"],
            "friend",
        )

if __name__ == "__main__":
    unittest.main()
