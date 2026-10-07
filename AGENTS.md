# Academic Assistant agent instructions

## Existing application
- This repository is the Python application with a plain HTML/CSS/JavaScript frontend in `dashboard/`. Use `.venv/bin/python` and the existing Python requirements. `tools/frontend/` is development tooling only; this is not a Node application.
- Preserve existing user changes. Inspect `git status` before edits. Do not reset, overwrite, publish or commit unrelated work.
- Keep Moodle fetching, local extraction, calendar synchronization, authentication and saved user corrections intact. No new paid AI services or mandatory subscriptions.
- Keep credentials, `data/`, browser profiles, OAuth tokens and screenshots out of Git. Browser verification must not click update/sync/connect/disconnect or modify real calendar data unless the task calls for it.
- The normal local app is at http://127.0.0.1:8767. `dashboard/` is canonical; the installed app may serve a deployed mirror under `/Users/fbelsabah/Documents/Codex/2026-09-27/can/outputs/dashboard`. Check the served version before claiming a source edit is visible. Follow the existing launcher/deployment workflow; never copy runtime state or credentials over existing state.

## Frontend skills and precedence
Read `docs/frontend-workflow.md` for commands and source provenance.
- For frontend implementation, use `.agents/skills/gpt-tasteskill/SKILL.md` (`gpt-taste`) and `.agents/skills/clean/SKILL.md` (`clean`). Clean is the single baseline design system.
- For user-provided screenshots/mockups, use `.agents/skills/image-to-code-skill/SKILL.md` (`image-to-code`): inspect the images and adapt their layout, hierarchy, spacing and components.
- For UI review, use `.agents/skills/web-design-guidelines/SKILL.md` and review accessibility, responsive behavior, typography, hierarchy, spacing and interactions.
- For rendered browser verification, use `.agents/skills/playwright-cli/SKILL.md` and the pinned `./scripts/playwright-cli` wrapper. Upstream command examples mean this local wrapper, not a global install or unpinned npx download.
- Project constraints take precedence over upstream style defaults: keep existing green palette, typefaces, controls and plain frontend stack. No forced React, Tailwind, GSAP, huge landing-page sections, randomized layouts, stock photos or image generation. Use restrained CSS motion with reduced-motion support. Never fabricate tool output.
- Taste and image-to-code have documented local adaptations; their `references/UPSTREAM.md` files are provenance/design references, not mandatory instructions. Clean's blue/purple tokens and fonts are examples, not a migration request.

## Required frontend verification
After significant frontend changes:
1. Inspect the actual running application with Playwright. Confirm it is serving the changed version.
2. Test desktop (1440x900) and mobile (390x844), navigation, sidebar, affected controls, keyboard focus and reduced-motion behavior. Check page overflow, labels, touch targets, empty/loading/error states where relevant, browser errors and failed requests.
3. Capture and visually inspect screenshots at both sizes. Accessibility snapshots or source inspection alone are insufficient.
4. Fix visual/interaction regressions found and recheck affected layouts. Do not redesign unrelated screens during verification.
5. Report tested URLs/viewports/actions and limitations. Never claim a frontend task complete based only on source code, a passing build, or a CLI version check. If browser access is blocked, explicitly mark rendered verification incomplete; do not bypass sandbox policy.

## Skill maintenance
Do not bulk-install competing style systems. Sources and pinned revisions are in `docs/frontend-skill-sources.json`. Review changes before updating. Keep the Playwright skill matched to the installed CLI using `./scripts/playwright-cli install --skills=agents`. Retain project overrides here rather than modifying the generated Playwright skill.
