# AI usage record

## Tools used

- ChatGPT
- Claude
- Antigravity

## Important prompts or prompt summaries

For each fix, I followed a structured AI-assisted workflow:

1. **Problem analysis:** I first used ChatGPT to understand the defect, the relevant contract requirements, and possible solutions.
2. **Prompt preparation:** I then worked with ChatGPT to create a focused, customized prompt for Claude/Antigravity to inspect the repository and propose an implementation approach.
3. **Approach review:** I reviewed the approach returned by Claude/Antigravity, challenged assumptions and unnecessary complexity, and asked for changes or clarification when needed before approving it.
4. **Implementation and testing:** Once the approach was approved, I instructed Claude/Antigravity to implement only the agreed changes and add focused tests. I then reviewed the implementation and ran the test suite.
5. **Final review:** After all fixes were completed, I used ChatGPT to create a final review prompt covering correctness, tests, scope, trade-offs, remaining risks, and documentation.

The individual prompts were lengthy and followed this same workflow for each fix, so they are summarized here rather than reproduced in full. The final review prompt is included at the end of this file.

## Generated output rejected or corrected

### 1. `PRAGMA foreign_keys = OFF`

AI initially suggested disabling foreign-key enforcement during the table rebuild.
I challenged the suggestion and verified that `telemetry_events` is a leaf table with no tables referencing it, so there was no concrete failure requiring this change.
**Action:** I did not add the pragma.

### 2. Existing data could violate the new unique constraint

AI initially raised this as a migration risk.
I challenged it and verified that the old constraint was:
`UNIQUE (device_id, sequence)` while the new constraint is: `UNIQUE (device_id, boot_id, sequence)`
The new constraint is less restrictive, so existing valid data does not create a conflict.
**Action:** I did not add any data-cleanup logic.

### 3. Optional WebSocket architecture was not added

AI proposed several possible improvements, including per-client message queues, environment/config-file based timeout configuration, dropped-client logging, and concurrent sends with `asyncio.gather()`.
I reviewed these against the assignment scope and kept the simpler configurable timeout-and-drop implementation.
**Action:** I did not add these optional improvements.

### 4. Additional slow-client test was not added

AI proposed a third test where a slow client eventually succeeds after the timeout.
I determined that the slow-client isolation test and the send-error regression test already covered the required behavior, while the additional test was not necessary for the assignment.
**Action:** I did not add the third test.

### 5. Test strengthening and implementation corrections

AI initially relied on the iteration order of the WebSocket client set for the slow-client test. I identified that this would not reliably prove that the slow client was encountered first.
I required the test to explicitly arrange the slow client first and also corrected the formatting of the `asyncio.wait_for()` call.
**Action:** I kept these corrections and verified the full test suite after the changes.

### 6. Redundant duplicate assertion

AI suggested adding another assertion combining the cross-boot and same-boot duplicate cases.
I determined that the existing tests already covered both behaviors.
**Action:** I did not add the additional assertion.

## Verification performed

- Reviewed the proposed approach before allowing implementation, and challenged or refined it when assumptions or unnecessary complexity were identified.
- After implementation, reviewed the changed files and the relevant code to understand why each change was made and check for issues.
- Reviewed the production and test Git diffs to confirm that only the intended changes were included.
- Compared the implementation against the protocol and runtime contracts in `docs/`.
- Ran the full test suite after completing the fixes.
- Final test result: `15 passed, 0 failed`.
- Reviewed the final `DECISIONS.md` and `AI_USAGE.md` to ensure they accurately describe the implemented changes, tests, trade-offs, and remaining risks.

## Final review prompt

Review the complete implementation against the assignment requirements and docs/ contracts. We have completed six required problem areas:

1. Event identity / duplicate idempotency
2. Device boot separation
3. Current-state ordering and incorrect device clocks
4. Transaction and realtime publication boundary
5. Slow WebSocket client isolation / bounded memory
6. Dashboard reconnect recovery

Please review the ENTIRE repository and verify:

- Each of the six requirements is actually satisfied by the current implementation.
- The relevant existing/new tests cover each behavior appropriately.
- Run the full test suite and confirm all tests pass.
- Identify any requirement that is only partially covered or has a meaningful remaining risk.
- Check that we did not make unnecessary architectural or scope-expanding changes.
- Check that the implementation remains understandable and maintainable.
- Do not modify production code or tests unless you find a genuine correctness issue. If you find one, STOP and explain it before changing anything.

For each of the six fixes, report concisely:

- Problem
- What was changed
- Tests covering it
- Status
- Important design choice / trade-off
- Remaining risk or limitation, if any

Be especially careful to distinguish between:
- What the assignment/contracts explicitly require.
- What our implementation actually guarantees.
- What is a deliberate trade-off or known limitation.

Do not invent risks or trade-offs that do not actually apply.

Also review the assignment requirements around:

- System and data-model reasoning
- Correctness under failure and reordering
- Tests and debugging method
- Scope control and maintainability
- Risk prioritization
- Ability to direct and verify AI-generated work
- Trade-offs and remaining risks

After the review, create:

docs/REVIEW.md

Keep it concise and factual. Organize it by the six fixes. Include a short final section containing:

- Full test result
- Files changed across the six fixes
- Overall scope/maintainability assessment
- Remaining risks or incomplete requirements
- Important trade-offs we made

Do not write a long essay.

Do not create or modify any other documentation files.

Do not make implementation changes unless you find a genuine correctness issue. If you find one, STOP before changing anything and explain the issue first.