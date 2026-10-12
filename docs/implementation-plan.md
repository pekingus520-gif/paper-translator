# Translation desktop app Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Deliver an editable Windows/Linux desktop translator with live selection and screenshot OCR, two modes and configurable global pause.

**Architecture:** Qt owns all UI and request state. Translation/OCR workers are independent of platform input adapters; GNOME Wayland uses a selection-only bridge.

**Tech Stack:** Python 3.10+, PySide6, standard-library HTTP, Tesseract, keyring, python-xlib, Windows UI Automation.

**Spec:** design.md

## Global Constraints

- No visual styling work. Chinese UI and instructions.
- Default hotkeys Ctrl+Alt+S (screenshot), Ctrl+Alt+T (toggle).
- Selection settles for 450ms; no drag-in-progress request.
- Pause invalidates in-flight results; queues retain only latest request.
- Credentials belong to user; no live paid requests without their configuration.

## Review Focus

- Empty/stale OCR or PRIMARY text must not become a translation of old clipboard contents.
- Rapid selection, pause and mode changes must not show older results.
- API errors and invalid AI responses must not masquerade as reviewed translations.
- Unavailable keyring must not silently write plaintext credentials.
- Wayland permissions, unsupported apps and shortcut conflicts need visible diagnostics.

### Task 1: configuration, providers, request state
Files: src/paper_translator/{config,providers,state}.py; tests/test_core.py.
Interfaces: Settings; TranslationResult; Translator.translate(text, settings); RequestGate; SelectionDebouncer.
- [x] Write tests for HTTP signing, daily/paper flow, invalid JSON, config secrecy and disabled/stale results.
- [x] Run tests RED; implement contracts; run entire core suite GREEN.

### Task 2: OCR, IPC, cross-platform desktop app
Files: src/paper_translator/{ocr,ipc,capture,ui,app}.py; platforms/{windows,x11,wayland}.py; tests/test_desktop.py.
Interfaces: adapter signals selection/screenshot/toggle; app uses gate and translator, Qt IPC carries JSON commands; OCR returns text.
- [x] Write failing tests for OCR errors, valid/invalid IPC, pause while result pending, screenshot cancellation and settings.
- [x] Implement workers, plain UI, native adapters and portal capture; run suite and Qt offscreen smoke tests.

### Task 3: GNOME bridge and distribution
Files: gnome-bridge/*; scripts/*; README.md; pyproject.toml; tests/test_bridge.mjs.
- [x] Test selection settling and pause behavior before implementing bridge helper logic.
- [x] Implement bridge lifecycle, secure local transport and configurable shortcuts.
- [x] Verify JS syntax, GSettings schema, Python tests, Linux GUI/IPC smoke and build source package.
- [x] Review requirement checklist and document native Windows/Wayland and real API validation limits.

User explicitly instructed direct implementation and no style tuning; proceed inline without further design approval rounds. No existing Git repository; this output directory is the isolated new project.
