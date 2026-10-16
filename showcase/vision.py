"""Intern multimodal input adapter and redacted image asset references."""

from __future__ import annotations

import base64
import binascii
import hashlib
import struct
from dataclasses import dataclass
from typing import Any

from .adapters import AdapterError, InternModelAdapter, ModelResponse

MAX_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg", "image/webp"}


class VisionInputError(ValueError):
    """Stable, user-actionable image input error."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class ImageAsset:
    """Decoded image held only for the duration of one adapter call."""

    asset_id: str
    mime_type: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None
    _content: bytes

    def reference(self) -> dict[str, Any]:
        """Return the safe event/Evidence reference; never include binary content."""

        return {
            "asset_id": self.asset_id,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
        }

    def data_url(self) -> str:
        """Build the provider-only data URL at the final adapter boundary."""

        encoded = base64.b64encode(self._content).decode("ascii")
        return f"data:{self.mime_type};base64,{encoded}"


@dataclass(frozen=True)
class VisionResult:
    """Multimodal result with explicit implementation/unavailable label."""

    status: str
    feature_status: str
    asset_reference: dict[str, Any]
    response: ModelResponse | None = None
    error_category: str | None = None


class VisionAdapter:
    """Send text plus validated image content through the Intern adapter."""

    def __init__(
        self,
        model: InternModelAdapter,
        *,
        max_image_bytes: int = MAX_IMAGE_BYTES,
    ) -> None:
        self.model = model
        self.max_image_bytes = max_image_bytes

    def prepare_asset(
        self,
        content: bytes | str,
        *,
        mime_type: str | None = None,
        asset_id: str | None = None,
    ) -> ImageAsset:
        """Decode and validate one image without retaining it in product state."""

        raw_mime = mime_type
        if isinstance(content, str):
            if content.startswith("data:"):
                header, _, encoded = content.partition(",")
                raw_mime = raw_mime or header[5:].split(";", 1)[0]
                content = encoded
            try:
                content = base64.b64decode(content, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise VisionInputError("image_base64_invalid") from exc
        if not isinstance(content, bytes):
            raise VisionInputError("image_content_must_be_bytes_or_base64")
        if len(content) > self.max_image_bytes:
            raise VisionInputError("image_too_large")
        mime = raw_mime or _detect_mime(content)
        if mime not in ALLOWED_IMAGE_MIME:
            raise VisionInputError("image_mime_not_allowed")
        detected = _detect_mime(content)
        if detected != mime and not (mime == "image/jpeg" and detected == "image/jpeg"):
            raise VisionInputError("image_format_mismatch")
        width, height = _dimensions(content, mime)
        digest = hashlib.sha256(content).hexdigest()
        return ImageAsset(
            asset_id=asset_id or f"asset_{digest[:16]}",
            mime_type=mime,
            size_bytes=len(content),
            sha256=digest,
            width=width,
            height=height,
            _content=content,
        )

    def complete(self, problem: str, asset: ImageAsset) -> VisionResult:
        """Call Intern with a normalized text/image content array."""

        if not isinstance(problem, str) or not problem.strip():
            raise VisionInputError("problem_must_be_non_empty")
        try:
            response = self.model.complete(
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": problem.strip()},
                            {"type": "image_url", "image_url": {"url": asset.data_url()}},
                        ],
                    }
                ]
            )
        except AdapterError as exc:
            return VisionResult(
                status="unavailable",
                feature_status="unavailable",
                asset_reference=asset.reference(),
                error_category=exc.category,
            )
        return VisionResult(
            status="completed",
            feature_status="implemented",
            asset_reference=asset.reference(),
            response=response,
        )


def _detect_mime(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _dimensions(content: bytes, mime: str) -> tuple[int | None, int | None]:
    if mime == "image/png" and len(content) >= 24:
        width, height = struct.unpack(">II", content[16:24])
        return width, height
    return None, None


__all__ = ["ImageAsset", "VisionAdapter", "VisionInputError", "VisionResult"]
