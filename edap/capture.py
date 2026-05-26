from __future__ import annotations

from dataclasses import dataclass

from edap.config import CaptureRegionConfig, ScreenConfig


@dataclass(frozen=True)
class PixelBounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def to_dict(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "width": self.width,
            "height": self.height,
        }


@dataclass(frozen=True)
class CaptureLayout:
    reference_width: int
    reference_height: int
    mode: str
    base_region: CaptureRegionConfig
    base_bounds: PixelBounds
    named_regions: dict[str, PixelBounds]

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "reference_width": self.reference_width,
            "reference_height": self.reference_height,
            "base_region": region_to_dict(self.base_region),
            "base_bounds": self.base_bounds.to_dict(),
            "regions": {
                name: bounds.to_dict()
                for name, bounds in sorted(self.named_regions.items())
            },
        }


def region_to_dict(region: CaptureRegionConfig) -> dict[str, float]:
    return {
        "left": region.left,
        "top": region.top,
        "right": region.right,
        "bottom": region.bottom,
    }


def scaled_dimensions(screen: ScreenConfig) -> tuple[int, int]:
    return (
        int(screen.resolution_width * screen.scale),
        int(screen.resolution_height * screen.scale),
    )


def bounds_from_region(region: CaptureRegionConfig, width: int, height: int) -> PixelBounds:
    return PixelBounds(
        left=round(width * region.left),
        top=round(height * region.top),
        right=round(width * region.right),
        bottom=round(height * region.bottom),
    )


def build_capture_layout(screen: ScreenConfig) -> CaptureLayout:
    width, height = scaled_dimensions(screen)
    base_bounds = bounds_from_region(screen.capture.base_region, width, height)
    named_regions = {
        name: bounds_from_region(region, base_bounds.width, base_bounds.height)
        for name, region in screen.capture.regions.items()
    }
    return CaptureLayout(
        reference_width=width,
        reference_height=height,
        mode=screen.capture.mode,
        base_region=screen.capture.base_region,
        base_bounds=base_bounds,
        named_regions=named_regions,
    )
