from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ParameterType = Literal["integer", "float", "boolean", "string", "enum"]
Visibility = Literal["private", "public", "unlisted", "system"]
ModuleStatus = Literal["draft", "published", "hidden", "blocked", "deleted"]
RenderStatus = Literal["queued", "running", "completed", "failed", "cancelled", "timed_out"]


class ScadParameter(BaseModel):
    id: str
    name: str
    label: str
    description: str = ""
    section: str = "General"
    type: ParameterType
    defaultValue: Any
    currentValue: Any
    min: float | int | None = None
    max: float | int | None = None
    step: float | int | None = None
    options: list[str] = Field(default_factory=list)
    order: int = 0
    hidden: bool = False
    advanced: bool = False
    unit: str = ""


class ModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="Other", min_length=1, max_length=80)
    visibility: Visibility = "private"


class ModuleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="Other", min_length=1, max_length=80)
    visibility: Visibility = "private"
    revision: int = Field(ge=1)


class VersionCreate(BaseModel):
    version_label: str = Field(default="", max_length=80)
    changelog: str = Field(default="", max_length=4000)


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parameters: dict[str, Any]


class PresetUpdate(PresetCreate):
    pass


class RenderCreate(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_format: Literal["stl", "3mf"] = "stl"
    mode: Literal["model", "metadata"] = "model"
    version_id: str | None = None


class ModerationRequest(BaseModel):
    action: Literal["hide", "unhide", "block", "unblock", "official", "unofficial"]


class PublishRequest(BaseModel):
    version_id: str | None = None
    visibility: Literal["public", "unlisted", "system"] = "public"


class SourceReplace(BaseModel):
    source: str = Field(min_length=1)
    filename: str = Field(default="main.scad", pattern=r"^[A-Za-z0-9_.-]+\.scad$")
    version_label: str = Field(default="", max_length=80)
    changelog: str = Field(default="", max_length=4000)


class ListQuery(BaseModel):
    scope: Literal["my", "public", "official", "all", "shared"] = "public"
    search: str = ""
    category: str = ""
    author: str = ""
    sort: Literal["updated", "newest", "name"] = "updated"

    @field_validator("search", "category", "author")
    @classmethod
    def trim(cls, value: str) -> str:
        return value.strip()[:120]
