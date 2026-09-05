"""Migrations, schema drift and database-enforced append-only evidence."""

from __future__ import annotations

import uuid

import psycopg
import pytest
from alembic import command
from alembic.config import Config


def test_integrity_migration_backfills_provenance_and_freezes_evidence(monkeypatch) -> None:
    schema = f"integrity_{uuid.uuid4().hex}"
    url = "postgresql://clearledger:clearledger@localhost:5432/clearledger_test"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        monkeypatch.setenv(
            "DATABASE_DIRECT_URL",
            url.replace("postgresql://", "postgresql+psycopg://")
            + f"?options=-csearch_path%3D{schema}",
        )
        config = Config("alembic.ini")
        command.upgrade(config, "9f3a8b2e5d1d")
        with psycopg.connect(url, options=f"-csearch_path={schema}", autocommit=True) as connection:
            run_id = connection.execute(
                "INSERT INTO reconciliation_runs(status,dataset_checksum,config) "
                "VALUES ('COMPLETED','historical-dataset-checksum',"
                "'{\"dataset_id\":\"historical_batch\"}') RETURNING id"
            ).fetchone()[0]
            candidate_id = connection.execute(
                "INSERT INTO candidate_relationships(reconciliation_run_id,source_entity_id,"
                "target_entity_id,relationship_type,match_score,decision_level,"
                "allocated_amount_paise) VALUES "
                "(%s,'s','b','settlement_bank',600000,'UNRESOLVED',1) "
                "RETURNING id",
                (run_id,),
            ).fetchone()[0]
            decision_ids = [
                connection.execute(
                    "INSERT INTO human_decisions(case_id,reconciliation_run_id,action,actor,"
                    "previous_state,new_state,created_at) VALUES "
                    "('CASE-001',%s,%s,'reviewer','UNRESOLVED',%s,%s) RETURNING id",
                    (run_id, action, new_state, created_at),
                ).fetchone()[0]
                for action, new_state, created_at in (
                    ("ASSIGN", "ASSIGNED", "2026-08-30T10:00:00+00:00"),
                    ("APPROVE", "RESOLVED", "2026-08-31T10:00:00+00:00"),
                )
            ]
            source_ids: list[uuid.UUID] = []
            expected_checksums: dict[str, str] = {}
            for source_type in (
                "orders",
                "payments",
                "settlements",
                "settlement_components",
                "bank_transactions",
            ):
                checksum = f"checksum-{source_type}"
                source_ids.append(
                    connection.execute(
                        "INSERT INTO source_files(filename,source_type,file_checksum,"
                        "ingestion_quality,reconciliation_run_id) VALUES (%s,%s,%s,'VALID',%s) "
                        "RETURNING id",
                        (f"{source_type}.csv", source_type, checksum, run_id),
                    ).fetchone()[0]
                )
                expected_checksums[f"{source_type}.csv"] = checksum
            idempotency_id = connection.execute(
                "INSERT INTO idempotency_records(scope,idempotency_key,request_checksum,"
                "response_status,response_payload) VALUES "
                "('runs:create','historical-key','historical-request',201,'{\"id\":\"run\"}') "
                "RETURNING id"
            ).fetchone()[0]
        command.upgrade(config, "head")
        command.check(config)
        with psycopg.connect(url, options=f"-csearch_path={schema}", autocommit=True) as connection:
            assert (
                connection.execute(
                    "SELECT match_score FROM candidate_relationships WHERE id=%s", (candidate_id,)
                ).fetchone()[0]
                == 6000
            )
            run_revision, input_manifest = connection.execute(
                "SELECT review_revision,input_manifest FROM reconciliation_runs WHERE id=%s",
                (run_id,),
            ).fetchone()
            assert run_revision == 2
            assert input_manifest == {
                "dataset_id": "historical_batch",
                "file_checksums": expected_checksums,
                "provenance_status": "reconstructed",
            }
            decisions = connection.execute(
                "SELECT id,execution_revision,review_revision FROM human_decisions "
                "WHERE reconciliation_run_id=%s ORDER BY created_at,id",
                (run_id,),
            ).fetchall()
            assert decisions == [
                (decision_ids[0], 1, 1),
                (decision_ids[1], 1, 2),
            ]
            assert connection.execute(
                "SELECT state,claim_token,lease_expires_at FROM idempotency_records WHERE id=%s",
                (idempotency_id,),
            ).fetchone() == ("COMPLETED", None, None)
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    "UPDATE candidate_relationships SET match_score=10001 WHERE id=%s",
                    (candidate_id,),
                )
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                connection.execute(
                    "UPDATE reconciliation_runs SET dataset_checksum='altered' WHERE id=%s",
                    (run_id,),
                )
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                connection.execute(
                    "UPDATE source_files SET file_checksum='altered' WHERE id=%s",
                    (source_ids[0],),
                )
            event_id = connection.execute(
                "INSERT INTO audit_events(event_type) VALUES ('TEST') RETURNING id"
            ).fetchone()[0]
            raw_id = connection.execute(
                "INSERT INTO raw_source_rows(source_file_id,row_number,raw_payload,quality) "
                "VALUES (%s,1,'{}','VALID') RETURNING id",
                (source_ids[0],),
            ).fetchone()[0]
            for sql, identifier in [
                ("UPDATE audit_events SET event_type='ALTERED' WHERE id=%s", event_id),
                ("DELETE FROM audit_events WHERE id=%s", event_id),
                ("UPDATE raw_source_rows SET raw_payload='{\"changed\":true}' WHERE id=%s", raw_id),
                ("DELETE FROM raw_source_rows WHERE id=%s", raw_id),
            ]:
                with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                    connection.execute(sql, (identifier,))
            with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
                connection.execute("TRUNCATE audit_events")
            assert (
                connection.execute(
                    "SELECT event_type FROM audit_events WHERE id=%s", (event_id,)
                ).fetchone()[0]
                == "TEST"
            )
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
