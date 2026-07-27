# Repository Engineering Policy

## Scope and precedence

- Trigger: Any change or investigation in this repository.
- Requirement: Agents and contributors MUST follow this file for engineering process. The contracts in `design/overlay_scenes_spec.md` and `design/overlay_scenes_architecture.md` MUST govern product behavior. Higher-priority user or system instructions take precedence over this file; conflicts MUST be reported explicitly.
- Verification: Before editing, read the design files relevant to the requested behavior and inspect the current worktree.
- Exception: A user MAY explicitly replace a design decision for the requested change. The resulting contract change MUST be documented in the same change.

## Evidence-based debugging

- Trigger: Diagnosing a defect, regression, integration failure, or unexpected behavior.
- Requirement: NEVER guess the root cause. Capture expected behavior, actual behavior, and concrete evidence from an automated test, deterministic reproduction, Home Assistant log, trace, compiler, or linter before editing production code. Assumptions MUST be written down and verified.
- Verification: The change report MUST identify the evidence that established the cause and connect the fix to that evidence.
- Exception: Exploratory instrumentation MAY be added to gather evidence, but it MUST NOT be presented as a fix and MUST be removed unless it has lasting diagnostic value.

## Bug fixes: red-green-refactor

- Trigger: Any change described as a bug fix or regression fix.
- Requirement: Follow red-green-refactor in this order:
  1. Red: add an automated test that reproduces the exact defect and confirm it fails for the expected reason.
  2. Green: implement the smallest production change that makes the new test pass.
  3. Refactor: improve the implementation only while all relevant tests remain green.
- Verification: Record the failing test result before the implementation and the passing result afterward.
- Exception: If an automated failing test cannot be produced, STOP. Do not implement the fix. Treat the missing reproduction as insufficient understanding and ask the user for more evidence or clarification.

## Python and TypeScript type safety

- Trigger: Writing or modifying typed Python or introducing TypeScript.
- Requirement: NEVER bypass a type error to force compilation. Python code MUST NOT use unjustified `# type: ignore`, untyped escape hatches, or unsafe casts that conceal an invalid model. TypeScript MUST NOT use `as any`, `as unknown as`, double-cast chains, unsafe assertions used as type escapes, or the non-null assertion operator (`!`). If typing blocks progress, redesign the types or data flow.
- Verification: Run the applicable type checker when the repository provides one. Every suppression MUST be scoped to one expression or line and include a specific reason comment.
- Exception: A library-boundary cast or suppression is allowed ONLY IF the upstream type is demonstrably incorrect or incomplete, runtime validation protects the boundary, and the reason is documented beside the suppression.

- Trigger: Declaring local variables in TypeScript.
- Requirement: Use `const` by default. `let` is allowed ONLY IF reassignment is required by the algorithm. Mutable variables MUST NOT be introduced merely for convenience.
- Verification: Review each new `let` declaration for necessary reassignment.
- Exception: Framework-generated code MAY follow the framework's generated convention and MUST NOT be manually edited.

- Trigger: Representing missing, uninitialized, error, or fallback state in any language.
- Requirement: NEVER use `""` or `0` as a sentinel. Use explicit nullability, an enum, a tagged state, or a dedicated result type.
- Verification: Tests MUST cover the explicit missing/error state separately from valid empty-string or zero values when those are valid domain data.
- Exception: An external Home Assistant API value MAY contain `""` or `0`; it MUST be normalized at the integration boundary before internal use when it represents a sentinel.

## Home Assistant integration contracts

- Trigger: Changing config flows, config subentries, services, storage, entities, templates, event listeners, contexts, or write-through behavior.
- Requirement: Verify the current Home Assistant developer contract from official documentation or the installed Home Assistant source before implementation. NEVER assume an unstable API from memory.
- Verification: Add focused tests for the relevant boundary and report the Home Assistant version or official contract used.
- Exception: If current documentation or a runnable Home Assistant environment is unavailable, implementation MAY proceed only for version-stable pure logic. Runtime-facing changes MUST be reported as unverified and MUST NOT be declared complete.

