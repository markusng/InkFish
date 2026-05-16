# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**inkfish** is a standalone desktop text editor whose distinguishing feature is **pinch-zoom and pan as the primary navigation model** — instead of scroll bars, users move around a document the way they would on a touchscreen. Goal: a natural, gestural reading and editing experience for long but structured documents (source code, long markdown, HTML).

## Stack

- Python 3.12+
- PyQt6

Env management, packaging, and test framework choices are not yet committed — see the spec referenced below.

## Run commands

- Set up env / install: `uv sync`
- Run the editor: `uv run inkfish [path]`
- Run tests: `uv run pytest`

## Architecture

The editing surface is a `QGraphicsView` + `QGraphicsScene` with the document as a graphics item inside. The view's transform (`scale`, `translate`) provides zoom and pan uniformly across input modes:

- Touchscreen pinch + pan, trackpad pinch + two-finger drag — wired through `QGestureEvent` / `Qt::PinchGesture`.
- Mouse fallback: Ctrl+wheel zoom, middle-click drag pan.

For `.md` / `.html` files, the source/rendered **toggle** (hotkey-driven, single mode visible at a time) swaps what's loaded into the same `QTextDocument` via `setMarkdown()` / `setHtml()` — one canvas, two modes.

Code folding is hotkey-driven and bracket / heading / tag based — language-agnostic where possible; no language-server dependency.

## Conventions

- Supported file formats: `.txt`, `.md`, `.html` only.
- Editor (not viewer): full read/write capability is mandatory.
- Single-document UI: one file open at a time. No tabs, no split panes, no infinite canvas.
- Monospace typography by default (Courier-class fonts).
- Touchscreen + trackpad are first-class input targets, not afterthoughts.

## Spec & open decisions

The full project context spec — motivation, scope boundaries, architectural alternatives, and open implementation decisions (distribution model, env tool, test framework, project layout, syntax highlighting scope, target document size, touch platform targets, save semantics) — lives at:

`C:\Users\mng\.claude\plans\help-me-define-project-tidy-cascade.md`

A refined version is being produced via Ultraplan and will land as a PR; once merged, this section should point at the in-repo location instead.
