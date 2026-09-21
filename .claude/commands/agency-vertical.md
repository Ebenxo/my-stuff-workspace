---
description: Research a trade and build, review and stage a new sample site for it (stops before Final)
argument-hint: <trade or profession, e.g. plumbing>
---
You are the director of the Form & Flow agency. Read Business-Ops/06-Agency-Operating-System.md and DESIGN_WORKFLOW.md first. The vertical to work on: $ARGUMENTS

If no vertical was given, stop and ask which one from section 8 of the operating system.

1. `industry-researcher`: write Business-Ops/research/<vertical>.md with sourced findings. Read it yourself and check that two of its key claims match their cited sources before continuing.
2. Create the project: copy Templates/new-project to Projects/portfolio-demo-<vertical> (do not overwrite anything). Write its Brief from the research.
3. `site-builder`: build in Drafts only, following its standards and the modern-web-guidance and accessibility guides.
4. `qa-reviewer`: review the Drafts build. If the verdict is fix, send the findings back to `site-builder` and re-review. At most two loops; if it still fails, stop and report why.
5. **Stop before Final.** Do not promote. Report the QA verdict, the measurements it relied on, and what it could not verify.
6. `ops-bookkeeper`: update the project HANDOFF, Business-Ops/HANDOFF.md, and commit and push the specific files.

Finish with a report of at most 12 lines, ending with `APPROVAL NEEDED:` for promotion to Final, and a note that any addition to the public portfolio site is a separate owner-approved step.

Never send, submit, sign up, spend, or publish anything.
