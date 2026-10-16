"""Profile constants and the product import boundary."""

from __future__ import annotations

OFFICIAL_PROFILE = "official"
SHOWCASE_PROFILE = "showcase_mvp"


class ProfileBoundaryError(ValueError):
    """Raised when an official run is routed into the product service."""

    category = "profile_not_supported"

    def __init__(self, profile: str) -> None:
        super().__init__(f"{self.category}: {profile!r}")
        self.profile = profile


def ensure_showcase_profile(profile: str) -> None:
    """Keep the Run application service explicitly scoped to showcase MVP."""

    if profile != SHOWCASE_PROFILE:
        raise ProfileBoundaryError(profile)
