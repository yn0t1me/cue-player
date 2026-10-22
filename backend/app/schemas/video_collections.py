from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.enums import SubtitlePreference
from app.schemas.videos import ProcessingJobResponse, VideoResponse

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=36)]
Version = Annotated[int, Field(strict=True, ge=1)]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class CollectionCreate(RequestModel):
    name: Name
    description: str | None = Field(default=None, max_length=2000)


class CollectionPatch(RequestModel):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=2000)
    expected_version: Version

    @model_validator(mode='after')
    def validate_changes(self):
        if not ({'name', 'description'} & self.model_fields_set) or ('name' in self.model_fields_set and self.name is None):
            raise ValueError('Provide a valid collection change')
        return self


class CollectionMembersRequest(RequestModel):
    video_ids: list[Identifier] = Field(min_length=1, max_length=200)
    expected_version: Version


class CollectionOrderRequest(RequestModel):
    item_ids: list[Identifier] = Field(max_length=10000)
    expected_version: Version


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str | None
    version: int
    source_playlist_id: str | None
    source_playlist_url: str | None
    created_at: datetime
    updated_at: datetime
    thumbnail_url: str | None = None
    total_count: int = 0
    ready_count: int = 0


class CollectionMemberResponse(BaseModel):
    id: str
    position: int
    video: VideoResponse


class CollectionDetailResponse(CollectionResponse):
    items: list[CollectionMemberResponse]


class CollectionListResponse(BaseModel):
    items: list[CollectionResponse]


class PreviewRequest(RequestModel):
    input_kind: Literal['single', 'multiple', 'playlist']
    urls: list[Annotated[str, Field(min_length=1, max_length=2048)]] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def validate_count(self):
        if self.input_kind != 'multiple' and len(self.urls) != 1:
            raise ValueError('Expected one URL')
        return self


class PreviewError(BaseModel):
    code: str
    message: str


class PreviewItem(BaseModel):
    id: str
    source_position: int
    youtube_video_id: str | None
    url: str | None
    title: str | None = None
    duration: float | None = None
    thumbnail_url: str | None = None
    selectable: bool
    existing_video_id: str | None = None
    error: PreviewError | None = None


class PreviewSource(BaseModel):
    input_kind: Literal['single', 'multiple', 'playlist']
    playlist_id: str | None = None
    url: str | None = None
    title: str | None = None


class PreviewLimits(BaseModel):
    max_items: int = 200
    expires_in_seconds: int = 1800


class PreviewResponse(BaseModel):
    id: str
    expires_at: datetime
    limits: PreviewLimits = Field(default_factory=PreviewLimits)
    source: PreviewSource
    items: list[PreviewItem]
    duplicate_count: int


class NoTarget(RequestModel):
    kind: Literal['none']


class ExistingTarget(RequestModel):
    kind: Literal['existing']
    collection_id: Identifier


class NewTarget(CollectionCreate):
    kind: Literal['new']


class BatchRequest(RequestModel):
    preview_id: Identifier
    selected_item_ids: list[Identifier] = Field(min_length=1, max_length=200)
    subtitle_preference: SubtitlePreference = SubtitlePreference.MANUAL_FIRST
    target: Annotated[NoTarget | ExistingTarget | NewTarget, Field(discriminator='kind')]
    idempotency_key: str = Field(min_length=1, max_length=100)


class BatchItemResponse(BaseModel):
    id: str
    preview_item_id: str
    position: int
    youtube_video_id: str | None
    disposition: Literal['created', 'reused', 'already_member', 'unavailable']
    video: VideoResponse | None
    job: ProcessingJobResponse | None
    error: PreviewError | None


class BatchCounts(BaseModel):
    total: int = 0
    ready: int = 0
    waiting: int = 0
    running: int = 0
    failed: int = 0
    unavailable: int = 0


class BatchResponse(BaseModel):
    id: str
    preview_id: str
    collection_id: str | None
    collection_name_snapshot: str | None
    subtitle_preference: SubtitlePreference
    created_at: datetime
    status: Literal['pending', 'running', 'completed', 'completed_with_errors']
    counts: BatchCounts
    items: list[BatchItemResponse]


class RetryVideoRequest(RequestModel):
    expected_job_id: Identifier
    idempotency_key: str = Field(min_length=1, max_length=100)


class RetryVideoResponse(BaseModel):
    video_id: str
    previous_job_id: str
    job: ProcessingJobResponse


class RetryBatchRequest(RequestModel):
    item_ids: list[Identifier] = Field(min_length=1, max_length=200)
    expected_job_ids: dict[Identifier, Identifier | None] = Field(max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def validate_items(self):
        if len(set(self.item_ids)) != len(self.item_ids) or set(self.item_ids) != set(self.expected_job_ids):
            raise ValueError('Provide each selected item and its expected job once')
        return self


class RetryBatchItemResponse(BaseModel):
    item_id: str
    video_id: str | None
    previous_job_id: str | None
    status: Literal['accepted', 'skipped', 'rejected']
    job: ProcessingJobResponse | None = None
    error: PreviewError | None = None


class RetryBatchResponse(BaseModel):
    batch_id: str
    items: list[RetryBatchItemResponse]
