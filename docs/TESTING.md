# ClearLedger Testing Strategy

## Test Coverage Summary

**Total: 199 Python Tests + TypeScript/Browser Tests**

### Test Suite Breakdown

#### Python Tests (199 total)
- **Unit Tests**: 154 tests
  - AI Contract Tests: 17 tests (validation, invariant checks)
  - Auth Tests: 11 tests (API key validation, security)
  - Case Presentation: 3 tests (UI data formatting)
  - Cash Forecast: 5 tests (forward cash flow calculations)
  - Control Package: 3 tests (evaluation provenance)
  - Enums: 2 tests (domain model stability)
  - Grounded Q&A: 8 tests (deterministic answers, injection protection)
  - Invariants: 10 tests (12 financial invariants)
  - Mock AI: 2 tests (offline testing)
  - Money Arithmetic: 13 tests (paise parsing, formatting, validation)
  - Matching Rules: 9 tests (deterministic matching logic)
  - Tax Audit: 4 tests (GST reconciliation)

- **Property-Based Tests**: 4 tests (Hypothesis)
  - Financial property invariants
  - Fuzzing input validation

- **Evaluator Tests**: 20 tests
  - Metrics calculation accuracy
  - Ground truth comparison

- **Prediction Integrity**: 5 tests
  - Checksum validation
  - Reproducibility

- **Generator Tests**: 38 tests
  - Scenario generation (clean lifecycle, timing delays, refunds, chargebacks, etc.)

- **Integration Tests**: 45 tests
  - API endpoint tests
  - Database persistence
  - Full workflow scenarios

#### Frontend Tests
- **TypeScript**: Type checking (0 errors)
- **ESLint**: Linting (0 errors)
- **Build**: Production build (successful)

## Test Commands

### Quick Unit Tests (No Database Required)
```bash
make test-unit
# Runs: 154 unit + property + evaluator + generator tests
# Duration: ~5 seconds
```

### Full Test Suite
```bash
make test
# Runs: All 199 Python tests + Frontend tests
# Duration: ~40 seconds
```

### Claims Verification
```bash
make verify-claims
# Validates:
# - Precision >= 1.0 ✓
# - Recall >= 0.95 ✓
# - False positives = 0 ✓
# - Zero unexplained residuals ✓
# - Reproducibility (same seed = same results) ✓
# - Performance (<10s for demo batch) ✓
```

### Security Scans
```bash
make secret-scan
# Scans for exposed credentials, API keys, private keys
```

### Stress Testing
```bash
make stress-test
# Tests 1,000 cases
# Measures: throughput, latency, memory
```

## Test Categories

### 1. Financial Invariant Tests (`test_invariants.py`)

Tests all 12 financial invariants that protect settlement integrity:

- **INV-001**: Currency consistency across all records
- **INV-002**: Order-to-payment amount matching
- **INV-003**: Settlement composition balance
- **INV-004**: Settlement-bank receipt verification
- **INV-005**: Zero residual (perfect balance)
- **INV-006**: Unique allocation (no double-counting)
- **INV-007**: Temporal validity (chronological order)
- **INV-008**: Lifecycle validity (state transitions)
- **INV-009**: SLA validity (timing windows)
- **INV-010**: Control total validation
- **INV-011**: Fee policy compliance
- **INV-012**: Tax policy compliance

### 2. Matching Rule Tests (`test_rules.py`)

Tests deterministic matching strategies:

- Exact order-payment ID matching
- Settlement component membership
- UTR-based bank matching
- Narration token fuzzy matching
- Amount-date-window matching
- Ambiguity detection
- Conflict resolution
- Priority ordering

### 3. Money Arithmetic Tests (`test_money.py`)

Tests integer-only financial calculations:

- Paise parsing (₹1,000.50 → 100050 paise)
- Precision rejection (no sub-paise values)
- Invalid input rejection (NaN, Infinity, non-numeric)
- Formatting (100050 paise → ₹1,000.50)
- Balance assertions (exact equality)

### 4. AI Contract Tests (`test_ai_contract.py`)

Tests AI system boundaries and safety:

- Response validation (structured JSON)
- Confidence score ranges (0-1)
- Entity ID extraction
- Invalid output rejection
- Deterministic checks (AI cannot override)
- Prompt injection protection
- Validation error handling

### 5. Grounded Q&A Tests (`test_grounded_qa.py`)

Tests read-only query system:

- Deterministic answers from computed data
- Case-specific queries
- Cash position queries
- Exception summaries
- Prompt injection rejection
- Unknown case ID handling
- No hallucination (only computed facts)

