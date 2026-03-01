# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: Tasker

**Tasker** is a lightweight development task tracking application designed specifically for AI agents. It provides a clear and concise list of actions to take during development of a project, helping agents stay focused on the current task and mitigating unnecessary scope creep, code bloat, and context drift.

### Purpose

When AI agents work on development tasks, they can sometimes drift from the primary objective, add unnecessary features, or lose focus on what needs to be accomplished. Tasker acts as a focusing mechanism - similar to paid platforms like Traycer or Kiro - by maintaining an active task list that keeps agents on track.

### Core Features

1. **Task Management**: Create, update, and manage development tasks
2. **Project Context**: Set and track the current project directory being worked on
3. **Agent Focus**: Provide a clear interface for AI agents to check what they should be working on
4. **Lightweight Design**: Minimal overhead, simple to use, fast to query

### Design Principles

- **Simplicity**: Keep the tool small and focused on task tracking only
- **Agent-First**: Designed primarily for AI agent workflows, but usable by humans
- **No Scope Creep**: Ironically, the tool itself must avoid feature bloat and stay focused
- **Fast Queries**: Agents should be able to quickly check current tasks without significant overhead

## Current Structure

```
Tasker/
├── data/
│   └── cipher-sessions.db  # SQLite database (existing, may be repurposed)
└── CLAUDE.md
```

## Database

The project uses SQLite for data storage. The existing `data/cipher-sessions.db` may be repurposed or a new database may be created for task tracking.

## Notes

- This repository is not currently a git repository
- Implementation pending - needs architecture planning
