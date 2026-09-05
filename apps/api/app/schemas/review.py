"""Human-review API contracts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from packages.domain.enums import FollowUpTaskType


class ReviewActionRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=1000)
    note: str | None = Field(default=None, max_length=4000)


class DeferRequest(ReviewActionRequest):
    until: date


class AssignRequest(ReviewActionRequest):
    owner_role: str = Field(min_length=1, max_length=200)


class TaskCreateRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    task_type: FollowUpTaskType
    amount_at_risk_paise: int = Field(default=0, ge=0)
    required_evidence: str | None = Field(default=None, max_length=2000)
    deadline: date | None = None
    action_code: str | None = Field(default=None, max_length=200)


class ReviewActionResponse(BaseModel):
    case_id: str
    action: str
    previous_state: str
    new_state: str
    invariant_passed: bool | None
    human_reviewed: bool
    created_at: datetime


class TaskResponse(BaseModel):
    id: uuid.UUID
    case_id: str
    task_type: str
    amount_at_risk_paise: int
    currency: str
    required_evidence: str | None
    deadline: date | None
    action_code: str | None
    status: str
    created_at: datetime
