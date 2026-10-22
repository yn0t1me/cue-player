import asyncio
from dataclasses import asdict

import httpx
import pytest

from app.core.enums import SubtitleSource
from app.services.transcript import (
    NormalizationValidationError,
    PersistedRawCueData,
    PersistedRawWordData,
    RawTranscriptEvidence,
    TranscriptNormalizationService,
)


@pytest.mark.parametrize('source', list(SubtitleSource))
def test_local_normalization_keeps_source_text_times_and_audit_without_network(source, monkeypatch):
    async def forbid_cloud(*args, **kwargs):
        pytest.fail('Local normalization must not send a cloud request')

    monkeypatch.setattr(httpx.AsyncClient, 'post', forbid_cloud)
    cue = PersistedRawCueData('cue-0', 0, 1.25, 3.5, 'we sale cars')
    words = tuple(PersistedRawWordData(f'word-{i}', cue.id, i, word, None, None, 0.9)
                  for i, word in enumerate(['we', 'sale', 'cars'])) if source is SubtitleSource.STT else ()
    raw = RawTranscriptEvidence(source, 'en', (cue,), words)
    before = asdict(raw)
    result = asyncio.run(TranscriptNormalizationService().normalize(raw))
    assert [(segment.text, segment.start_seconds, segment.end_seconds,
             segment.source_ref_type, segment.source_refs, segment.normalization_version)
            for segment in result.segments] == [('we sale cars', 1.25, 3.5, 'cue', ('cue-0',), 2)]
    assert result.run.method == 'deterministic'
    assert result.run.normalization_version == 2
    assert result.run.input_unit_count == 3
    assert asdict(raw) == before


def test_local_normalization_rejects_invalid_raw_evidence():
    raw = RawTranscriptEvidence(SubtitleSource.YOUTUBE_MANUAL, 'en', ())
    with pytest.raises(NormalizationValidationError, match='no cues'):
        asyncio.run(TranscriptNormalizationService().normalize(raw))
