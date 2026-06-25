"""Pydantic schemas for the AgencyRatings API."""
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgencyRatingBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    company_code: Optional[str] = None
    company_name: Optional[str] = None

    agency: str
    is_esg: bool

    rating: Optional[str] = None
    outlook: Optional[str] = None
    score: Optional[str] = None

    rating_date_text: Optional[str] = None
    rating_date: Optional[date] = None

    report_url: Optional[str] = None

    created_at: datetime
    updated_at: datetime


class AgencyRatingDetail(AgencyRatingBrief):
    legacy_id: Optional[str] = None
    legacy_board_id: Optional[str] = None
    extra: Optional[dict] = None


class AgencyRatingListResponse(BaseModel):
    items: list[AgencyRatingBrief]
    total: int
    by_agency:  dict = Field(default_factory=dict)
    by_company: dict = Field(default_factory=dict)
    credit_count: int = 0
    esg_count: int = 0


class CompanyRatingsResponse(BaseModel):
    """All ratings for one company, split by category."""
    company_id: UUID
    company_code: str
    company_name: str
    credit: list[AgencyRatingBrief] = Field(default_factory=list)
    esg:    list[AgencyRatingBrief] = Field(default_factory=list)


class AgencyRatingCreate(BaseModel):
    company_id: UUID
    agency: str = Field(..., min_length=1, max_length=64)
    rating: Optional[str] = Field(None, max_length=16)
    outlook: Optional[str] = Field(None, max_length=32)
    score: Optional[str] = Field(None, max_length=16)
    rating_date_text: Optional[str] = Field(None, max_length=64)
    rating_date: Optional[date] = None
    report_url: Optional[str] = Field(None, max_length=2000)


class AgencyRatingUpdate(BaseModel):
    rating: Optional[str] = Field(None, max_length=16)
    outlook: Optional[str] = Field(None, max_length=32)
    score: Optional[str] = Field(None, max_length=16)
    rating_date_text: Optional[str] = Field(None, max_length=64)
    rating_date: Optional[date] = None
    report_url: Optional[str] = Field(None, max_length=2000)


class AgencyRatingHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    rating: Optional[str] = None
    outlook: Optional[str] = None
    score: Optional[str] = None
    rating_date_text: Optional[str] = None
    rating_date: Optional[date] = None
    report_url: Optional[str] = None
    changed_by_name: Optional[str] = None
    created_at: datetime


class AgencyRatingHistoryResponse(BaseModel):
    company_id: UUID
    agency: str
    items: list[AgencyRatingHistoryItem] = Field(default_factory=list)
