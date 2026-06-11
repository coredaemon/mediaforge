from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import ScanSessionStatus


class ScanSessionCreate(BaseModel):
    source_path: str
    target_path: str


class ScanSessionListItem(BaseModel):
    id: int
    source_path: str
    target_path: str
    status: ScanSessionStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)


ScanSessionRead = ScanSessionListItem


class ScanSessionDeleteResult(BaseModel):
    ok: bool
    id: int
