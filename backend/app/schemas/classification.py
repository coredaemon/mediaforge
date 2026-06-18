from pydantic import BaseModel, Field


class ExtensionCount(BaseModel):
    extension: str
    count: int


class MediaClassificationResult(BaseModel):
    scan_session_id: int
    content_type: str
    confidence: float = Field(ge=0, le=1)
    reason: str
    total_files: int
    video_files: int
    subtitle_files: int
    sidecar_files: int
    nested_folder_count: int
    known_extensions: list[ExtensionCount]
    ignored_extensions: list[ExtensionCount]
    movie_like_files: int
    tv_like_files: int
    mixed: bool
    needs_user_decision: bool
    warnings: list[str] = []
