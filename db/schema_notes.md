# Schema Notes

Authoritative monetary columns use `BIGINT` paise plus a required three-letter currency code.
Raw rows are immutable, evidence allocations are unique and bounded, and evaluator-only ground
truth is excluded from the production schema.
