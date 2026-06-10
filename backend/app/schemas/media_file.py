from datetime import datetime

from pydantic import BaseModel, ConfigDict

from ..models.enums import MediaFileKind


class MediaFileRead(BaseModel):
    id: int
    scan_session_id: int
    media_item_id: int | None = None
    path: str
    file_name: str
    extension: str
    size_bytes: int | None = None
    kind: MediaFileKind
    is_video: bool
    is_subtitle: bool
    is_sidecar: bool
    scan_error: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