### 6. Integration Tests (`apps/api/tests/`)

Tests full API workflows:

- Run creation and file upload
- Validation endpoint
- Reconciliation execution
- Case retrieval and filtering
- Evidence graph queries
- Human review workflows (approve/reject/defer)
- AI analysis integration
- Export endpoints (CSV, JSON, Markdown)
- Evaluation endpoints

## Continuous Integration

### Pre-Commit Checks
```bash
# Type checking
pnpm --dir apps/web typecheck

# Linting
pnpm --dir apps/web lint

# Python tests
make test-unit
```

### Full CI Pipeline
```bash
# 1. Install dependencies
make install

# 2. Database setup
make db-up
make migrate

# 3. Generate test data
make generate-demo

# 4. Run all tests
make test

# 5. Verify claims
make verify-claims

# 6. Security scan
make secret-scan

# 7. Build frontend
pnpm --dir apps/web build
```

## Test Data

### Demo Dataset
- **Seed**: 20260827 (reproducible)
- **Cases**: 75
- **Source Records**: 693
- **Scenarios**: 12 types
  - Clean lifecycle: 20
  - Batched settlement: 10
  - Timing delay: 7
  - Holiday shift: 4
  - Refund: 6
  - Chargeback: 4
  - Split settlement: 4
  - Fee variance: 4
  - Messy narration: 5
  - Malformed input: 4
  - Missing event: 4
  - Ambiguous: 3

### Stress Dataset
- **Seed**: 99999 (reproducible)
- **Cases**: 1,000
- **Source Records**: 10,525
- **Scenarios**: Simplified (clean lifecycle + batched)

## Test Metrics

### Current Benchmarks (Demo Dataset)
| Metric | Value |
|--------|-------|
| Relationship Precision | 1.0000 |
| Relationship Recall | 1.0000 |
| Relationship F1 Score | 1.0000 |
| Case State Accuracy | 1.0000 |
| False Positive Count | 0 |
| Unexplained Residual | ₹0.00 |
| STP Rate | 70.67% |
| Monetary Reconciliation | 76.42% |

### Performance (Stress Test)
| Metric | Value |
|--------|-------|
| Throughput | 873 records/second |
| Case Processing | 83 cases/second |
| P50 Latency | 0.81 ms |
| P95 Latency | 0.92 ms |
| Peak Memory | 162 MB |

## Coverage Goals

Current coverage focuses on:
- ✅ Core financial logic (100%)
- ✅ Matching algorithms (100%)
- ✅ Invariant validation (100%)
- ✅ API endpoints (95%+)
- ✅ Error handling (100%)
- ✅ Security boundaries (100%)

## Running Specific Test Groups

```bash
# Only invariant tests
pytest tests/unit/test_invariants.py -v

# Only matching rules
pytest tests/unit/test_rules.py -v

# Only AI tests
pytest tests/unit/test_ai_contract.py tests/unit/test_mock_ai.py -v

# Only API integration tests
pytest apps/api/tests/ -v

# With coverage report
pytest --cov=services --cov=apps --cov-report=html
```

## Test Philosophy

ClearLedger testing follows these principles:

1. **Determinism First**: Every test produces same results on every run
2. **Integer Arithmetic**: No floating-point assertions in financial tests
3. **Offline Capable**: Unit tests never require network, DB, or live AI
4. **Fast Feedback**: Unit suite completes in <10 seconds
5. **Property Testing**: Use Hypothesis for fuzz testing edge cases
6. **Integration Reality**: Integration tests use real database transactions
7. **No Mocking Core Logic**: Only mock external APIs (AI, network)
8. **Reproducibility**: All generated data uses fixed seeds
9. **Claims Verification**: Every README claim has a test

## Test Failures

If tests fail:

1. **Check Prerequisites**: `make doctor`
2. **Clean State**: `make reset-demo`
3. **Update Dependencies**: `make install`
4. **Check Database**: Ensure PostgreSQL is running
5. **Review Logs**: Check test output for specific failures
6. **Environment**: Verify `.env` configuration

## Adding New Tests

When adding features:

1. Write unit tests first (TDD)
2. Add integration test for API endpoints
3. Update `verify-claims` if adding new metrics
4. Document test coverage in this file
5. Run full suite: `make test`

## Test Data Fixtures

Located in `tests/fixtures/` and generated by `generator/`:

- Reproducible synthetic data
- Covers all scenario types
- Includes edge cases
- Ground truth for evaluation
