from __future__ import annotations

import os
import unittest
from unittest import mock

import audit_log


class AuditLogRedactionTests(unittest.TestCase):
    def test_new_request_id_is_unique_hex(self) -> None:
        first = audit_log.new_request_id()
        second = audit_log.new_request_id()

        self.assertEqual(len(first), 32)
        self.assertEqual(len(second), 32)
        self.assertNotEqual(first, second)
        int(first, 16)
        int(second, 16)

    def test_redact_payload_redacts_nested_sensitive_keys_and_truncates(self) -> None:
        with mock.patch.dict(os.environ, {"AUDIT_MAX_FIELD_CHARS": "6"}, clear=False):
            payload = {
                "apiKey": "abcdef123456",
                "nested": {
                    "token": "secret-token",
                    "profile": [{"password": "p@ssw0rd"}, {"phone": "0909123456"}],
                },
                "public": "0123456789",
            }
            redacted = audit_log.redact_payload(payload)

        self.assertEqual(redacted["apiKey"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["token"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["profile"][0]["password"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["profile"][1]["phone"], "[REDACTED]")
        self.assertTrue(redacted["public"].startswith("012345"))
        self.assertTrue(redacted["public"].endswith("...<truncated>"))
        self.assertEqual(payload["apiKey"], "abcdef123456")
