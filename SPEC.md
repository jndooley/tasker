# Tasker Feature Spec: Notes Log & Code Reviews

## Context

Tasker is a lightweight task tracking tool for AI agents. Two new features are being added:

1. **Notes Log** — An append-only, timestamped commentary log per task. Useful for recording decisions, blockers, and observations as a task progresses. Semantically distinct from `description` (what the task is) and `plan` (how to implement it) — notes are the running log of *what happened*.

2. **Code Reviews** — Structured review records attached to tasks during the REVIEW phase. Each task can accumulate multiple CRs (one per review round). CRs capture reviewer details, recommendations, and two intellectual-honesty fields: devil's advocate (reviewer critiques their own recommendations) and false positives (issues raised but later ruled out).

---

## Feature 1: Notes Log

### Data Model

New table: `task_notes`

```sql
CREATE TABLE task_notes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id  INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    author   TEXT    NOT NULL,
    content  TEXT    NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

- Entries are **truly immutable** — no update or delete operations exposed
- Multiple entries per task, always ordered by `created_at` ascending
- Author is a required free-form string (e.g., `"jason"`, `"claude-agent"`)

### CLI

**Add a note:**
```
tasker note TASK_ID CONTENT --author NAME
```
- `--author, -a NAME` is required; fails if omitted or empty
- Fails if task does not exist

**View notes and CRs:**
```
tasker show TASK_ID --notes
```
- Without `--notes`: existing show behavior unchanged
- With `--notes`: appends notes log section and all CRs to output

### Display (in `tasker show TASK_ID --notes`)

```
Notes
─────────────────────────────────────────
[2026-03-01 14:23]  jason
Blocked on API credentials, following up with infra team.

[2026-03-01 16:45]  claude-agent
Credentials received, proceeding with implementation.
```

### Export

```
tasker export --include-notes
```
- Governs both notes and CRs in export output
- JSON: each task gains `"notes": [{"id": 1, "author": "...", "content": "...", "created_at": "..."}]`
- Markdown: notes rendered as a dated list under each task section

---

## Feature 2: Code Reviews

### Data Model

New table: `task_reviews`

```sql
CREATE TABLE task_reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    cr_num          INTEGER NOT NULL,   -- task-scoped, 1-based
    reviewer        TEXT,
    recommendations TEXT,
    devils_advocate TEXT,
    false_positives TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (task_id, cr_num)
);
```

- `cr_num` is task-scoped and 1-based: CR-1, CR-2, CR-3...
- All text fields are optional — a stub is valid with just `task_id`, `cr_num`, and `created_at`
- `updated_at` is refreshed on every `tasker cr update`

### Fields

| Field | Type | Description |
|---|---|---|
| `reviewer` | text | Name of the person conducting the review |
| `recommendations` | text | What the reviewer suggests should change |
| `devils_advocate` | text | Reviewer critiques their own recommendations — argues why they may be wrong or over-engineered |
| `false_positives` | text | Issues the reviewer initially raised but later determined were not real problems |
| `created_at` | timestamp | Auto-set when stub is created; not overridable |

### CR Creation Trigger

- When `tasker review TASK_ID` is called and the task has **no existing CRs**, a CR-1 stub is automatically created.
- Subsequent calls to `tasker review` on the same task do **not** auto-create new CRs (task already has at least one).
- Use `tasker cr add TASK_ID` to manually open a new review round (increments `cr_num`).
- Use `tasker cr delete TASK_ID CR_NUM` to remove a stub if the review passed with no issues.

### CLI Commands

**Modified existing command:**
```
tasker review TASK_ID
```
- Transitions task status to REVIEW (existing behavior preserved)
- If task has no CRs: auto-creates CR-1 stub and prints:
  `Created CR-1. Use 'tasker cr update {TASK_ID} 1' to fill in details.`

**New subcommand group: `tasker cr`**

```
tasker cr list TASK_ID
```
Lists all CRs for a task: cr_num, reviewer (if set), created_at, populated field count.

```
tasker cr show TASK_ID CR_NUM
```
Shows full detail of one CR.

```
tasker cr add TASK_ID
```
Creates a new CR stub (auto-increments `cr_num`).

```
tasker cr update TASK_ID CR_NUM [OPTIONS]
    --reviewer,        -r TEXT   Name of reviewer
    --recommendations, -R TEXT   Core findings and suggested changes (or - for stdin)
    --devils-advocate, -d TEXT   Reviewer's self-critique of their recommendations (or - for stdin)
    --false-positives, -f TEXT   Issues raised but ruled out (or - for stdin)
