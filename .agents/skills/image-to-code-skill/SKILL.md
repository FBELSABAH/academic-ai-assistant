---
name: image-to-code
description: Use when the user supplies screenshots, mockups or visual references to adapt their layout, hierarchy, typography, spacing and components to this existing app.
---

Read AGENTS.md and docs/frontend-workflow.md first. This project adaptation comes from Leonxlnx/taste-skill; unchanged upstream text is in references/UPSTREAM.md. Its mandatory image-generation workflow does not apply here.

1. Open every supplied reference and inspect the actual image; do not infer unseen portions.
2. Extract hierarchy, alignment, proportions, spacing rhythm, typography scale, palette, borders/radii, component states and motion intent. Distinguish observations from estimates.
3. Identify the principles the user wants and map them to existing plain HTML/CSS/JavaScript components. Preserve app functions and established design tokens unless the request changes them.
4. Consider desktop and mobile behavior; one screenshot is not evidence of every breakpoint. Ask only when consequential behavior cannot be inferred.
5. Implement semantic, accessible components, not a screenshot sliced into images. Use real app content, not invented data.
6. Compare rendered screenshots with the reference, check interactions, keyboard focus and overflow, and iterate on meaningful differences.
No generated images, external uploads or paid services are required. Generate assets only when explicitly requested; supplied screenshots are the primary reference.
