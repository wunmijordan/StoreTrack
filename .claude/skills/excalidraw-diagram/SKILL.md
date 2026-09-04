---
name: excalidraw-diagram
description: >
  Create clear, business-ready Excalidraw diagrams for StoreTrack architecture,
  operating flows, multi-tenant design, production workflows, finance flows, and pitch materials.
  Use when a user asks for a diagrammatic document, system map, process flow, or pitch visual.
version: "1.0"
updated: 2026-09-04
---

# Excalidraw Diagram — StoreTrack

Use this skill for diagrams intended for technical documentation, internal planning, onboarding, or business/investor/customer pitches.

## Goal

Turn StoreTrack concepts into a diagram that can be understood quickly without requiring the source code beside it. The diagram should be accurate enough for engineers while remaining legible to business stakeholders when the context is a pitch.

## Choose the diagram type first

Prefer one primary message per diagram:

- **Business capability map** — what StoreTrack manages from procurement through production, stock, sales, finance, and audit.
- **Production flow** — Order → Shared Production Run → proportional material release → ProductionBatch → customer/store/offcut/wastage/shortage.
- **Shared run allocation** — multiple customers/channels/products coordinated in one run while commercial orders remain separate.
- **Inventory traceability** — RawMaterial receipt → release → batch → FinishedGood → sale/reconciliation/non-stock destination.
- **Finance flow** — receivables/payables, CashAccount, FinancialTransaction, payment/reversal relationships.
- **Multi-tenant architecture** — Business ownership, request.business/session context, tenant-scoped data, global superuser boundary.
- **Pitch architecture** — simplified layers: users/channels, StoreTrack operating core, controls/analytics, integrations/future extensions.

Do not combine every one of these into a single unreadable canvas.

## Accuracy rules

- Distinguish **commercial Order** from **physical production**.
- Shared Production Runs group normal orders; they do not merge customers into one commercial order.
- Recipe consumption is proportional to product output against registered batch yield.
- Planned production/offcut, unexpected excess, wastage, and shortage are distinct concepts.
- Uncommitted planned offcut becomes general FinishedGood stock; committed offcut customer allocations create their own sales/receivables.
- Reversal is compensating/auditable, not silent history deletion.
- Database `Order.id` is technical/global; visible order numbering is business-specific where the current schema supports it.
- Keep Business/tenant ownership boundaries explicit on architecture diagrams.

## Visual language

For business-facing diagrams:

- use StoreTrack burgundy (`#8f172d`) as the dominant accent where the rendering tool permits;
- use a light neutral canvas;
- keep text short and high-contrast;
- use rounded boxes for business capabilities/entities and arrows for movement/state transitions;
- use green/amber/red only for semantic statuses, not decoration;
- prefer left-to-right operating flows;
- group related elements with labelled containers instead of dense crossing arrows.

For technical diagrams:

- label model names exactly (`Order`, `OrderItem`, `ProductionRun`, `ProductionBatch`, `Sale`, `CashAccount`, etc.);
- show cardinality only when it materially helps;
- distinguish data ownership from process movement;
- add a small legend when line styles have different meanings.

## Pitch-diagram discipline

A pitch diagram should explain value before implementation detail. Use language such as:

- Plan demand
- Release materials proportionally
- Produce & trace batches
- Allocate output across channels
- Reconcile stock and shortages
- Capture revenue & receivables
- Audit every movement

Keep model/table names out of the main pitch layer unless the audience is technical.

## File handling

- Prefer editable `.excalidraw` JSON as the source artifact.
- When the user needs something to insert into a pitch deck/document, also produce a clean PNG/SVG/PDF export when the available toolchain supports it.
- Store architecture sources under `docs/architecture/` unless the user specifies another destination.
- Use descriptive filenames, e.g. `shared-production-run-flow.excalidraw`.
- Never overwrite an existing diagram with materially different semantics without preserving or intentionally updating the source.

## Diagram QA

Before finalizing:

1. Can a non-engineer state the main message in under 15 seconds?
2. Are arrows unambiguous?
3. Are customer demand, production, stock, and finance kept conceptually separate?
4. Is text readable at normal document/slide scale?
5. Are there unnecessary crossings or duplicate labels?
6. Does the diagram reflect the current StoreTrack architecture rather than an earlier conversation state?

If the diagram documents implemented architecture, inspect the current models/views/docs before drawing it.