```

```
tasker cr delete TASK_ID CR_NUM
```
Deletes a CR. Prompts: `Delete CR-{N} for task {TASK_ID}? [y/N]`

### Display (in `tasker show TASK_ID --notes`)

```
Code Reviews
─────────────────────────────────────────
CR-1  2026-03-01 14:00  Reviewer: jason

  Recommendations
  Consider splitting the auth module into separate concerns.
  The retry logic in utils.py should use exponential backoff.

  Devil's Advocate
  These recommendations add complexity. The current approach is
  simpler and may be sufficient at the current scale.

  False Positives
  Initially flagged the caching layer as redundant — on closer
  review, the performance gains justify the added complexity.
```

### Export

Included when `tasker export --include-notes` is passed.

- JSON: each task gains `"reviews": [{"cr_num": 1, "reviewer": "...", "recommendations": "...", ...}]`
- Markdown: CRs rendered as structured subsections under each task

---

## Implementation Details

### Schema Migration

Version 8 adds both new tables. Both cascade-delete when the parent task is deleted.

### Files to Modify

| File | Changes |
|---|---|
| `tasker/database.py` | Add migration v8 creating `task_notes` and `task_reviews` |
| `tasker/models.py` | Add `Note` and `CodeReview` dataclasses |
| `tasker/queries.py` | Add CRUD functions for notes and reviews; modify `review_task()` |
| `tasker/cli.py` | Add `tasker note` command; add `tasker cr` group; modify `tasker review`; add `--notes` to `show`; add `--include-notes` to `export` |
| `tasker/formatter.py` | Add `format_notes()` and `format_reviews()` rendering functions |

### New Query Functions (queries.py)

**Notes:**
- `add_note(task_id, author, content) → Note`
- `get_notes(task_id) → List[Note]`

**Reviews:**
- `create_review_stub(task_id) → CodeReview` — auto-increments `cr_num`
- `get_reviews(task_id) → List[CodeReview]`
- `get_review(task_id, cr_num) → Optional[CodeReview]`
- `update_review(task_id, cr_num, *, reviewer, recommendations, devils_advocate, false_positives) → CodeReview`
- `delete_review(task_id, cr_num) → bool`
- `task_has_reviews(task_id) → bool`

**Modified:**
- `review_task(task_id)` — after status transition, calls `create_review_stub(task_id)` if `not task_has_reviews(task_id)`

### CR Numbering

`cr_num` is computed at insertion time:
```sql
SELECT COALESCE(MAX(cr_num), 0) + 1 FROM task_reviews WHERE task_id = ?
```
This is safe within a transaction but should be wrapped in one to avoid races.

---

## Verification Checklist

1. `pytest` — all existing tests pass with no regressions
2. Create a task, run `tasker note TASK_ID "content" --author jason`, verify entry stored
3. Try adding a second note, verify order is chronological in `tasker show --notes`
4. Try `tasker note TASK_ID "x"` without `--author`, verify error
5. Run `tasker review TASK_ID`, verify CR-1 stub auto-created
6. Run `tasker review TASK_ID` again, verify no second stub created
7. Run `tasker cr update TASK_ID 1 --reviewer jason --recommendations "..."`, verify fields stored
8. Run `tasker show TASK_ID --notes`, verify notes section and CR section both appear
9. Run `tasker show TASK_ID` (no flag), verify notes/CRs hidden
10. Run `tasker cr add TASK_ID`, verify CR-2 created with correct cr_num
11. Run `tasker cr delete TASK_ID 1`, verify prompt and deletion
12. Delete a task, verify cascade-deletes its notes and CRs
13. Run `tasker export --include-notes`, verify notes and CRs present in output
14. Run `tasker export` (no flag), verify notes/CRs absent from output
