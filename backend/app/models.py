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


class LithophaneParams(BaseModel):
    width_mm: float = Field(150, ge=20, le=256, description="Preset dimension: 100x150, 130x180 or 150x200 mm, in either orientation")
    height_mm: float = Field(100, ge=20, le=256, description="Preset dimension: 100x150, 130x180 or 150x200 mm, in either orientation")
    min_thickness_mm: float = Field(0.8, ge=0.4, le=10)
    max_thickness_mm: float = Field(3.2, gt=0.4, le=22)
    gamma: float = Field(1.0, ge=0.1, le=5)
    brightness: float = Field(1.0, ge=0.25, le=2)
    contrast: float = Field(1.0, ge=0.25, le=3)
    resolution: int = Field(180, ge=24, le=600, description="Points on the longest edge")
    orientation: Literal["portrait", "landscape"] = Field("landscape", description="Must match the selected preset dimensions")
    border_width_mm: float = Field(0, ge=0, le=20)
    border_height_mm: float | None = Field(None, ge=0, le=20)
    invert: bool = False
    mirror: bool = False
    crop: Crop = Field(default_factory=Crop)

    @model_validator(mode="after")
    def physical_relations(self):
        dimensions = tuple(sorted((self.width_mm, self.height_mm)))
        if dimensions not in ((100.0, 150.0), (130.0, 180.0), (150.0, 200.0)):
            raise ValueError("Model size must be one of: 100x150, 130x180 or 150x200 mm")
        if (self.orientation == "landscape") != (self.width_mm > self.height_mm):
            raise ValueError("orientation must match model dimensions")
        if self.width_mm + 2 * self.border_width_mm > 256 or self.height_mm + 2 * self.border_width_mm > 256:
            raise ValueError("Model with border must fit within 256x256 mm")
        if self.max_thickness_mm <= self.min_thickness_mm:
            raise ValueError("max_thickness_mm must exceed min_thickness_mm")
        if self.max_thickness_mm - self.min_thickness_mm > 12:
            raise ValueError("Thickness range cannot exceed 12 mm")
        if self.border_width_mm > 0:
            height = self.border_height_mm or self.max_thickness_mm
            if height > 20:
                raise ValueError("border_height_mm cannot exceed 20 mm")
            if height < self.max_thickness_mm:
                raise ValueError("border_height_mm must be at least max_thickness_mm")
        return self

    @property
    def effective_border_height(self) -> float:
        return self.border_height_mm or self.max_thickness_mm
