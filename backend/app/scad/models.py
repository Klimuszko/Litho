from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ParameterType = Literal["integer", "float", "boolean", "string", "enum"]
Visibility = Literal["private", "public", "unlisted", "system"]
ModuleStatus = Literal["draft", "published", "hidden", "blocked", "deleted"]


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
    options: list[Any] = Field(default_factory=list)
    optionLabels: list[str] = Field(default_factory=list)
    order: int = 0
    hidden: bool = False
    advanced: bool = False
    unit: str = ""


class ModuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="Other", min_length=1, max_length=80)
    visibility: Visibility = "private"


class ModuleCodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="Other", min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=10 * 1024 * 1024)


class ModuleCodeUpdate(BaseModel):
    source: str = Field(min_length=1, max_length=10 * 1024 * 1024)
    version_label: str = Field(default="", max_length=80)
    changelog: str = Field(default="", max_length=4000)


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
    scope: Literal["my", "all"] = "all"
    search: str = ""
    category: str = ""
    author: str = ""
    sort: Literal["updated", "newest", "name"] = "updated"
    status: Literal["", "draft", "published", "blocked"] = ""

    @field_validator("search", "category", "author")
    @classmethod
    def trim(cls, value: str) -> str:
        return value.strip()[:120]
