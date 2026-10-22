"""Read-only source evidence and local sentence timing, without database or network I/O."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import html
import json
import math
import re
import unicodedata
from typing import Literal, NoReturn

from app.core.enums import SubtitleSource
from app.services.transcript.vtt import PersistedRawCueData

EXTRACTOR_VERSION = 'youtube-vtt-units-v2'
MAX_BOUNDARY_OVERRUN_MS = 10
MANUAL_EXTRACTOR_VERSION = 'youtube-manual-cues-v1'
MAX_SOURCE_BYTES = 5 * 1024 * 1024
MAX_SOURCE_UNITS = 50_000
MAX_RESULT_BYTES = 1024 * 1024
MAX_RESULT_SEGMENTS = 5000
_TAG = re.compile(r'<[^>]*>')
_TIMESTAMP = re.compile(r'<(\d{2,}):(\d{2}):(\d{2})\.(\d{3})>')
_DISPLAY_TAG = re.compile(r'</?(?:c(?:\.[^ >]+)*|v(?: [^>]+)?|lang(?: [^>]+)?|i|b|u)>')
_TOKEN = re.compile(r'\[\s*__\s*\]|\S+')
_ENTITY = re.compile(r'&(?:#[xX][0-9a-fA-F]+|#\d+|[a-zA-Z][a-zA-Z0-9]+);')
TimeBasis = Literal['inline_timestamp', 'cue_start']


class SourceLearningError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _fail(code: str, rule: str) -> NoReturn:
    raise SourceLearningError(code, rule)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _size(value: str, code: str) -> int:
    try:
        return len(value.encode('utf-8'))
    except UnicodeError:
        _fail(code, '文字不是合法 UTF-8。')


@dataclass(frozen=True, slots=True)
class RawSourceCue:
    id: str
    sequence_index: int
    start_seconds: float
    end_seconds: float
    text: str
    raw_vtt_sha256: str


def parse_source_vtt(content: bytes) -> tuple[RawSourceCue, ...]:
    """Recover immutable original cues, including whitespace-only display lines.

    The legacy webvtt parser treats a whitespace-only payload line as an empty
    separator and drops that cue. Keep original-file locators separate from DB IDs.
    """
    if len(content) > MAX_SOURCE_BYTES:
        _fail('LEARNING_SOURCE_TOO_LARGE', '原始 VTT 超过大小上限。')
    try:
        document = content.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    except UnicodeError:
        _fail('INVALID_SOURCE_EVIDENCE', '原始 VTT 编码无效。')
    if not re.match(r'^WEBVTT(?:[ \t].*)?(?:\n|$)', document):
        _fail('INVALID_SOURCE_EVIDENCE', '原始文件不是 WebVTT。')
    digest = hashlib.sha256(content).hexdigest()
    cues = []
    pattern = re.compile(r'(\d{2,}:\d{2}:\d{2}\.\d{3}) --> (\d{2,}:\d{2}:\d{2}\.\d{3})(?:[ \t].*)?')
    def seconds(stamp: str) -> float:
        try:
            h, m, remainder = stamp.split(':')
            sec, ms = remainder.split('.')
            if int(m) >= 60 or int(sec) >= 60:
                _fail('INVALID_SOURCE_EVIDENCE', '原始 VTT 时间格式无效。')
            return ((int(h) * 60 + int(m)) * 60 + int(sec)) + int(ms) / 1000
        except (ValueError, OverflowError) as exc:
            if isinstance(exc, SourceLearningError):
                raise
            _fail('INVALID_SOURCE_EVIDENCE', '原始 VTT 时间格式无效。')
    # Only an actually empty line separates original cues; a line containing
    # spaces is a legitimate empty displayed row and must remain in its payload.
    for block in document.split('\n\n'):
        lines = block.splitlines()
        if not lines:
            continue
        if lines[0].startswith('WEBVTT'):
            if any('-->' in line for line in lines):
                _fail('INVALID_SOURCE_EVIDENCE', '原始 VTT 缺少头部与 cue 分隔。')
            continue
        if lines[0].startswith(('NOTE', 'STYLE', 'REGION')):
            continue
        timing = next((i for i, line in enumerate(lines) if '-->' in line), None)
        if timing is None:
            if any(line.strip() for line in lines):
                _fail('INVALID_SOURCE_EVIDENCE', '原始 VTT 包含无法识别的块。')
            continue
        match = pattern.fullmatch(lines[timing])
        if timing not in (0, 1) or not match or len(lines) <= timing + 1:
            _fail('INVALID_SOURCE_EVIDENCE', '原始 VTT cue 格式无效。')
        index = len(cues)
        cues.append(RawSourceCue(f'vtt:{digest}:{index}', index,
                                 seconds(match[1]), seconds(match[2]),
                                 '\n'.join(lines[timing + 1:]), digest))
    if not cues:
        _fail('SOURCE_TIMING_UNAVAILABLE', '原始 VTT 没有字幕。')
    return tuple(cues)


@dataclass(frozen=True, slots=True)
class SourceUnit:
    id: str
    text: str
    start_ms: int
    cue_end_ms: int
    time_basis: TimeBasis
    cue_id: str | None
    raw_vtt_sha256: str | None
    cue_sequence_index: int
    line_index: int
    token_index: int
    char_start: int
    char_end: int
    end_cue_sequence_index: int | None = None

    def public_data(self) -> dict:
        return dict(id=self.id, text=self.text, start_ms=self.start_ms,
                    time_basis=self.time_basis)


@dataclass(frozen=True, slots=True)
class LearningSource:
    source_video_id: str
    source_digest: str
    extractor_version: str
    units: tuple[SourceUnit, ...]
    source_type: SubtitleSource = SubtitleSource.YOUTUBE_AUTO
    processing_mode: Literal['manual_cues', 'auto_units'] = 'auto_units'
    format: Literal['learning-source-v2'] = 'learning-source-v2'


    def public_data(self) -> dict:
        data = dict(format=self.format, source_video_id=self.source_video_id,
                    source_digest=self.source_digest, extractor_version=self.extractor_version,
                    units=[unit.public_data() for unit in self.units])
        data.update(source_type=self.source_type, processing_mode=self.processing_mode)
        return data


@dataclass(frozen=True, slots=True)
class TimedLearningSentence:
    sequence_index: int
    first_unit_id: str
    last_unit_id: str
    source_text: str
    text: str
    chunks: tuple[str, ...]
    boundary_offsets: tuple[int, ...]
    start_ms: int
    end_ms: int
    start_basis: TimeBasis
    end_basis: Literal['next_sentence_start', 'source_cue_end']
    source_units: tuple[SourceUnit, ...]
    translation_zh: str | None = None


@dataclass(frozen=True, slots=True)
class LearningWarning:
    code: str
    sequence_index: int


@dataclass(frozen=True, slots=True)
class RebuiltLearning:
    source_digest: str
    extractor_version: str
    sentences: tuple[TimedLearningSentence, ...]
    warnings: tuple[LearningWarning, ...]
    result_format: str = 'learning-result-v2'
    source_type: SubtitleSource = SubtitleSource.YOUTUBE_AUTO
    processing_mode: str = 'auto_units'

    def preview_digest(self, revision_id: str) -> str:
        data = [revision_id, self.source_digest, self.extractor_version, [
            [s.first_unit_id, s.last_unit_id, s.start_ms, s.end_ms, s.text,
             list(s.boundary_offsets)] for s in self.sentences]]
        data.extend([self.result_format, self.source_type, self.processing_mode,
                     [s.translation_zh for s in self.sentences]])
        return hashlib.sha256(_json(data).encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class _Cue:
    raw: PersistedRawCueData | RawSourceCue
    start_ms: int
    end_ms: int
    lines: tuple[tuple[SourceUnit, ...], ...]

    @property
    def tokens(self) -> tuple[SourceUnit, ...]:
        return tuple(token for line in self.lines for token in line)


def _milliseconds(value: float, cue_number: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        _fail('INVALID_SOURCE_EVIDENCE', f'cue {cue_number} 时间类型无效。')
    try:
        if not math.isfinite(value) or value < 0 or not math.isfinite(value * 1000):
            _fail('INVALID_SOURCE_EVIDENCE', f'cue {cue_number} 时间无效。')
        return round(value * 1000)
    except OverflowError:
        _fail('INVALID_SOURCE_EVIDENCE', f'cue {cue_number} 时间溢出。')


def _decode(fragment: str, offset: int) -> tuple[str, list[tuple[int, int]]]:
    """Decode entities while retaining positions in the immutable Raw text."""
    chars: list[str] = []
    locations: list[tuple[int, int]] = []
    cursor = 0
    for entity in _ENTITY.finditer(fragment):
        for i in range(cursor, entity.start()):
            chars.append(fragment[i])
            locations.append((offset + i, offset + i + 1))
        decoded = html.unescape(entity.group())
        chars.extend(decoded)
        locations.extend([(offset + entity.start(), offset + entity.end())] * len(decoded))
        cursor = entity.end()
    for i in range(cursor, len(fragment)):
        chars.append(fragment[i])
        locations.append((offset + i, offset + i + 1))
    return ''.join(chars), locations


def _parse_cue(raw: PersistedRawCueData | RawSourceCue, *, boundary_candidate: bool = False) -> _Cue:
    start, end = (_milliseconds(raw.start_seconds, raw.sequence_index),
                  _milliseconds(raw.end_seconds, raw.sequence_index))
    if end <= start or not isinstance(raw.text, str) or '\x00' in raw.text:
        _fail('INVALID_SOURCE_EVIDENCE', f'cue {raw.sequence_index} 范围或文字无效。')
    _size(raw.text, 'INVALID_SOURCE_EVIDENCE')
    clock, basis, last_marker = start, 'cue_start', None
    lines: list[tuple[SourceUnit, ...]] = []
    offset = 0
    for line_index, line in enumerate(raw.text.splitlines(keepends=True)):
        tokens: list[SourceUnit] = []
        cursor = 0
        for tag in [*_TAG.finditer(line), None]:
            stop = tag.start() if tag else len(line)
            if '<' in line[cursor:stop]:
                _fail('INVALID_SOURCE_EVIDENCE', f'cue {raw.sequence_index} 展示标签不完整。')
            decoded, positions = _decode(line[cursor:stop], offset + cursor)
            for word in _TOKEN.finditer(decoded):
                text = '[__]' if re.fullmatch(r'\[\s*__\s*\]', word.group()) else word.group()
                # Formatting inside a word does not create a second source word.
                raw_start, raw_end = positions[word.start()][0], positions[word.end() - 1][1]
                if tokens and word.start() == 0:
                    gap = raw.text[tokens[-1].char_end:raw_start]
                    tags = list(_TAG.finditer(gap))
                    if tags and ''.join(t.group() for t in tags) == gap and all(
                            _DISPLAY_TAG.fullmatch(t.group()) for t in tags):
                        tokens[-1] = replace(tokens[-1], text=tokens[-1].text + text,
                                             char_end=raw_end)
                        continue
                tokens.append(SourceUnit('', text, clock, end, basis,
                                         None if isinstance(raw, RawSourceCue) else raw.id,
                                         raw.raw_vtt_sha256 if isinstance(raw, RawSourceCue) else None,
                                         raw.sequence_index, line_index,
                                         len(tokens), positions[word.start()][0],
                                         positions[word.end() - 1][1]))
            if tag is None:
                break
            stamp = _TIMESTAMP.fullmatch(tag.group())
            if stamp:
                h, m, s, ms = map(int, stamp.groups())
                marker = ((h * 60 + m) * 60 + s) * 1000 + ms
                within_end = marker < end or (boundary_candidate and end < marker <= end + MAX_BOUNDARY_OVERRUN_MS)
                if m >= 60 or s >= 60 or marker < start or not within_end or (
                        last_marker is not None and marker < last_marker):
                    _fail('INVALID_SOURCE_EVIDENCE', f'cue {raw.sequence_index} 内部时间标记无效。')
                clock, basis, last_marker = marker, 'inline_timestamp', marker
            elif not _DISPLAY_TAG.fullmatch(tag.group()):
                _fail('INVALID_SOURCE_EVIDENCE', f'cue {raw.sequence_index} 含不支持的展示标签。')
            cursor = tag.end()
        if tokens:
            lines.append(tuple(tokens))
        offset += len(line)
    return _Cue(raw, start, end, tuple(lines))


def _texts(tokens: tuple[SourceUnit, ...]) -> tuple[str, ...]:
    return tuple(t.text for t in tokens)


def _prefix_overlap(previous: tuple[SourceUnit, ...], current: tuple[SourceUnit, ...]) -> int:
    # Rolling captions retain a suffix of the last display as their next prefix.
    # Work per displayed cue, never scan the full transcript for similar text.
    if not previous or not current:
        return 0
    # Prefix-function over current + a sentinel + the last displayed suffix.
    # The final value is the longest current prefix that ends the last display.
    values = [*_texts(current), None, *_texts(previous[-len(current):])]
    prefixes = [0] * len(values)
    for index in range(1, len(values)):
        count = prefixes[index - 1]
        while count and values[index] != values[count]:
            count = prefixes[count - 1]
        if values[index] == values[count]:
            count += 1
        prefixes[index] = count
    return prefixes[-1]


def _resolve_boundary_overruns(cues: tuple[_Cue, ...]) -> tuple[_Cue, ...]:
    """Keep exact word clocks only when a rolling display proves their end.

    Parsing a candidate is not acceptance: every overrun needs the next short
    display-only bridge and the following untimed prefix extension. Original
    cue ranges still drive adjacency; only the affected word's end is derived.
    """
    resolved = []
    for index, cue in enumerate(cues):
        overflow = [t for t in cue.tokens if t.start_ms >= cue.end_ms]
        if not overflow:
            resolved.append(cue)
            continue
        bridge = cues[index + 1] if index + 1 < len(cues) else None
        continuation = cues[index + 2] if index + 2 < len(cues) else None
        proven = bool(
            bridge and continuation and bridge.tokens
            and bridge.start_ms == cue.end_ms
            and 0 < bridge.end_ms - bridge.start_ms <= MAX_BOUNDARY_OVERRUN_MS
            and continuation.start_ms == bridge.end_ms
            and _prefix_overlap(cue.tokens, bridge.tokens) == len(bridge.tokens)
            and all(t.time_basis == 'cue_start' for t in bridge.tokens)
            and len(continuation.tokens) > len(bridge.tokens)
            and _texts(continuation.tokens[:len(bridge.tokens)]) == _texts(bridge.tokens)
            and all(t.time_basis == 'cue_start' for t in continuation.tokens[:len(bridge.tokens)])
            and all(t.start_ms == continuation.start_ms for t in overflow)
            and all(t in cue.tokens[-len(bridge.tokens):] for t in overflow))
        if not proven:
            _fail('INVALID_SOURCE_EVIDENCE', f'cue {cue.raw.sequence_index} 内部时间标记无效。')
        # Both sources are immutable; the continuation locator explains the
        # derived end without pretending it was the original cue's end.
        assert continuation is not None
        lines = tuple(tuple(replace(t, cue_end_ms=continuation.end_ms,
                                    end_cue_sequence_index=continuation.raw.sequence_index)
                            if t.start_ms >= cue.end_ms else t for t in line) for line in cue.lines)
        resolved.append(replace(cue, lines=lines))
    return tuple(resolved)


def extract_learning_source(
    source_video_id: str, source_type: SubtitleSource,
    raw_cues: tuple[PersistedRawCueData | RawSourceCue, ...],
) -> LearningSource:
    """Derive ordered evidence; callers load immutable Raw, not Learning rows."""
    if source_type == SubtitleSource.YOUTUBE_MANUAL:
        return extract_manual_source(source_video_id, raw_cues)
    if source_type != SubtitleSource.YOUTUBE_AUTO:
        _fail('SOURCE_TIMING_UNAVAILABLE', '语音转写暂不支持此学习字幕处理入口。')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', source_video_id):
        _fail('INVALID_SOURCE_EVIDENCE', '公开视频 ID 无效。')
    if not raw_cues:
        _fail('SOURCE_TIMING_UNAVAILABLE', '没有原始字幕。')
    if any(not isinstance(c.sequence_index, int) or isinstance(c.sequence_index, bool)
           or c.sequence_index != i or not c.id for i, c in enumerate(raw_cues)):
        _fail('INVALID_SOURCE_EVIDENCE', 'Raw cue 序号或定位无效。')
    if len({c.id for c in raw_cues}) != len(raw_cues):
        _fail('INVALID_SOURCE_EVIDENCE', 'Raw cue 定位重复。')
    if sum(_size(c.text, 'INVALID_SOURCE_EVIDENCE') for c in raw_cues) > MAX_SOURCE_BYTES:
        _fail('LEARNING_SOURCE_TOO_LARGE', '原始来源超过大小上限。')
    cues = _resolve_boundary_overruns(tuple(_parse_cue(raw, boundary_candidate=True) for raw in raw_cues))
    units: list[SourceUnit] = []
    previous_display: tuple[SourceUnit, ...] = ()
    previous_cue: _Cue | None = None
    was_bridge = False
    for index, cue in enumerate(cues):
        if previous_cue and cue.start_ms < previous_cue.start_ms:
            _fail('INVALID_SOURCE_EVIDENCE', f'cue {cue.raw.sequence_index} 起点倒序。')
        current = cue.tokens
        adjacent = previous_cue is not None and 0 <= cue.start_ms - previous_cue.end_ms <= 50
        overlapping = previous_cue is not None and cue.start_ms < previous_cue.end_ms
        count = _prefix_overlap(previous_display, current) if adjacent or overlapping else 0
        next_cue = cues[index + 1] if index + 1 < len(cues) else None
        # A short display-only transition is proven by both the preceding display
        # and an immediately following prefix extension. Duration alone proves nothing.
        bridge = bool(current and count == len(current) and adjacent
                      and cue.end_ms - cue.start_ms <= 50
                      and all(t.time_basis == 'cue_start' for t in current)
                      and next_cue and 0 <= next_cue.start_ms - cue.end_ms <= 50
                      and len(next_cue.tokens) > len(current)
                      and _texts(next_cue.tokens[:len(current)]) == _texts(current)
                      and all(t.time_basis == 'cue_start' for t in next_cue.tokens[:len(current)]))
        if bridge:
            display = previous_display[-count:]
        else:
            carried = 0
            if count and was_bridge and adjacent:
                # The bridge establishes which text is already on screen.
                if all(t.time_basis == 'cue_start' for t in current[:count]):
                    carried = count
            elif count and adjacent and len(cue.lines) > 1:
                # A matching untimed row without a display transition cannot be
                # distinguished from repeated speech. Require evidence, not a guess.
                prefix_count = 0
                for line in cue.lines[:-1]:
                    prefix_count += len(line)
                    if prefix_count == count and all(t.time_basis == 'cue_start' for t in current[:count]):
                        _fail('INVALID_SOURCE_EVIDENCE',
                              f'cue {cue.raw.sequence_index} 回显行缺少可验证的展示转换。')
            elif count and overlapping:
                # Exact time anchors distinguish a retained display from new speech.
                old = previous_display[-count:]
                if all(a.start_ms == b.start_ms for a, b in zip(old, current[:count])):
                    carried = count
            if carried:
                display = previous_display[-carried:] + current[carried:]
            else:
                display = current
            for token in current[carried:]:
                if units and token.start_ms < units[-1].start_ms:
                    _fail('INVALID_SOURCE_EVIDENCE',
                          f'cue {cue.raw.sequence_index} 新内容时间倒序或回显不明确。')
                units.append(replace(token, id=f'u{len(units) + 1:06d}'))
                if len(units) > MAX_SOURCE_UNITS:
                    _fail('LEARNING_SOURCE_TOO_LARGE', '来源单元超过上限。')
        previous_display, previous_cue, was_bridge = display, cue, bridge
    if not units or not any(t.time_basis == 'inline_timestamp' for t in units):
        _fail('SOURCE_TIMING_UNAVAILABLE', '原字幕没有可用的内部时间依据。')
    evidence = [source_video_id, EXTRACTOR_VERSION, [
        [c.id, c.sequence_index, _milliseconds(c.start_seconds, c.sequence_index),
         _milliseconds(c.end_seconds, c.sequence_index), c.text] for c in raw_cues], [
        [u.id, u.text, u.start_ms, u.cue_end_ms, u.time_basis, u.cue_id,
         u.raw_vtt_sha256, u.cue_sequence_index, u.line_index, u.token_index, u.char_start, u.char_end,
         u.end_cue_sequence_index] for u in units]]
    digest = hashlib.sha256(_json(evidence).encode('utf-8')).hexdigest()
    bound_digest = hashlib.sha256(_json([
        'learning-source-v2', source_type, 'auto_units', digest]).encode('utf-8')).hexdigest()
    source = LearningSource(source_video_id, bound_digest, EXTRACTOR_VERSION, tuple(units))
    if _size(_json(source.public_data()), 'INVALID_SOURCE_EVIDENCE') > MAX_SOURCE_BYTES:
        _fail('LEARNING_SOURCE_TOO_LARGE', '来源包超过大小上限。')
    return source


def extract_manual_source(
    source_video_id: str, raw_cues: tuple[PersistedRawCueData | RawSourceCue, ...],
) -> LearningSource:
    """Keep each original nonempty manual cue, including overlapping times."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', source_video_id):
        _fail('INVALID_SOURCE_EVIDENCE', '公开视频 ID 无效。')
    if not raw_cues:
        _fail('SOURCE_TIMING_UNAVAILABLE', '没有原始人工字幕。')
    if any(not isinstance(c.sequence_index, int) or isinstance(c.sequence_index, bool)
           or c.sequence_index != i or not c.id for i, c in enumerate(raw_cues)):
        _fail('INVALID_SOURCE_EVIDENCE', 'Raw cue 序号或定位无效。')
    if len({c.id for c in raw_cues}) != len(raw_cues):
        _fail('INVALID_SOURCE_EVIDENCE', 'Raw cue 定位重复。')
    if sum(_size(c.text, 'INVALID_SOURCE_EVIDENCE') for c in raw_cues) > MAX_SOURCE_BYTES:
        _fail('LEARNING_SOURCE_TOO_LARGE', '原始来源超过大小上限。')
    units = []
    previous_start = -1
    for raw in raw_cues:
        cue = _parse_cue(raw)
        if cue.start_ms < previous_start:
            _fail('INVALID_SOURCE_EVIDENCE', f'cue {raw.sequence_index} 起点倒序。')
        previous_start = cue.start_ms
        # Manual cues only lose display markup and excess whitespace. The auto
        # tokenizer also canonicalizes censor markers, which would change text.
        text = ' '.join(html.unescape(_TAG.sub('', raw.text)).split())
        if not text:
            continue
        units.append(SourceUnit(
            f'u{len(units) + 1:06d}', text, cue.start_ms, cue.end_ms, 'cue_start',
            None if isinstance(raw, RawSourceCue) else raw.id,
            raw.raw_vtt_sha256 if isinstance(raw, RawSourceCue) else None,
            raw.sequence_index, 0, 0, 0, len(raw.text)))
        if len(units) > MAX_SOURCE_UNITS:
            _fail('LEARNING_SOURCE_TOO_LARGE', '来源单元超过上限。')
    if not units:
        _fail('SOURCE_TIMING_UNAVAILABLE', '原始人工字幕没有正文。')
    evidence = ['learning-source-v2', source_video_id, SubtitleSource.YOUTUBE_MANUAL,
                'manual_cues', MANUAL_EXTRACTOR_VERSION,
                [[c.id, c.sequence_index, c.start_seconds, c.end_seconds, c.text]
                 for c in raw_cues], [unit.public_data() for unit in units]]
    digest = hashlib.sha256(_json(evidence).encode('utf-8')).hexdigest()
    source = LearningSource(source_video_id, digest, MANUAL_EXTRACTOR_VERSION, tuple(units),
                            SubtitleSource.YOUTUBE_MANUAL, 'manual_cues')
    if _size(_json(source.public_data()), 'INVALID_SOURCE_EVIDENCE') > MAX_SOURCE_BYTES:
        _fail('LEARNING_SOURCE_TOO_LARGE', '来源包超过大小上限。')
    return source


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail('INVALID_LEARNING_RESULT', '结果含重复 JSON 字段。')
        result[key] = value
    return result


