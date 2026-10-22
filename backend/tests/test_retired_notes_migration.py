"""The 015 cleanup removes only notes/questions, preserving every other record."""
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.config import Settings
from app.db.session import create_db_engine


def snapshot(engine):
    with engine.connect() as connection:
        return {table: sorted([dict(row) for row in connection.execute(text(
            f'SELECT * FROM "{table}"')).mappings()], key=lambda row: json.dumps(row, sort_keys=True, default=str))
            for table in inspect(connection).get_table_names()}


def test_upgrade_cleans_notes_and_questions_preserving_current_and_old_favorites(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "notes.db"}')
    monkeypatch.setenv('DATA_DIR', str(tmp_path / 'data'))
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '014_retire_legacy_subtitles')
    engine = create_db_engine(Settings(_env_file=None))
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO videos (id,youtube_video_id,youtube_url,current_revision_id) VALUES ('v','newvideo001','url','r2')"))
        connection.execute(text("INSERT INTO processing_jobs (id,video_id,stage) VALUES ('j','v','completed')"))
        connection.execute(text("INSERT INTO raw_transcript_cues (id,video_id,sequence_index,start_seconds,end_seconds,text,source_type,source_payload) VALUES ('cue','v',0,0,1,'Source','youtube_manual','{}')"))
        for number in (1, 2):
            connection.execute(text("INSERT INTO transcript_revisions (id,video_id,origin,revision_number) VALUES (:r,'v','source_aligned',:n)"), {'r': f'r{number}', 'n': number})
            connection.execute(text("""INSERT INTO learning_transcript_segments
                (id,video_id,revision_id,sequence_index,text,translation_zh,start_seconds,end_seconds,source_ref_type,source_refs,normalization_version)
                VALUES (:s,'v',:r,0,'Hello world','你好',0,1,'source_units','{}',NULL)"""), {'s': f's{number}', 'r': f'r{number}'})
            connection.execute(text("""INSERT INTO transcript_marks
                (id,video_id,revision_id,segment_id,start_offset,end_offset,selected_text,note)
                VALUES (:m,'v',:r,:s,0,5,'Hello','Delete personal note')"""), {'m': f'm{number}', 's': f's{number}', 'r': f'r{number}'})
            connection.execute(text("""INSERT INTO transcript_mark_keys
                (video_id,revision_id,segment_id,start_offset,end_offset,mark_id)
                VALUES ('v',:r,:s,0,5,:m)"""), {'m': f'm{number}', 's': f's{number}', 'r': f'r{number}'})
        connection.execute(text("""INSERT INTO transcript_questions
            (id,video_id,revision_id,segment_id,start_offset,end_offset,selected_text,question,answer,has_saved_answer)
            VALUES ('q','v','r1','s1',0,5,'Hello','Delete question','Delete answer',1)"""))
        connection.execute(text("INSERT INTO transcript_chunk_layouts (id,video_id,revision_id,content_sha256) VALUES ('l','v','r2',:digest)"), {'digest': 'a' * 64})
        connection.execute(text("INSERT INTO transcript_chunk_segments (id,layout_id,segment_id,boundary_offsets) VALUES ('b','l','s2','[5]')"))
        connection.execute(text("INSERT INTO video_collections (id,name,version) VALUES ('c','Keep',1)"))
        connection.execute(text("INSERT INTO video_collection_items (id,collection_id,video_id,position) VALUES ('i','c','v',0)"))
    before = snapshot(engine)
    command.upgrade(config, 'head')
    command.check(config)
    after = snapshot(engine)
    assert 'transcript_questions' not in after
    for table, rows in before.items():
        if table in ('alembic_version', 'transcript_questions'):
            continue
        expected = [{k: v for k, v in row.items() if k != 'note'} for row in rows] if table == 'transcript_marks' else rows
        assert after[table] == expected, table
    with engine.connect() as connection:
        assert not connection.execute(text('PRAGMA foreign_key_check')).all()
        assert connection.scalar(text('PRAGMA integrity_check')) == 'ok'
    command.downgrade(config, '014_retire_legacy_subtitles')
    restored = snapshot(engine)
    assert restored['transcript_questions'] == []
    assert all(row['note'] is None for row in restored['transcript_marks'])
    assert restored['transcript_mark_keys'] == before['transcript_mark_keys']
    command.upgrade(config, 'head')
    command.check(config)
    engine.dispose()
