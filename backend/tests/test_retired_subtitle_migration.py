"""Verify legacy removal guards and reversible schema changes with real children."""
import json
from pathlib import Path

import pytest
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


@pytest.mark.parametrize('legacy', ['cloud_run', 'external_srt', 'old_version'])
def test_upgrade_refuses_legacy_rows_before_any_changes(tmp_path, monkeypatch, legacy):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "legacy.db"}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '013_import_retries')
    engine = create_db_engine(Settings(_env_file=None))
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO videos (id,youtube_video_id,youtube_url) VALUES ('v','oldvideo001','url')"))
        if legacy == 'cloud_run':
            connection.execute(text("INSERT INTO processing_jobs (id,video_id,stage) VALUES ('j','v','completed')"))
            connection.execute(text("""INSERT INTO transcript_normalization_runs
                (id,video_id,job_id,method,normalization_version,provider,model,prompt_version,input_unit_count,request_count)
                VALUES ('n','v','j','llm',4,'provider','model','prompt',1,1)"""))
        else:
            origin = 'external_srt' if legacy == 'external_srt' else 'generated'
            connection.execute(text('INSERT INTO transcript_revisions (id,video_id,origin,revision_number) VALUES (\'r\',\'v\',:origin,1)'), {'origin': origin})
            if legacy == 'old_version':
                connection.execute(text("""INSERT INTO learning_transcript_segments
                    (id,video_id,revision_id,sequence_index,text,start_seconds,end_seconds,source_ref_type,source_refs,normalization_version)
                    VALUES ('s','v','r',0,'Old',0,1,'cue','{}',4)"""))
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match='remove retired subtitle records'):
        command.upgrade(config, '014_retire_legacy_subtitles')
    assert snapshot(engine) == before
    engine.dispose()


def test_populated_upgrade_and_downgrade_preserve_all_current_children(tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{tmp_path / "current.db"}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '013_import_retries')
    engine = create_db_engine(Settings(_env_file=None))
    with engine.begin() as connection:
        statements = [
            "INSERT INTO videos (id,youtube_video_id,youtube_url,current_revision_id) VALUES ('v','newvideo001','url','r')",
            "INSERT INTO processing_jobs (id,video_id,stage) VALUES ('j','v','completed')",
            "INSERT INTO transcript_normalization_runs (id,video_id,job_id,method,normalization_version,input_unit_count,request_count) VALUES ('n','v','j','deterministic',2,1,0)",
            "INSERT INTO transcript_revisions (id,video_id,origin,revision_number) VALUES ('r','v','generated',1)",
            "INSERT INTO learning_transcript_segments (id,video_id,revision_id,sequence_index,text,translation_zh,start_seconds,end_seconds,source_ref_type,source_refs,normalization_version,normalization_run_id) VALUES ('s','v','r',0,'Hello world','你好',0,1,'cue','{}',2,'n')",
            "INSERT INTO transcript_marks (id,video_id,revision_id,segment_id,start_offset,end_offset,selected_text,note) VALUES ('m','v','r','s',0,5,'Hello','Keep note')",
            "INSERT INTO transcript_mark_keys (video_id,revision_id,segment_id,start_offset,end_offset,mark_id) VALUES ('v','r','s',0,5,'m')",
            "INSERT INTO transcript_questions (id,video_id,revision_id,segment_id,start_offset,end_offset,selected_text,question,answer,has_saved_answer) VALUES ('q','v','r','s',0,5,'Hello','Why?','Answer',1)",
            "INSERT INTO transcript_chunk_layouts (id,video_id,revision_id,content_sha256) VALUES ('l','v','r','" + 'a'*64 + "')",
            "INSERT INTO transcript_chunk_segments (id,layout_id,segment_id,boundary_offsets) VALUES ('b','l','s','[5]')",
        ]
        for statement in statements:
            connection.execute(text(statement))
    before = snapshot(engine)
    command.upgrade(config, '014_retire_legacy_subtitles')
    after = snapshot(engine)
    for table, rows in before.items():
        if table in ('alembic_version','transcript_normalization_runs','transcript_corrections','transcript_normalization_batches'):
            continue
        assert after[table] == rows, table
    assert after['transcript_normalization_runs'][0]['input_unit_count'] == 1
    assert 'provider' not in after['transcript_normalization_runs'][0]
    with engine.connect() as connection:
        assert not connection.execute(text('PRAGMA foreign_key_check')).all()
        assert connection.scalar(text('PRAGMA integrity_check')) == 'ok'
    command.downgrade(config, '013_import_retries')
    assert snapshot(engine) == before
    engine.dispose()
