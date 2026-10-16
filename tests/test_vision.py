"""Offline contracts for multimodal asset handling."""

from __future__ import annotations

import base64
import unittest

from showcase.adapters import InternModelAdapter
from showcase.vision import VisionAdapter, VisionInputError

PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cf00000004000101e2dd"
    "0000000049454e44ae426082"
)


class FakeVisionClient:
    model = "intern-vision-test"

    def __init__(self, response="看图结果"):
        self.response = response
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.response


class VisionAdapterTest(unittest.TestCase):
    def test_asset_reference_hashes_and_dimensions_without_content(self):
        client = FakeVisionClient()
        adapter = VisionAdapter(InternModelAdapter(client))
        asset = adapter.prepare_asset(base64.b64encode(PNG_1X1).decode("ascii"), mime_type="image/png")
        reference = asset.reference()
        self.assertEqual("image/png", reference["mime_type"])
        self.assertEqual(len(PNG_1X1), reference["size_bytes"])
        self.assertEqual(1, reference["width"])
        self.assertEqual(1, reference["height"])
        self.assertNotIn("content", reference)
        result = adapter.complete("图中有几个点？", asset)
        self.assertEqual("completed", result.status)
        self.assertEqual("implemented", result.feature_status)
        self.assertEqual("看图结果", result.response.text)
        content = client.calls[0][0][0]["content"]
        self.assertEqual("text", content[0]["type"])
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_invalid_and_oversized_assets_have_stable_categories(self):
        adapter = VisionAdapter(InternModelAdapter(FakeVisionClient()), max_image_bytes=4)
        with self.assertRaisesRegex(VisionInputError, "image_too_large"):
            adapter.prepare_asset(PNG_1X1, mime_type="image/png")
        with self.assertRaisesRegex(VisionInputError, "image_mime_not_allowed"):
            adapter.prepare_asset(b"text", mime_type="text/plain")

    def test_provider_failure_is_unavailable_without_leaking_image(self):
        class FailingClient(FakeVisionClient):
            def chat(self, messages, **kwargs):
                raise RuntimeError("provider secret")

        adapter = VisionAdapter(InternModelAdapter(FailingClient()))
        asset = adapter.prepare_asset(PNG_1X1, mime_type="image/png")
        result = adapter.complete("题目", asset)
        self.assertEqual("unavailable", result.status)
        self.assertEqual("adapter_error", result.error_category)
        self.assertNotIn(base64.b64encode(PNG_1X1).decode("ascii"), repr(result))


if __name__ == "__main__":
    unittest.main()
