from dataclasses import FrozenInstanceError

import pytest

from app.core.enums import SubtitleSource
from app.services.transcript.normalization_core import (
    NormalizationValidationError,
    RawTranscriptEvidence,
    prepare_normalization,
)
from app.services.transcript.stt import PersistedRawWordData
from app.services.transcript.vtt import PersistedRawCueData


def cue(index, start, end, text, cue_id=None):
    return PersistedRawCueData(cue_id or f"cue-{index}", index, start, end, text)


def word(index, cue_id, text, start=None, end=None):
    return PersistedRawWordData(
        id=f"word-{index}",
        cue_id=cue_id,
        sequence_index=index,
        text=text,
        start_seconds=start,
        end_seconds=end,
        confidence=0.9,
    )


def evidence(*cues, source=SubtitleSource.YOUTUBE_MANUAL, words=()):
    return RawTranscriptEvidence(source, "en", tuple(cues), tuple(words))


def test_manual_rolling_expansion_builds_unique_units_with_real_cue_mapping():
    plan = prepare_normalization(evidence(
        cue(0, 1.0, 2.0, "I wasn't really"),
        cue(1, 1.8, 2.8, "I wasn't really sold on"),
        cue(2, 2.6, 3.5, "I wasn't really sold on the idea."),
    ))

    assert [(unit.id, unit.text) for unit in plan.units] == [
        ("u000001", "I"),
        ("u000002", "wasn't"),
        ("u000003", "really"),
        ("u000004", "sold"),
        ("u000005", "on"),
        ("u000006", "the"),
        ("u000007", "idea."),
    ]


def test_auto_rolling_removes_only_confirmed_overlap_and_keeps_token_locators():
    plan = prepare_normalization(evidence(
        cue(0, 0.0, 0.01, "We are checking"),
        cue(1, 0.01, 2.0, "We are checking <00:00:01.000>into the hotel"),
        cue(2, 2.0, 2.01, "into the hotel"),
        cue(3, 2.01, 4.0, "into the hotel <00:00:03.000>together now."),
        source=SubtitleSource.YOUTUBE_AUTO,
    ))

    assert [unit.text for unit in plan.units] == [
        "We", "are", "checking", "into", "the", "hotel", "together", "now."
    ]


def test_stt_prefers_words_for_recorded_input_units():
    cues = (cue(0, 0.0, 1.0, "Hello world."), cue(1, 1.0, 2.0, "Again."))
    words = (
        word(0, "cue-0", " Hello", None, 0.4),
        word(1, "cue-0", " world.", 0.4, None),
        word(2, "cue-1", " Again.", None, None),
    )
    plan = prepare_normalization(evidence(*cues, source=SubtitleSource.STT, words=words))

    assert [unit.text for unit in plan.units] == ["Hello", "world.", "Again."]


def test_stt_without_words_uses_cue_tokens_for_recorded_input_units():
    plan = prepare_normalization(evidence(
        cue(0, 4.0, 8.0, "first second"), source=SubtitleSource.STT
    ))
    assert [unit.text for unit in plan.units] == ["first", "second"]


def test_rejects_invalid_evidence_and_dtos_are_frozen():
    with pytest.raises(NormalizationValidationError, match="source"):
        prepare_normalization(RawTranscriptEvidence(
            "stt", "en", (cue(0, 0.0, 1.0, "hello"),), ()
        ))
    with pytest.raises(NormalizationValidationError, match="no cues"):
        prepare_normalization(RawTranscriptEvidence(
            SubtitleSource.STT, "en", (), ()
        ))
    with pytest.raises(NormalizationValidationError, match="no usable units"):
        prepare_normalization(evidence(cue(0, 0.0, 1.0, "<c></c>")))
    with pytest.raises(NormalizationValidationError, match="Raw word evidence"):
        prepare_normalization(evidence(
            cue(0, 0.0, 1.0, "hello"),
            source=SubtitleSource.STT,
            words=(word(0, "missing-cue", "hello", 0.1, 0.2),),
        ))

    raw = evidence(cue(0, 0.0, 1.0, "hello"))
    with pytest.raises(FrozenInstanceError):
        raw.language = "changed"
    plan = prepare_normalization(raw)
    with pytest.raises(FrozenInstanceError):
        plan.units[0].text = "changed"
    with pytest.raises(FrozenInstanceError):
        plan.language = "changed"
