import math
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
    min_thickness_mm: float = Field(1.0, ge=0.4, le=10)
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
    usb_side: Literal["left", "right"] = "right"
    electronics_position: Literal["bottom", "top"] = "bottom"

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
        minimum_depth = self.electronics_minimum_depth_mm
        if self.depth_mm < minimum_depth:
            raise ValueError(f"USB-C side mount requires at least {minimum_depth} mm housing depth")
        if self.usb_mount_bottom_mm <= self.wall_mm or self.usb_mount_top_mm >= self.outer_height_mm - self.wall_mm:
            raise ValueError("Housing is too short for the USB-C side mount")
        if (
            self.dimmer_mount_bottom_mm - self.dimmer_end_wall_mm <= self.wall_mm
            or self.dimmer_mount_top_mm + self.dimmer_end_wall_mm >= self.outer_height_mm - self.wall_mm
        ):
            raise ValueError("Housing is too short for the touch dimmer mount")
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
        return 2 * (self.panel_horizontal_clip_count + self.panel_vertical_clip_count)

    @staticmethod
    def edge_clip_count(edge_length_mm: float) -> int:
        if edge_length_mm >= 175:
            return 4
        if edge_length_mm >= 125:
            return 3
        return 2

    @property
    def panel_horizontal_clip_count(self) -> int:
        return self.edge_clip_count(self.panel_width_mm)

    @property
    def panel_vertical_clip_count(self) -> int:
        return self.edge_clip_count(self.panel_height_mm)

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
    def back_snap_reach_mm(self) -> float:
        return 0.35

    @property
    def back_snap_width_mm(self) -> float:
        return 12.0

    @property
    def back_snap_count(self) -> int:
        return 2 * (
            self.edge_clip_count(self.outer_width_mm)
            + self.edge_clip_count(self.outer_height_mm)
        )

    @property
    def back_horizontal_snap_count(self) -> int:
        return self.edge_clip_count(self.outer_width_mm)

    @property
    def back_vertical_snap_count(self) -> int:
        return self.edge_clip_count(self.outer_height_mm)

    @property
    def body_depth_mm(self) -> float:
        """Body depth excluding the external plate of the fitted rear cover."""
        return self.depth_mm - self.back_thickness_mm

    # Measured USB-C breakout used by Litho. The opening is deliberately
    # smaller than the metal shell, so the thin bezel carries unplugging load.
    @property
    def usb_shell_width_mm(self) -> float:
        return 8.85

    @property
    def usb_shell_height_mm(self) -> float:
        return 3.12

    @property
    def usb_shell_length_mm(self) -> float:
        return 8.65

    @property
    def usb_board_width_mm(self) -> float:
        return 8.35

    @property
    def usb_board_length_mm(self) -> float:
        return 5.33

    @property
    def usb_board_thickness_mm(self) -> float:
        return 1.2

    @property
    def usb_total_length_mm(self) -> float:
        return 14.02

    @property
    def usb_fit_clearance_mm(self) -> float:
        return 0.25

    @property
    def usb_aperture_width_mm(self) -> float:
        return 8.5

    @property
    def usb_aperture_height_mm(self) -> float:
        return 2.8

    @property
    def usb_mount_center_y_mm(self) -> float:
        return self.body_depth_mm - self.electronics_rear_margin_mm

    @property
    def electronics_rear_margin_mm(self) -> float:
        # Keeps the pockets and their wedge slots clear of the rear-cover lip.
        return 12.5

    @property
    def usb_mount_center_z_mm(self) -> float:
        return 12.0 if self.electronics_position == "bottom" else self.outer_height_mm - 12.0

    @property
    def usb_bezel_mm(self) -> float:
        # Thin enough for a USB-C plug to seat fully through the side wall.
        return 0.8

    @property
    def usb_pocket_wall_mm(self) -> float:
        return 2.4

    # Shallow icons engraved on the outside of the side wall mark the port
    # and the spot to touch, which is the measured centre of the antenna.
    @property
    def icon_engrave_depth_mm(self) -> float:
        return 0.4

    @property
    def electronics_direction(self) -> int:
        """Sign of the height axis pointing from the USB-C port to the dimmer."""
        return 1 if self.electronics_position == "bottom" else -1

    @property
    def usb_icon_center_z_mm(self) -> float:
        return self.usb_mount_center_z_mm + 6.5 * self.electronics_direction

    @property
    def touch_antenna_offset_mm(self) -> float:
        return 29.5

    @property
    def touch_icon_center_z_mm(self) -> float:
        return self.usb_mount_center_z_mm + self.touch_antenna_offset_mm * self.electronics_direction

    @property
    def usb_slot_clearance_mm(self) -> float:
        # Tighter than the general fit: the shell must not rock in its slot.
        return 0.15

    @property
    def usb_pocket_half_height_mm(self) -> float:
        return (self.usb_shell_height_mm + 2 * self.usb_slot_clearance_mm) / 2

    @property
    def usb_mount_bottom_mm(self) -> float:
        return self.usb_mount_center_z_mm - self.usb_pocket_half_height_mm - self.usb_pocket_wall_mm

    @property
    def usb_mount_top_mm(self) -> float:
        return self.usb_mount_center_z_mm + self.usb_pocket_half_height_mm + self.usb_pocket_wall_mm

    @property
    def electronics_pocket_floor_mm(self) -> float:
        return 1.6

    @property
    def electronics_pocket_floor_y_mm(self) -> float:
        """Underside of both push-in pockets, measured from the housing front."""
        shell_half = (self.usb_shell_width_mm + 2 * self.usb_fit_clearance_mm) / 2
        return self.usb_mount_center_y_mm - shell_half - self.electronics_pocket_floor_mm

    @property
    def electronics_keepout_y_mm(self) -> float:
        """Depth reserved for the Litho panel and its flexing clips."""
        return (
            self.front_thickness_mm + self.panel_thickness_mm + self.panel_clip_clearance_mm
            + self.panel_clip_ramp_height_mm + self.panel_clip_end_relief_mm
        )

    @property
    def electronics_minimum_depth_mm(self) -> int:
        pocket_stack = self.usb_mount_center_y_mm - self.electronics_pocket_floor_y_mm + self.electronics_rear_margin_mm
        return math.ceil(round(self.electronics_keepout_y_mm + pocket_stack + self.back_thickness_mm, 6))

    @property
    def dimmer_board_width_mm(self) -> float:
        return 10.08

    @property
    def dimmer_board_length_mm(self) -> float:
        return 37.04

    @property
    def dimmer_board_thickness_mm(self) -> float:
        return 1.2

    @property
    def dimmer_spring_height_mm(self) -> float:
        return 10.11

    @property
    def dimmer_overall_depth_mm(self) -> float:
        return 12.65

    @property
    def dimmer_spring_preload_mm(self) -> float:
        # Light contact only; the spring is an antenna, not a structural clamp.
        return 0.4

    # One printed wedge locks each pocket: it is pushed in from the open
    # interior, across the top of the part, until its taper jams in the slot.
    @property
    def wedge_slot_height_mm(self) -> float:
        return 2.0

    @property
    def wedge_groove_mm(self) -> float:
        return 0.8

    @property
    def wedge_slot_width_mm(self) -> float:
        # Independent of the USB-C slot fit, so wedges keep their size.
        return self.usb_shell_height_mm + 2 * self.usb_fit_clearance_mm + 2 * self.wedge_groove_mm

    @property
    def wedge_width_mm(self) -> float:
        return self.wedge_slot_width_mm - 0.3

    @property
    def wedge_length_mm(self) -> float:
        return 11.0

    @property
    def wedge_tip_thickness_mm(self) -> float:
        return 1.4

    @property
    def wedge_head_thickness_mm(self) -> float:
        return 2.4

    # Frame only: wedge sockets on the shelf beside the panel pocket. Each
    # wedge is pushed towards the wall until it stops, leaving its tail over
    # the 2 mm panel flange as a rigid stop behind the flexible clips.
    @property
    def panel_lock_shelf_mm(self) -> float:
        """Flat shelf between the panel pocket and the inner wall."""
        return self.panel_x0_mm - self.clearance_mm / 2 - self.wall_mm

    @property
    def panel_lock_depth_mm(self) -> float:
        return min(self.panel_lock_shelf_mm, 7.0)

    @property
    def panel_lock_pier_mm(self) -> float:
        return 2.4

    @property
    def panel_lock_gap_mm(self) -> float:
        # Play between the seated panel and the underside of a wedge.
        return 0.1

    def _panel_lock_centers(self, start: float, span: float, clip_count: int) -> list[float]:
        if self.kind != "frame" or self.panel_lock_shelf_mm < 4.0:
            return []
        pitch = span / (clip_count + 1)
        clip_half = min(self.panel_clip_width_mm, pitch * 0.8) / 2
        block_half = self.wedge_slot_width_mm / 2 + self.panel_lock_pier_mm
        if pitch / 2 - clip_half - block_half < 1.0:
            return []
        # Midway between neighbouring clips, clear of their flex reliefs.
        return [start + pitch * (index + 0.5) for index in range(1, clip_count)]

    @property
    def panel_horizontal_lock_centers_mm(self) -> list[float]:
        return self._panel_lock_centers(self.panel_x0_mm, self.panel_width_mm, self.panel_horizontal_clip_count)

    @property
    def panel_vertical_lock_centers_mm(self) -> list[float]:
        return self._panel_lock_centers(self.panel_z0_mm, self.panel_height_mm, self.panel_vertical_clip_count)

    @property
    def panel_lock_count(self) -> int:
        return 2 * (len(self.panel_horizontal_lock_centers_mm) + len(self.panel_vertical_lock_centers_mm))

    @property
    def panel_wedge_length_mm(self) -> float:
        # Seated against the socket end, the tail covers 1.4 mm of the flange.
        return self.panel_lock_depth_mm + 1.6

    @property
    def panel_wedge_taper(self) -> float:
        return 0.15

    @property
    def panel_wedge_tip_thickness_mm(self) -> float:
        # Jams in the 2 mm socket about 0.5 mm before reaching its end.
        return self.wedge_slot_height_mm - self.panel_wedge_taper * (self.panel_lock_depth_mm - 0.5)

    @property
    def panel_wedge_head_thickness_mm(self) -> float:
        return self.panel_wedge_tip_thickness_mm + self.panel_wedge_taper * self.panel_wedge_length_mm

    @property
    def panel_wedge_count(self) -> int:
        return self.panel_lock_count + 2 if self.panel_lock_count else 0

    @property
    def wedge_count(self) -> int:
        # USB-C pocket, both dimmer channels, and one spare.
        return 4

    @property
    def dimmer_end_wall_mm(self) -> float:
        return 2.4

    @property
    def dimmer_mount_bottom_mm(self) -> float:
        if self.electronics_position == "bottom":
            return self.usb_mount_top_mm + 4.0
        return self.usb_mount_bottom_mm - 4.0 - self.dimmer_board_length_mm - 0.5

    @property
    def dimmer_mount_top_mm(self) -> float:
        if self.electronics_position == "bottom":
            return self.dimmer_mount_bottom_mm + self.dimmer_board_length_mm + 0.5
        return self.usb_mount_bottom_mm - 4.0

    @property
    def dimmer_board_face_offset_mm(self) -> float:
        return self.dimmer_spring_height_mm - self.dimmer_spring_preload_mm
