"""Pydantic schemas for Model Registry."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# --- Model ---

class ModelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Slug-style name: my-custom-model")
    display_name: Optional[str] = None
    description: Optional[str] = None
    visibility: str = Field("private", pattern="^(private|department|organization)$")
    department_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class ModelUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[str] = Field(None, pattern="^(private|department|organization)$")
    department_id: Optional[str] = None
    tags: Optional[list[str]] = None


# --- Version ---

class VersionCreate(BaseModel):
    version: str = Field(..., min_length=1, max_length=50, description="Semver: 1.0.0")
    release_notes: Optional[str] = None
    training_data: Optional[dict] = None
    intended_use: Optional[str] = None
    limitations: Optional[str] = None
    license: Optional[str] = None
    architecture: Optional[dict] = None
    eval_results: Optional[dict] = None
    artifact_uri: Optional[str] = None
    artifact_size_bytes: Optional[int] = None
    artifact_hash: Optional[str] = None
    gateway_config: Optional[dict] = None


class VersionUpdate(BaseModel):
    release_notes: Optional[str] = None
    training_data: Optional[dict] = None
    intended_use: Optional[str] = None
    limitations: Optional[str] = None
    license: Optional[str] = None
    architecture: Optional[dict] = None
    eval_results: Optional[dict] = None
    artifact_uri: Optional[str] = None
    artifact_size_bytes: Optional[int] = None
    artifact_hash: Optional[str] = None
    gateway_config: Optional[dict] = None


# --- Access ---

class AccessGrant(BaseModel):
    grantee_type: str = Field(..., pattern="^(user|department|organization)$")
    grantee_id: str
    permission: str = Field(..., pattern="^(view|use|edit|admin)$")
