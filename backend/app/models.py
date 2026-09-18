from typing import Literal

from pydantic import BaseModel, Field, model_validator

MOUNTING_FLANGE_WIDTH_MM = 2.0
MOUNTING_FLANGE_HEIGHT_MM = 1.6


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
    max_thickness_mm: float = Field(4.0, gt=0.4, le=22)
    gamma: float = Field(1.0, ge=0.1, le=5)
    brightness: float = Field(1.0, ge=0.25, le=2)
    contrast: float = Field(1.25, ge=0.25, le=3)
    nozzle_diameter_mm: Literal[0.2, 0.4] = 0.4
    quality_profile: Literal["economic", "optimal", "maximum"] = "maximum"
    resolution: int | None = Field(None, ge=24, le=2000, description="Optional legacy override; UI profiles derive resolution from a physical XY sample pitch")
    orientation: Literal["portrait", "landscape"] = Field("landscape", description="Must match the final model dimensions")
    border_width_mm: float = Field(0, ge=0, le=20)
    border_widths_mm: BorderWidths | None = None
    border_height_mm: float | None = Field(None, ge=0.4, le=20)
    mounting_flange: bool = Field(False, description="Standard 2.0 mm internal mounting rim with a fixed 1.6 mm thickness")
    removable_support: bool = False
    invert: bool = False
    mirror: bool = Field(False, description="Creative mirror shown in preview; mesh applies the inverse technical orientation")
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
            height = self.effective_border_height
            if height > 20:
                raise ValueError("border_height_mm cannot exceed 20 mm")
            if height < 2 * self.nozzle_diameter_mm:
                raise ValueError("border_height_mm must be at least two nozzle widths")
        return self

    @property
    def effective_border_height(self) -> float:
        if self.mounting_flange:
            return MOUNTING_FLANGE_HEIGHT_MM
        return self.border_height_mm or self.max_thickness_mm

    @property
    def border_top_mm(self) -> float:
        if self.mounting_flange:
            return MOUNTING_FLANGE_WIDTH_MM
        return self.border_widths_mm.top if self.border_widths_mm else self.border_width_mm

    @property
    def border_right_mm(self) -> float:
        if self.mounting_flange:
            return MOUNTING_FLANGE_WIDTH_MM
        return self.border_widths_mm.right if self.border_widths_mm else self.border_width_mm

    @property
    def border_bottom_mm(self) -> float:
        if self.mounting_flange:
            return MOUNTING_FLANGE_WIDTH_MM
        return self.border_widths_mm.bottom if self.border_widths_mm else self.border_width_mm

    @property
    def border_left_mm(self) -> float:
        if self.mounting_flange:
            return MOUNTING_FLANGE_WIDTH_MM
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


class HousingParams(BaseModel):
    kind: Literal["box", "frame"] = "box"
    panel_width_mm: float = Field(150, ge=20, le=250)
    panel_height_mm: float = Field(100, ge=20, le=250)
    panel_thickness_mm: Literal[1.6] = 1.6
    clearance_mm: float = Field(0.4, ge=0.2, le=0.8)
    depth_mm: float = Field(40, ge=20, le=80)
    wall_mm: float = Field(2.4, ge=2.4, le=5.0)
    frame_border_mm: float = Field(12, ge=5, le=25)
    bezel_overlap_mm: float = Field(1.2, ge=0.6, le=1.8)
    back_thickness_mm: float = Field(2.4, ge=1.6, le=5.0)
    cable_width_mm: float = Field(12, ge=6, le=25)
    cable_height_mm: float = Field(8, ge=4, le=20)

    @model_validator(mode="after")
    def printable_relations(self):
        if self.panel_pocket_depth_mm > 4.8:
            raise ValueError("Panel pocket is too deep")
        if self.bezel_overlap_mm >= min(self.panel_width_mm, self.panel_height_mm) / 2:
            raise ValueError("Bezel overlap is too large for the panel")
        if self.bezel_overlap_mm > MOUNTING_FLANGE_WIDTH_MM:
            raise ValueError("Bezel overlap cannot exceed the 2 mm Litho mounting flange")
        if self.outer_width_mm > 256 or self.outer_height_mm > 256:
            raise ValueError("Housing footprint must fit within 256 x 256 mm")
        if self.cable_width_mm >= self.outer_width_mm - 2 * self.wall_mm:
            raise ValueError("Cable opening is too wide")
        if self.cable_height_mm >= self.outer_height_mm / 3:
            raise ValueError("Cable opening is too tall")
        return self

    @property
    def panel_pocket_depth_mm(self) -> float:
        return self.panel_thickness_mm + self.clearance_mm

    @property
    def outer_margin_mm(self) -> float:
        return self.frame_border_mm if self.kind == "frame" else self.wall_mm + self.clearance_mm

    @property
    def outer_width_mm(self) -> float:
        return self.panel_width_mm + 2 * self.outer_margin_mm

    @property
    def outer_height_mm(self) -> float:
        return self.panel_height_mm + 2 * self.outer_margin_mm

    @property
    def panel_x0_mm(self) -> float:
        return self.outer_margin_mm

    @property
    def panel_x1_mm(self) -> float:
        return self.panel_x0_mm + self.panel_width_mm

    @property
    def panel_z0_mm(self) -> float:
        return self.outer_margin_mm

    @property
    def panel_z1_mm(self) -> float:
        return self.panel_z0_mm + self.panel_height_mm

    @property
    def front_thickness_mm(self) -> float:
        return self.wall_mm

    @property
    def effective_bezel_overlap_mm(self) -> float:
        return self.bezel_overlap_mm if self.kind == "frame" else 0.8

    @property
    def panel_clip_count(self) -> int:
        return 6 if max(self.panel_width_mm, self.panel_height_mm) >= 175 else 4

    @property
    def panel_clip_width_mm(self) -> float:
        return 9.0

    @property
    def panel_clip_reach_mm(self) -> float:
        return 0.4

    @property
    def panel_clip_clearance_mm(self) -> float:
        return 0.15

    @property
    def panel_clip_ramp_height_mm(self) -> float:
        return 0.8

    @property
    def panel_clip_flex_thickness_mm(self) -> float:
        return 0.8

    @property
    def panel_clip_relief_mm(self) -> float:
        return 0.6

    @property
    def panel_clip_end_relief_mm(self) -> float:
        return 0.6

    @property
    def rear_opening_width_mm(self) -> float:
        return self.outer_width_mm - 2 * self.wall_mm

    @property
    def rear_opening_height_mm(self) -> float:
        return self.outer_height_mm - 2 * self.wall_mm

    @property
    def back_lip_mm(self) -> float:
        return 1.2

    @property
    def back_lip_depth_mm(self) -> float:
        return 4.0

    @property
    def back_clearance_mm(self) -> float:
        return 0.15

    @property
    def body_depth_mm(self) -> float:
        """Body depth excluding the external plate of the fitted rear cover."""
        return self.depth_mm - self.back_thickness_mm