- Trigger: Changing source eviction, modifier ordering, lifecycle expiry, persistence, or base-state feedback behavior.
- Requirement: Preserve per-`Channel` occupancy and lifecycle semantics. A multi-channel layer MUST support partial eviction. Write-through events MUST NOT replace the last externally authored base value.
- Verification: Update or add coverage in the registry, lifecycle, feedback, and scenario-walkthrough tests for the affected contract.
- Exception: Any change to these semantics REQUIRES EXPLICIT USER APPROVAL and a corresponding update to both design documents.

## Async reliability

- Trigger: Creating a coroutine, task, timer, callback, event subscription, or service call.
- Requirement: NEVER leave an awaitable unawaited or an exception path unobserved. Coroutines MUST be awaited or deliberately scheduled through Home Assistant's task APIs. Every timer and subscription MUST have an explicit cancellation path on eviction or unload.
- Verification: Tests MUST cover completion, cancellation, unload, and failure behavior for changed async lifecycle code.
- Exception: Fire-and-forget work is allowed ONLY through the Home Assistant-supported scheduling API and ONLY IF failures remain observable in Home Assistant logs.

## Persistence and migrations

- Trigger: Changing persisted storage format, config-entry version, or any future migration file.
- Requirement: Existing migration files are immutable. Functional or schema changes MUST use a new migration. In-place edits are allowed ONLY for a non-functional corrective repair of a broken migration that is still in progress and has not been released or applied.
- Verification: Persistence changes MUST include upgrade, restart/restore, expired-record, and backward-compatibility tests as applicable.
- Exception: Formatting or comment-only changes MAY be made to an unapplied in-progress migration when they cannot alter execution.

- Trigger: Changing a stored public format or removing a persisted field.
- Requirement: Maintain backward compatibility unless the user explicitly approves a breaking change. NEVER add an undocumented compatibility alias or silent migration shim.
- Verification: Test data from the previous supported format MUST load successfully, or the approved breaking migration MUST fail with an actionable error.
- Exception: Corrupt data MAY be rejected when the rejection is logged without exposing secrets and recovery steps are documented.

## Database permission gate

- Trigger: Any change that would affect a database, including schema changes, data migrations, destructive database commands, resets, or executing migration tooling.
- Requirement: Database-affecting execution REQUIRES EXPLICIT HUMAN USER APPROVAL after the user has reviewed the exact proposed change. Autopilot approval is NEVER sufficient. STOP and ask before executing the change.
- Verification: The work log MUST identify the approved command and scope before execution.
- Exception: Drafting a new migration file for review does not itself affect a database and does not require execution approval. The migration MUST NOT be run, applied, or represented as verified against a database without explicit approval.

## Security and secrets

- Trigger: Handling entity data, templates, service inputs, logs, credentials, tokens, or configuration exports.
- Requirement: NEVER commit or log credentials, tokens, private configuration, or unnecessary entity-state data. Validate service inputs and template results at trust boundaries. Error logs MUST be actionable without exposing secrets.
- Verification: Inspect the final diff and changed logging statements for sensitive values and unbounded user-controlled content.
- Exception: Sanitized fixtures MAY contain clearly fictional values that cannot be mistaken for live credentials.

## Integration before invention

- Trigger: Adding a new model, coordinator, registry, storage wrapper, lifecycle mechanism, or helper.
- Requirement: First inspect whether the existing `Channel`, `Layer`, registry, lifecycle, runtime, store, or Home Assistant helper can represent the requirement. NEVER create a parallel abstraction for an existing domain concept when reuse or a focused refactor is sufficient.
- Verification: The change rationale MUST name the existing abstractions considered for any new shared abstraction.
- Exception: A new abstraction is allowed when evidence shows the existing one cannot preserve the required contract without mixing unrelated responsibilities.

## API compatibility

- Trigger: Changing service names or schemas, entity unique IDs, storage keys, config-entry/subentry data, public models, or documented behavior.
- Requirement: Public contracts MUST remain stable unless breaking changes receive explicit user approval. A breaking change MUST include migration and release notes where applicable.
- Verification: Existing contract tests MUST remain green, and new tests MUST cover both the retained contract and any approved migration path.
- Exception: NEVER add backward-compatibility aliases or migration shims unless the user explicitly requests them.

## Linting and formatting

