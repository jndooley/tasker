# Tasker

Tasker is a lightweight command-line task tracker built for AI agents. It keeps focus tight on current development work with fast commands and minimal dependencies.

## Features
- Task CRUD with status (`todo`, `in-progress`, `done`) and priority (`none`, `low`, `medium`, `high`)
- Optional per-task acceptance criteria list for richer context
- Project context management with a single active project
- `focus` command tells you the next task to work on
- Rich terminal output with JSON option for agents

## Installation
```
pip install -e .
```

## Usage
Initialize a project (defaults to current directory):
```
tasker init
```
Add tasks and list them:
```
tasker add "Implement models" -p high
tasker add "Wire API client" \
  --acceptance-criteria "Auth token refreshes automatically" \
  --acceptance-criteria "Retries transient 5xx responses"
tasker list
```
See what to work on:
```
tasker focus
```

See `tasker --help` for the full command list.
