# Tasker

Tasker is a lightweight command-line task tracker built for AI agents. It keeps focus tight on current development work with fast commands and minimal dependencies.

## Features

- Task CRUD with status, priority, grouping, and implementation plans
- Acceptance criteria per task for richer context
- Task relations: `blocked-by`, `caused-by`, `related-to`
- Notes log: append-only timestamped commentary per task
- Code reviews: structured CR records attached to tasks
- Project context management with a single active project
- `focus` command tells you the next task to work on
- Export to JSON or Markdown
- Rich terminal output with JSON option for agents

## Installation

```
pip install -e .
```

## Usage

### Projects

```
tasker init                  # initialize project in current directory
tasker init /path/to/project # initialize at a specific path
tasker switch /other/project # switch active project
tasker project               # show active project
tasker projects              # list all projects
```

### Tasks

```
tasker add "Implement auth" -p high -s in-progress
tasker add "Wire API client" \
  --acceptance-criteria "Retries transient 5xx responses" \
  --acceptance-criteria "Auth token refreshes automatically" \
  --plan "Use httpx with retry middleware"
tasker list
tasker list --status in-progress
tasker list --group auth --group-by
tasker show TASK_ID
tasker update TASK_ID --title "New title" --priority medium
tasker delete TASK_ID
tasker reorder TASK_ID POSITION
```

### Status transitions

```
tasker start  TASK_ID   # → in-progress
tasker review TASK_ID   # → review (auto-creates CR-1 stub)
tasker qa     TASK_ID   # → qa
tasker done   TASK_ID   # → done
tasker block  TASK_ID BLOCKER_ID  # → blocked, adds blocked-by relation
```

### Task relations

```
tasker link   SOURCE_ID TARGET_ID --type blocked-by
tasker link   SOURCE_ID TARGET_ID --type caused-by
tasker link   SOURCE_ID TARGET_ID --type related-to
tasker unlink SOURCE_ID TARGET_ID --type blocked-by
```

### Groups

```
tasker add "Login page" -g auth
tasker groups
tasker list -g auth
```

### Notes (append-only log)

```
tasker note TASK_ID "Blocked on API credentials" --author jason
tasker note TASK_ID "Credentials received, proceeding" --author claude-agent
tasker show TASK_ID --notes   # show task + notes + code reviews
```

`--author` is required. Notes cannot be edited or deleted.

### Code reviews

```
tasker review TASK_ID              # transitions to review, auto-creates CR-1
tasker cr list   TASK_ID
tasker cr show   TASK_ID CR_NUM
tasker cr add    TASK_ID           # open a new review round (CR-2, CR-3, ...)
tasker cr update TASK_ID CR_NUM \
  --reviewer jason \
  --recommendations "Split the auth module" \
  --devils-advocate "May be premature at this scale" \
  --false-positives "Initially flagged caching as redundant — not the case"
tasker cr delete TASK_ID CR_NUM
```

Text fields (`--recommendations`, `--devils-advocate`, `--false-positives`) accept `-` to read from stdin.

### Focus and stats

```
tasker focus    # next task to work on (skips blocked tasks)
tasker stats    # task counts by status
tasker clean    # remove completed tasks
tasker clean --days 30
```

### Export

```
tasker export                        # JSON to stdout
tasker export --format md            # Markdown to stdout
tasker export out.json               # write to file
tasker export --include-notes        # include notes and code reviews in output
```

## Task statuses

| Status | Description |
|---|---|
| `todo` | Not yet started |
| `in-progress` | Actively being worked on |
| `blocked` | Waiting on another task |
| `review` | Ready for code review |
| `qa` | In quality assurance |
| `done` | Completed |

## Priority levels

`none` (default) · `low` · `medium` · `high`
