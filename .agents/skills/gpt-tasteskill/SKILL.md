---
name: gpt-taste
description: Use for frontend UI implementation and visual direction in Academic Assistant: hierarchy, typography, spacing, purposeful motion and restrained composition.
---

Read AGENTS.md and docs/frontend-workflow.md first. This is a project-adapted GPT Taste skill, sourced from Leonxlnx/taste-skill. The unchanged upstream text is references/UPSTREAM.md for attribution and optional design ideas, not mandatory project instructions.

1. Inspect the existing component, surrounding screens and CSS tokens before proposing changes.
2. State the task's visual priority and simplest useful layout. Apply the Clean system with the app's existing green palette, typography and navigation.
3. Make primary actions obvious, labels concise, heading widths readable and spacing consistent. Avoid generic decorative badges, nested cards and repetitive filler.
4. Use aligned, purposeful grids only when they improve scanning. Do not force bento on lists, calendars or data tables.
5. Use subtle CSS motion for state transitions; respect prefers-reduced-motion. Do not introduce GSAP, React, Tailwind, remote fonts, stock images, marketing sections or randomized layouts just to satisfy upstream examples.
6. Never simulate tool execution or fabricate design measurements. Inspect actual rendered output with Playwright, review screenshots, test desktop/mobile and fix regressions before completion.
