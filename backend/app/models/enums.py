from enum import StrEnum


class ScanSessionStatus(StrEnum):
    CREATED = "CREATED"
    DISCOVERING = "DISCOVERING"
    DISCOVERED = "DISCOVERED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MediaFileKind(StrEnum):
    VIDEO = "VIDEO"
    SUBTITLE = "SUBTITLE"
    SIDECAR = "SIDECAR"
    OTHER = "OTHER"


class MediaItemStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    IGNORED = "IGNORED"
    MATCHING = "MATCHING"
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"


class MediaType(StrEnum):
    UNKNOWN = "UNKNOWN"
    MOVIE = "MOVIE"
    TV_SHOW = "TV_SHOW"
    TV_EPISODE = "TV_EPISODE"
    EXTRA = "EXTRA"


class ReviewDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    IGNORED = "ignored"
    DEFERRED = "deferred"
    MANUAL_OVERRIDE = "manual_override"


class PlanStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    APPLYING = "APPLYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class OperationStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ROLLED_BACK = "ROLLED_BACK"


class OperationType(StrEnum):
    CREATE_DIR = "CREATE_DIR"
    MOVE_FILE = "MOVE_FILE"
    COPY_FILE = "COPY_FILE"
    WRITE_TEXT_FILE = "WRITE_TEXT_FILE"
    DOWNLOAD_FILE = "DOWNLOAD_FILE"
    DELETE_EMPTY_DIR = "DELETE_EMPTY_DIR"
