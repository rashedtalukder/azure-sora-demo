#    Copyright 2025 Rashed Talukder
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""
Validation utilities for Rashed's Sora SDK.
"""

from typing import Tuple, List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Supported video resolutions (width, height)
SUPPORTED_RESOLUTIONS = [
    (480, 480),   # 480x480p
    (480, 854),   # 480x854p
    (854, 480),   # 854x480p
    (720, 720),   # 720x720p
    (720, 1280),  # 720x1280p
    (1280, 720),  # 1280x720p
    (1080, 1080),  # 1080x1080p
    (1080, 1920),  # 1080x1920p
    (1920, 1080)  # 1920x1080p
]

# Duration limits (all resolutions now support 1-20 seconds)
MIN_DURATION = 1
MAX_DURATION = 20

# Maximum number of variants based on resolution category
MAX_VARIANTS = {
    '1080p': 1,      # 1080p resolutions: disabled (1 variant only)
    '720p': 2,       # 720p resolutions: max 2 variants
    'other': 4       # Other resolutions: max 4 variants
}

# Maximum number of pending tasks allowed
MAX_PENDING_TASKS = 1


class ValidationError(Exception):
    """Exception raised for validation errors in the Sora SDK."""
    pass


def _get_resolution_category(width: int, height: int) -> str:
    """
    Determine the resolution category for variant limits.

    Args:
        width: Video width in pixels
        height: Video height in pixels

    Returns:
        Resolution category: '1080p', '720p', or 'other'
    """
    if width >= 1080 or height >= 1080:
        return '1080p'
    elif width >= 720 or height >= 720:
        return '720p'
    else:
        return 'other'


def validate_resolution(width: int, height: int) -> Tuple[int, int]:
    """
    Validate that the resolution is supported by the Sora API.

    Args:
        width: Video width in pixels
        height: Video height in pixels

    Returns:
        Tuple of validated (width, height)

    Raises:
        ValidationError: If the resolution is not supported
    """
    if (width, height) not in SUPPORTED_RESOLUTIONS:
        supported_str = ", ".join(
            [f"{w}x{h}" for w, h in SUPPORTED_RESOLUTIONS])
        raise ValidationError(
            f"Resolution {width}x{height} is not supported. Supported resolutions: {supported_str}"
        )

    return width, height


def validate_duration(width: int, height: int, duration: int) -> int:
    """
    Validate that the duration is within the allowed limits.

    Args:
        width: Video width in pixels (not used in new API but kept for compatibility)
        height: Video height in pixels (not used in new API but kept for compatibility)
        duration: Video duration in seconds

    Returns:
        Validated duration in seconds

    Raises:
        ValidationError: If the duration is outside the allowed range
    """
    if duration < MIN_DURATION:
        raise ValidationError(
            f"Duration must be at least {MIN_DURATION} second. Got {duration} seconds.")

    if duration > MAX_DURATION:
        raise ValidationError(
            f"Duration must be at most {MAX_DURATION} seconds. Got {duration} seconds.")

    return duration


def validate_variants(width: int, height: int, variants: int) -> int:
    """
    Validate that the number of variants is within the allowed limits for the resolution.

    Args:
        width: Video width in pixels
        height: Video height in pixels
        variants: Number of video variants to generate

    Returns:
        Validated number of variants

    Raises:
        ValidationError: If the number of variants exceeds the maximum allowed
    """
    if variants <= 0:
        raise ValidationError("Number of variants must be greater than 0.")

    category = _get_resolution_category(width, height)
    max_variants = MAX_VARIANTS[category]

    if variants > max_variants:
        if category == '1080p':
            raise ValidationError(
                f"1080p resolutions only support 1 variant. Got {variants} variants."
            )
        elif category == '720p':
            raise ValidationError(
                f"720p resolutions support maximum {max_variants} variants. Got {variants} variants."
            )
        else:
            raise ValidationError(
                f"This resolution supports maximum {max_variants} variants. Got {variants} variants."
            )

    return variants


def get_max_duration_for_resolution(width: int, height: int) -> int:
    """
    Get the maximum duration allowed for a given resolution.

    Args:
        width: Video width in pixels
        height: Video height in pixels

    Returns:
        Maximum duration in seconds
    """
    return MAX_DURATION


def get_max_variants_for_resolution(width: int, height: int) -> int:
    """
    Get the maximum variants allowed for a given resolution.

    Args:
        width: Video width in pixels
        height: Video height in pixels

    Returns:
        Maximum number of variants
    """
    category = _get_resolution_category(width, height)
    return MAX_VARIANTS[category]


def validate_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the complete video generation request.

    Args:
        request_data: Video generation request data

    Returns:
        Validated request data

    Raises:
        ValidationError: If any validation fails
    """
    width = request_data.get('width')
    height = request_data.get('height')
    n_seconds = request_data.get('n_seconds')
    n_variants = request_data.get('n_variants', 1)

    validate_resolution(width, height)
    validate_duration(width, height, n_seconds)
    validate_variants(width, height, n_variants)

    return request_data
