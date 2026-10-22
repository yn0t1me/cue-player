from enum import StrEnum


class VideoStatus(StrEnum):
    PROCESSING = 'processing'
    READY = 'ready'
    FAILED = 'failed'


class JobStatus(StrEnum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class ProcessingStage(StrEnum):
    FETCHING_METADATA = 'fetching_metadata'
    FETCHING_CAPTIONS = 'fetching_captions'
    DOWNLOADING_AUDIO = 'downloading_audio'
    TRANSCRIBING = 'transcribing'
    NORMALIZING = 'normalizing'
    COMPLETED = 'completed'
    FAILED = 'failed'


class SubtitlePreference(StrEnum):
    MANUAL_FIRST = 'manual_first'
    AUTO_ONLY = 'auto_only'


class SubtitleSource(StrEnum):
    YOUTUBE_MANUAL = 'youtube_manual'
    YOUTUBE_AUTO = 'youtube_auto'
    STT = 'stt'