- Trigger: A repository-provided auto-fix or formatting command exists for the changed file type.
- Requirement: Run the repository's auto-fix command before manual style-only edits. Manually fix ONLY residual issues the tool cannot resolve.
- Verification: Report the auto-fix and final lint results.
- Exception: This repository currently defines no formatter or lint command. Until one is added, do not invent or install tooling solely to reformat a change; preserve the surrounding style and run `git diff --check`.

- Trigger: Adding a lint, type-check, or test suppression.
- Requirement: Suppressions MUST be rare, minimal in scope, and accompanied by a reason explaining why a code-level solution is not correct. Broad or unexplained suppressions are prohibited.
- Verification: Review every new suppression in the final diff.
- Exception: Generated files MAY contain generator-owned suppressions and MUST NOT be manually edited.

## Verification gates

- Trigger: Before declaring any implementation complete.
- Requirement: Run all relevant automated tests for the changed scope, plus applicable type, lint, syntax, JSON, and formatting checks. At minimum, Python changes MUST parse and `git diff --check` MUST pass. Home Assistant runtime changes MUST be exercised in a compatible Home Assistant test environment before being represented as runtime-verified.
- Verification: Report each command and result. If a check cannot run, report the blocker and specific residual risk; NEVER imply that an unrun check passed.
- Exception: Documentation-only changes MAY omit runtime tests, but Markdown links, referenced commands, and changed examples MUST still be checked.

- Trigger: Claiming correctness, compatibility, or performance.
- Requirement: Claims MUST be supported by a like-for-like automated test, deterministic reproduction, benchmark, or runtime observation.
- Verification: Include the relevant before/after result or artifact in the handoff.
- Exception: No exception. Unsupported claims MUST be labeled as assumptions or omitted.

## Naming conventions

- Trigger: Creating a new file or directory.
- Requirement: Use kebab-case names unless a framework, language, Home Assistant, or generated-file convention requires another format. Python modules and tests MUST follow Python/Home Assistant snake_case conventions, including required names such as `config_flow.py`, `services.yaml`, and `strings.json`.
- Verification: Compare new paths with the applicable framework convention before completion.
- Exception: Existing paths MUST NOT be renamed solely to satisfy this rule, and externally required filenames MUST retain their prescribed spelling.

- Trigger: Naming models, services, entities, fields, operations, or lifecycle reasons.
- Requirement: Reuse terminology from the design documents and existing public contracts. Names MUST describe domain meaning rather than implementation mechanics.
- Verification: Search the repository for an existing term before introducing a synonym.
- Exception: An external API name MUST be preserved at the boundary even when it differs from internal terminology.

## Generated artifacts and scope control

- Trigger: Tools create caches, bytecode, reports, generated fixtures, or build output.
- Requirement: NEVER commit generated artifacts unless the repository explicitly tracks them. Remove `__pycache__`, `.pyc`, temporary reports, and equivalent local output before handoff.
- Verification: Inspect `git status --short` and the final diff.
- Exception: Framework-required generated artifacts MAY be committed only when their source and regeneration process are documented.

- Trigger: Implementing any requested change.
- Requirement: Keep the diff limited to the requested behavior and its tests/documentation. Preserve unrelated user changes in the worktree.
- Verification: Review `git status --short` and the complete diff before completion.
- Exception: A prerequisite refactor MAY be included only when it is necessary for the requested behavior and remains covered by the same verification gates.

## UI policy

- Trigger: Adding a future custom card, panel, or other non-trivial UI.
- Requirement: Add representative stories or the repository's equivalent component harness and visual-regression coverage when that infrastructure exists. Browser-visible behavior MUST be verified in a real Home Assistant frontend.
- Verification: Report the story/harness cases and visual or browser test result.
- Exception: Tier 1 native config-flow forms and diagnostic entities do not require Storybook; they still require config-flow and entity tests.

## Temporary policy waivers

- Trigger: A requested change cannot comply with a rule in this file.
- Requirement: STOP and request explicit user approval for a narrow, time-bounded waiver. State the rule, reason, risk, scope, and follow-up required. NEVER infer a waiver from urgency or prior approval for a different change.
- Verification: Record the approval and ensure the implementation does not exceed its scope.
- Exception: Higher-priority system instructions override this policy without a waiver, but the conflict MUST be reported when allowed.
