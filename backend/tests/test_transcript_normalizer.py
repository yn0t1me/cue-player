from app.services.transcript import PersistedRawCueData, TranscriptNormalizer, clean_vtt_text


def cue(index, start, end, text):
    return PersistedRawCueData(f'cue-{index}', index, start, end, text)


def test_clean_vtt_text_removes_display_tags_decodes_entities_and_normalizes_whitespace():
    assert clean_vtt_text(' <v Alice><c.green>Hello&nbsp;  <i>world</i></c></v>\nagain ') == (
        'Hello world again')


def test_rolling_prefix_expansion_uses_all_source_ids_and_real_time_range():
    result = TranscriptNormalizer().normalize([
        cue(0, 1.0, 2.0, "I wasn't really"),
        cue(1, 1.8, 2.8, "I wasn't really sold on"),
        cue(2, 2.6, 3.5, "I wasn't really sold on the idea."),
    ])
    assert len(result) == 1
    assert (result[0].start_seconds, result[0].end_seconds, result[0].text) == (
        1.0, 3.5, "I wasn't really sold on the idea.")
    assert result[0].source_ref_type == 'cue'
    assert result[0].source_refs == {'cue_ids': ['cue-0', 'cue-1', 'cue-2']}


def test_exact_repetition_and_unrelated_overlap_stay_separate():
    result = TranscriptNormalizer().normalize([
        cue(0, 0.0, 1.0, 'Really'),
        cue(1, 0.8, 1.5, 'Really'),
        cue(2, 1.2, 2.0, 'Another speaker'),
    ])
    assert [item.text for item in result] == ['Really', 'Really', 'Another speaker']


def test_only_obvious_short_fragments_across_a_small_non_overlapping_gap_merge():
    result = TranscriptNormalizer().normalize([
        cue(0, 0.0, 1.0, 'This is a short'),
        cue(1, 1.2, 2.0, 'fragment.'),
        cue(2, 3.0, 4.0, 'A real gap'),
        cue(3, 4.0, 5.0, 'continues?'),
        cue(4, 5.0, 6.0, 'New sentence.'),
    ])
    assert [(item.text, item.start_seconds, item.end_seconds) for item in result] == [
        ('This is a short fragment.', 0.0, 2.0),
        ('A real gap continues?', 3.0, 5.0),
        ('New sentence.', 5.0, 6.0),
    ]


def test_fragment_merge_stops_at_the_readability_limits():
    long_fragment = 'word ' * 25
    result = TranscriptNormalizer().normalize([
        cue(0, 0.0, 1.0, long_fragment),
        cue(1, 1.0, 2.0, 'tail'),
        cue(2, 2.0, 3.0, 'x' * 156),
    ])
    assert [item.text for item in result] == [long_fragment.strip(), 'tail', 'x' * 156]


def test_cue_with_multiple_sentences_is_not_split_without_word_timing():
    result = TranscriptNormalizer().normalize([cue(0, 4.0, 8.0, 'First. Second.')])
    assert [(item.text, item.start_seconds, item.end_seconds) for item in result] == [
        ('First. Second.', 4.0, 8.0)]


def test_empty_cleaned_cues_are_omitted_and_output_is_reindexed():
    result = TranscriptNormalizer().normalize([
        cue(3, 3.0, 4.0, '<c></c>'), cue(7, 7.0, 8.0, 'Kept.')])
    assert len(result) == 1
    assert result[0].sequence_index == 0
    assert result[0].normalization_version == 2


def test_auto_rolling_pairs_collapse_and_stitch_shared_words_without_fake_timing():
    result = TranscriptNormalizer().normalize([
        cue(0, 0.0, 0.01, 'We are checking'),
        cue(1, 0.01, 2.0, 'We are checking <00:00:01.000>into the hotel'),
        cue(2, 2.0, 2.01, 'into the hotel'),
        cue(3, 2.01, 4.0, 'into the hotel <00:00:03.000>together now.'),
    ])
    assert [(item.text, item.start_seconds, item.end_seconds) for item in result] == [
        ('We are checking into the hotel together now.', 0.0, 4.0),
    ]
    assert result[0].source_refs == {
        'cue_ids': ['cue-0', 'cue-1', 'cue-2', 'cue-3'],
    }


def test_auto_rolling_stitch_starts_a_new_segment_after_sentence_punctuation():
    result = TranscriptNormalizer().normalize([
        cue(0, 0.0, 0.01, 'We will show you'),
        cue(1, 0.01, 2.0, 'We will show you the process.'),
        cue(2, 2.0, 2.01, 'the process.'),
        cue(3, 2.01, 4.0, 'the process. Next time you will know.'),
    ])
    assert [(item.text, item.start_seconds, item.end_seconds, item.source_refs)
            for item in result] == [
        ('We will show you the process.', 0.0, 2.0,
         {'cue_ids': ['cue-0', 'cue-1']}),
        ('Next time you will know.', 2.01, 4.0,
         {'cue_ids': ['cue-3']}),
    ]


def test_auto_rolling_stitch_starts_a_new_segment_at_readability_limit():
    first_words = [f'word{index}' for index in range(20)]
    overlap = first_words[-3:]
    novel = [f'next{index}' for index in range(12)]
    result = TranscriptNormalizer().normalize([
        cue(0, 0.0, 0.01, ' '.join(first_words[:3])),
        cue(1, 0.01, 2.0, ' '.join(first_words)),
        cue(2, 2.0, 2.01, ' '.join(overlap)),
        cue(3, 2.01, 4.0, ' '.join([*overlap, *novel])),
    ])
    assert [item.text for item in result] == [' '.join(first_words), ' '.join(novel)]
    assert all(len(item.text) <= 160 for item in result)
    assert (result[1].start_seconds, result[1].end_seconds) == (2.01, 4.0)
    assert result[1].source_refs == {'cue_ids': ['cue-3']}


def test_suffix_overlap_without_auto_rolling_shape_remains_real_text():
    result = TranscriptNormalizer().normalize([
        cue(0, 0.0, 2.0, 'We agree.'),
        cue(1, 2.0, 4.0, 'agree. Next point.'),
    ])
    assert [item.text for item in result] == ['We agree.', 'agree. Next point.']