def _bad_constant(_: str) -> None:
    _fail('INVALID_LEARNING_RESULT', '结果含非标准 JSON 数值。')


def _lexical(text: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize('NFKC', text).casefold()
    return tuple(token.replace("'", '').replace('’', '') for token in
                 re.findall(r"\w+(?:['’]\w+)*", normalized))


def rebuild_learning_result(source: LearningSource, content: str) -> RebuiltLearning:
    """Accept only the full bound result; derive timing exclusively from source."""
    if not isinstance(content, str):
        _fail('INVALID_LEARNING_RESULT', '返回结果必须是 JSON 文本。')
    if _size(content, 'INVALID_LEARNING_RESULT') > MAX_RESULT_BYTES:
        _fail('LEARNING_RESULT_TOO_LARGE', '返回结果超过大小上限。')
    try:
        result = json.loads(content.strip().lstrip('\ufeff').strip(),
                            object_pairs_hook=_unique_object, parse_constant=_bad_constant)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, SourceLearningError):
            raise
        _fail('INVALID_LEARNING_RESULT', '返回结果不是完整合法的 JSON。')
    fields = {'format', 'source_video_id', 'source_digest', 'segments'}
    if not isinstance(result, dict) or set(result) != fields or result['format'] != 'learning-result-v2':
        _fail('INVALID_LEARNING_RESULT', '返回格式或字段不正确。')
    result_format = result['format']
    if not isinstance(result['source_video_id'], str) or not isinstance(result['source_digest'], str) or not re.fullmatch(r'[0-9a-f]{64}', result['source_digest']):
        _fail('INVALID_LEARNING_RESULT', '来源标识或摘要格式无效。')
    if result['source_video_id'] != source.source_video_id or result['source_digest'] != source.source_digest:
        _fail('LEARNING_SOURCE_MISMATCH', '返回稿不属于此视频或原始来源版本。')
    proposed = result['segments']
    if not isinstance(proposed, list) or not proposed:
        _fail('INVALID_LEARNING_RESULT', '返回结果没有句子。')
    if len(proposed) > MAX_RESULT_SEGMENTS:
        _fail('LEARNING_RESULT_TOO_LARGE', '句子数量超过上限。')
    unit_indexes = {u.id: i for i, u in enumerate(source.units)}
    ranges: list[tuple[int, int, tuple[str, ...], str | None]] = []
    cursor = 0
    for number, item in enumerate(proposed, start=1):
        item_fields = {'first_unit_id', 'last_unit_id', 'text', 'translation_zh'}
        if not isinstance(item, dict) or set(item) != item_fields:
            _fail('INVALID_LEARNING_RESULT', f'句子 {number} 字段不正确。')
        first, last, text = item['first_unit_id'], item['last_unit_id'], item['text']
        if not isinstance(first, str) or not isinstance(last, str):
            _fail('INVALID_SOURCE_RANGE', f'句子 {number} 来源编号无效。')
        a, b = unit_indexes.get(first), unit_indexes.get(last)
        if a is None or b is None or a != cursor or b < a:
            _fail('INVALID_SOURCE_RANGE', f'句子 {number} 来源范围缺失、重复或倒序。')
        if source.processing_mode == 'manual_cues' and a != b:
            _fail('INVALID_SOURCE_RANGE', f'句子 {number} 必须保留一条原始人工字幕。')
        translation = item.get('translation_zh')
        if not isinstance(translation, str) or not translation.strip() or '\x00' in translation:
            _fail('INVALID_LEARNING_RESULT', f'句子 {number} 中文翻译不能为空或无效。')
        _size(translation, 'INVALID_LEARNING_RESULT')
        translation = translation.strip()
        if not isinstance(text, str) or '\x00' in text:
            _fail('INVALID_LEARNING_RESULT', f'句子 {number} 文字无效。')
        _size(text, 'INVALID_LEARNING_RESULT')
        if source.processing_mode == 'manual_cues' and ' '.join(text.split()) == source.units[a].text:
            # A literal spaced slash in the original cue is valid English text;
            # an unchanged cue can always be returned without adding boundaries.
            chunks = (text,)
        else:
            chunks = tuple(text.split(' / '))
        if any(not c or c != c.strip()
               for c in chunks):
            _fail('INVALID_LEARNING_RESULT', f'句子 {number} 词块边界无效。')
        chunks = tuple(' '.join(c.split()) for c in chunks)
        if source.processing_mode == 'manual_cues' and ' '.join(chunks) != source.units[a].text:
            _fail('MANUAL_TRANSCRIPT_CHANGED', f'句子 {number} 人工字幕英文必须与原文一致。')
        ranges.append((a, b, chunks, translation))
        cursor = b + 1
    if cursor != len(source.units):
        _fail('INVALID_SOURCE_RANGE', '末句没有覆盖全部来源单元。')
    sentences: list[TimedLearningSentence] = []
    warnings: list[LearningWarning] = []
    for index, (a, b, chunks, translation) in enumerate(ranges):
        refs = source.units[a:b + 1]
        start, end = refs[0].start_ms, refs[-1].cue_end_ms
        end_basis = 'source_cue_end'
        if source.processing_mode == 'auto_units' and index + 1 < len(ranges):
            next_start = source.units[ranges[index + 1][0]].start_ms
            if next_start <= end:
                end, end_basis = next_start, 'next_sentence_start'
        if start < 0 or start >= end or end <= refs[-1].start_ms or (source.processing_mode == 'auto_units'
                and sentences and start < sentences[-1].end_ms):
            _fail('INVALID_REBUILT_TIMING', f'句子 {index + 1} 没有合法的独立时间范围。')
        text = ' '.join(chunks)
        boundaries: list[int] = []
        offset = 0
        for chunk in chunks[:-1]:
            offset += len(chunk)
            boundaries.append(offset)
            offset += 1
        original = ' '.join(u.text for u in refs)
        sentence = TimedLearningSentence(index, refs[0].id, refs[-1].id, original, text,
                                        chunks, tuple(boundaries), start, end,
                                        refs[0].time_basis, end_basis, refs, translation)
        sentences.append(sentence)
        if _lexical(original) != _lexical(text):
            warnings.append(LearningWarning('TEXT_CHANGED', index))
        if refs[0].time_basis == 'cue_start':
            warnings.append(LearningWarning('CUE_START_TIMING', index))
        if end - start < 250:
            warnings.append(LearningWarning('VERY_SHORT_SEGMENT', index))
        if end - refs[-1].start_ms > 3000:
            warnings.append(LearningWarning('LONG_END_HOLD', index))
    return RebuiltLearning(source.source_digest, source.extractor_version,
                          tuple(sentences), tuple(warnings), result_format,
                          source.source_type, source.processing_mode)
