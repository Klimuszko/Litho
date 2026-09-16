from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Crop(BaseModel):
    x: float = Field(0, ge=0, le=1)
    y: float = Field(0, ge=0, le=1)
    width: float = Field(1, gt=0, le=1)
    height: float = Field(1, gt=0, le=1)

    @model_validator(mode="after")
    def inside_image(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Crop must remain inside the image")
        return self


class BorderWidths(BaseModel):
    top: float = Field(0, ge=0, le=20)
    right: float = Field(0, ge=0, le=20)
    bottom: float = Field(0, ge=0, le=20)
    left: float = Field(0, ge=0, le=20)


class LithophaneParams(BaseModel):
    width_mm: float = Field(150, ge=20, le=256, description="Final model width, including the optional border")
    height_mm: float = Field(100, ge=20, le=256, description="Final model height, including the optional border")
    min_thickness_mm: float = Field(0.6, ge=0.4, le=10)
    max_thickness_mm: float = Field(2.0, gt=0.4, le=22)
    gamma: float = Field(1.0, ge=0.1, le=5)
    brightness: float = Field(1.0, ge=0.25, le=2)
    contrast: float = Field(1.0, ge=0.25, le=3)
    nozzle_diameter_mm: Literal[0.2, 0.4] = 0.4
    quality_profile: Literal["economic", "optimal", "maximum"] = "optimal"
    resolution: int | None = Field(None, ge=24, le=2000, description="Optional legacy override; UI profiles derive resolution from a physical XY sample pitch")
    orientation: Literal["portrait", "landscape"] = Field("landscape", description="Must match the final model dimensions")
    border_width_mm: float = Field(0, ge=0, le=20)
    border_widths_mm: BorderWidths | None = None
    border_height_mm: float | None = Field(None, ge=0, le=20)
    removable_support: bool = False
    invert: bool = False
    mirror: bool = False
    rotation_degrees: float = Field(0, ge=-360, le=360)
    crop: Crop = Field(default_factory=Crop)

    @model_validator(mode="after")
    def physical_relations(self):
        if self.width_mm != self.height_mm and (self.orientation == "landscape") != (self.width_mm > self.height_mm):
            raise ValueError("orientation must match model dimensions")
        if self.border_left_mm + self.border_right_mm >= self.width_mm:
            raise ValueError("horizontal border widths leave no room for the image")
        if self.border_top_mm + self.border_bottom_mm >= self.height_mm:
            raise ValueError("vertical border widths leave no room for the image")
        if self.max_thickness_mm <= self.min_thickness_mm:
            raise ValueError("max_thickness_mm must exceed min_thickness_mm")
        if self.max_thickness_mm - self.min_thickness_mm > 12:
            raise ValueError("Thickness range cannot exceed 12 mm")
        if self.has_border:
            height = self.border_height_mm or self.max_thickness_mm
            if height > 20:
                raise ValueError("border_height_mm cannot exceed 20 mm")
            if height < self.max_thickness_mm:
                raise ValueError("border_height_mm must be at least max_thickness_mm")
        return self

    @property
    def effective_border_height(self) -> float:
        return self.border_height_mm or self.max_thickness_mm

    @property
    def border_top_mm(self) -> float:
        return self.border_widths_mm.top if self.border_widths_mm else self.border_width_mm

    @property
    def border_right_mm(self) -> float:
        return self.border_widths_mm.right if self.border_widths_mm else self.border_width_mm

    @property
    def border_bottom_mm(self) -> float:
        return self.border_widths_mm.bottom if self.border_widths_mm else self.border_width_mm

    @property
    def border_left_mm(self) -> float:
        return self.border_widths_mm.left if self.border_widths_mm else self.border_width_mm

    @property
    def has_border(self) -> bool:
        return any(value > 0 for value in (self.border_top_mm, self.border_right_mm, self.border_bottom_mm, self.border_left_mm))

    @property
    def image_width_mm(self) -> float:
        return self.width_mm - self.border_left_mm - self.border_right_mm

    @property
    def image_height_mm(self) -> float:
        return self.height_mm - self.border_top_mm - self.border_bottom_mm

    @property
    def sample_pitch_mm(self) -> float:
        pitches = {
            0.2: {"economic": 0.20, "optimal": 0.125, "maximum": 0.10},
            0.4: {"economic": 0.40, "optimal": 0.25, "maximum": 0.20},
        }
        return pitches[self.nozzle_diameter_mm][self.quality_profile]

    @property
    def line_width_mm(self) -> float:
        return {0.2: 0.22, 0.4: 0.44}[self.nozzle_diameter_mm]

    @property
    def effective_resolution(self) -> int:
        if self.resolution is not None:
            return self.resolution
        return round(max(self.image_width_mm, self.image_height_mm) / self.sample_pitch_mm)

    @property
    def effective_sample_pitch_mm(self) -> float:
        return max(self.image_width_mm, self.image_height_mm) / self.effective_resolution
