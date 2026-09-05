"""Evidence graph and allocation-safety checks."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from packages.domain.enums import ActorType, DecisionLevel
from packages.domain.exceptions import InvariantError
from services.reconciliation.models import VerificationCheck


class EvidenceEdge(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)

    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    allocated_amount_paise: int
    rule_id: str
    rule_version: str
    evidence_fields: list[str]
    decision_level: DecisionLevel
    actor_type: ActorType
    verification_checks: list[VerificationCheck]
    created_at: datetime
    reconciliation_run_id: str


class EvidenceGraph:
    """In-memory graph for one deterministic reconciliation run."""

    def __init__(self) -> None:
        self._edges: list[EvidenceEdge] = []
        self._availability: dict[tuple[str, str], int] = {}
        self._allocated_abs: dict[tuple[str, str], int] = {}

    @property
    def edges(self) -> list[EvidenceEdge]:
        return list(self._edges)

    def register_available_amount(
        self,
        entity_id: str,
        relationship_type: str,
        available_amount_paise: int,
    ) -> None:
        self._availability[(relationship_type, entity_id)] = abs(available_amount_paise)

    def add_edge(self, edge: EvidenceEdge) -> None:
        if edge in self._edges:
            return
        if edge.decision_level == DecisionLevel.VERIFIED:
            self._assert_allocation_available(edge)
        self._edges.append(edge)
        if edge.decision_level == DecisionLevel.VERIFIED:
            for entity_id in {edge.source_entity_id, edge.target_entity_id}:
                key = (edge.relationship_type, entity_id)
                self._allocated_abs[key] = self._allocated_abs.get(key, 0) + abs(
                    edge.allocated_amount_paise
                )

    def remove_edge(self, edge: EvidenceEdge) -> None:
        if edge not in self._edges:
            return
        self._edges = [existing for existing in self._edges if existing != edge]
        if edge.decision_level == DecisionLevel.VERIFIED:
            for entity_id in {edge.source_entity_id, edge.target_entity_id}:
                key = (edge.relationship_type, entity_id)
                remaining = self._allocated_abs.get(key, 0) - abs(edge.allocated_amount_paise)
                if remaining:
                    self._allocated_abs[key] = remaining
                else:
                    self._allocated_abs.pop(key, None)

    def edges_for_entity(self, entity_id: str) -> list[EvidenceEdge]:
        return [
            edge
            for edge in self._edges
            if edge.source_entity_id == entity_id or edge.target_entity_id == entity_id
        ]

    def edges_by_relationship(self, relationship_type: str) -> list[EvidenceEdge]:
        return [edge for edge in self._edges if edge.relationship_type == relationship_type]

    def total_allocated_amount(self, entity_id: str, relationship_type: str | None = None) -> int:
        total = 0
        for edge in self._edges:
            if relationship_type is not None and edge.relationship_type != relationship_type:
                continue
            if edge.source_entity_id == entity_id or edge.target_entity_id == entity_id:
                total += edge.allocated_amount_paise
        return total

    def _current_abs_allocation(self, entity_id: str, relationship_type: str) -> int:
        return self._allocated_abs.get((relationship_type, entity_id), 0)

    def _assert_allocation_available(self, edge: EvidenceEdge) -> None:
        for role, entity_id in (
            ("source", edge.source_entity_id),
            ("target", edge.target_entity_id),
        ):
            availability = self._availability.get((edge.relationship_type, entity_id))
            existing = [
                candidate
                for candidate in self._edges
                if candidate.decision_level == DecisionLevel.VERIFIED
                and candidate.relationship_type == edge.relationship_type
                and (
                    candidate.source_entity_id == entity_id
                    or candidate.target_entity_id == entity_id
                )
            ]
            if availability is None:
                if edge.relationship_type == "payment_settlement" and role == "target":
                    continue
                if existing and all(
                    candidate.source_entity_id != edge.source_entity_id
                    or candidate.target_entity_id != edge.target_entity_id
                    for candidate in existing
                ):
                    raise InvariantError(
                        f"{entity_id} is already allocated for {edge.relationship_type}"
                    )
                continue

            proposed = self._current_abs_allocation(entity_id, edge.relationship_type) + abs(
                edge.allocated_amount_paise
            )
            if proposed > availability:
                raise InvariantError(
                    f"{entity_id} allocation {proposed} exceeds available {availability}"
                )

    def check_allocation_uniqueness(self) -> list[VerificationCheck]:
        checks: list[VerificationCheck] = []
        for (relationship_type, entity_id), available in sorted(self._availability.items()):
            allocated = self._current_abs_allocation(entity_id, relationship_type)
            checks.append(
                VerificationCheck(
                    check_id="allocation_uniqueness",
                    passed=allocated <= available,
                    expected_value=available,
                    actual_value=allocated,
                    affected_entities=[entity_id],
                    message=f"{relationship_type} allocation does not exceed availability",
                )
            )
        return checks
