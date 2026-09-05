from __future__ import annotations

from packages.domain.enums import ExceptionCode, IngestionQuality
from services.ingestion.service import ingest_file


def test_malformed_csv_row_remains_visible_as_invalid(tmp_path) -> None:
    path = tmp_path / "payments.csv"
    path.write_text(
        "payment_id,merchant_id,order_id,payment_status,amount_paise,currency,"
        "captured_at,payment_method,gateway_reference\n"
        "PAY_BAD,MERCHANT_001,ORD_001,captured,not-paise,INR,"
        "2026-08-01T10:00:00+00:00,upi,GW_BAD\n"
    )

    result = ingest_file(str(path), "payments")

    assert result.metadata.row_count == 1
    assert result.metadata.accepted_count == 0
    assert result.metadata.rejected_count == 1
    rejected = result.rejected_rows[0]
    assert rejected.source_record_id == "PAY_BAD"
    assert rejected.quality == IngestionQuality.INVALID
    assert rejected.raw_values["amount_paise"] == "not-paise"
    assert {issue.code for issue in rejected.issues} == {ExceptionCode.MALFORMED_INPUT}
