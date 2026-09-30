# Incisight UI and UX Review

Reviewed on 30 September 2026.

## Overall assessment

Incisight has a distinctive, coherent visual style. The home screen explains the product quickly, and the incident screen groups the timeline, evidence, conflicts, actions, and stakeholder update in a useful command-room layout. The simulated evidence label and the approval gate support trust.

The original experience was strongest as a guided demo. It was harder to use as an ongoing incident workspace: leaving an incident lost the path back to it, voice appeared ready when it was not configured, some failed actions gave no useful feedback, and several controls were too small to read comfortably. The changes below improve those paths. **The product still needs manual event capture and an operator authentication model before it can support real incidents without a voice service.**

## Review scope

I inspected the home screen and populated incident screen in the local browser at a desktop viewport, exercised the guided demo and refresh/navigation flow, and reviewed the React, CSS, and API code. I checked the resulting interface after the changes. This was not a user study, screen-reader audit, mobile-device test, or formal WCAG conformance assessment. Voice conversation could not be tested because this local API has no AssemblyAI key.

## What works well

| Area | Observation |
| --- | --- |
| Visual identity | The dark hero, light workspace, lime accent, and restrained icon set are consistent and memorable. |
| Information architecture | The timeline is visually primary; conflicts, actions, evidence, and updates are grouped beside it. |
| Evidence trust | Tool observations show source and confidence; simulated evidence is explicitly labeled. |
| Safety cue | Stakeholder updates start as drafts and require a separate approval action. |
| Responsive foundation | The layout collapses to one column below 900px and adjusts the form at narrower widths. |

## Findings and changes

Priority describes user impact, not engineering difficulty. “Completed” means code was changed and the listed verification was performed; it does not imply a formal accessibility certification.

| Priority | Finding and user impact | Phase and status |
| --- | --- | --- |
| High | Returning home removed the only visible path to the current incident. Refresh also returned to the landing page. This interrupted longer incident sessions. | **Phase 1 complete:** incident URLs now contain the incident ID, refresh restores the view, and the home page offers recent incidents saved on this device. |
| High | The new incident form was prefilled with demo data, making accidental duplicate “real” incidents easy. | **Phase 1 complete:** new incidents start with empty required fields and a separate “Try guided demo” action. |
| High | The microphone looked ready even when no voice key was configured. A click then failed. | **Phase 2 complete:** the API reports voice availability; the dashboard explains when voice is unavailable and disables the control. |
| High | Health-check, draft, and publish actions did not check HTTP failure responses. Users could click and see no clear result. | **Phase 2 complete:** actions now surface API errors, show progress text, and prevent repeat clicks while running. |
| High | A conflict could be detected but not reviewed from the dashboard, despite a backend review route. | **Phase 2 complete:** open conflicts now have a review note and Resolve or Dismiss actions. The note remains visible with the recorded status. |
| Medium | Publishing was one click from a draft, with the simulated destination explained mainly in the draft body. | **Phase 2 complete:** a review step names the simulated destination before the final confirmation. |
| Medium | The “IC” circle looked like a button but had no action. | **Phase 2 complete:** it is now a noninteractive role marker. |
| Medium | Panel headings, metadata, evidence text, and controls used many 9–11px labels. This made scanning difficult at normal desktop size. | **Phase 3 complete:** key labels and body text were enlarged; controls have larger targets and visible keyboard focus styles. Further zoom and mobile checks remain open. |
| Critical for real use | When voice is unavailable, a non-demo incident has no manual way to record observations, decisions, or owner assignments in the UI. | **Phase 4 planned:** add authenticated manual event capture and action assignment. |
| Critical for production | Dashboard write routes assume one trusted operator environment. Recent incidents are stored only in the current browser. | **Phase 4 planned:** define operator authentication and a server-backed incident list before multi-user deployment. |
| Medium | The incident header does not distinguish a guided demo from a real incident; only evidence records carry a simulated label. | **Phase 4 planned:** store and display an incident-level demo indicator. |

## Phased work

### Phase 1 — Keep incident work reachable

Completed: direct incident URLs, refresh restoration, recent incidents on the current device, and a clear split between creating an incident and trying the demo. Acceptance check: open the demo, refresh, return home through the logo, and reopen it from Recent incidents.

### Phase 2 — Make operational actions understandable

Completed: voice availability state, accessible microphone label, visible action errors and progress, conflict review controls, explicit publish confirmation, and removal of the inactive “IC” button. Acceptance check: an unconfigured voice service is identified before clicking; a seeded health check produces evidence and a conflict; a draft shows a separate confirmation step.

### Phase 3 — Improve readability and input access

Completed: larger key text, larger action targets, focus indicators, clearer placeholders, and tighter narrow-screen spacing. [WCAG 2.2](https://www.w3.org/TR/wcag/) calls for text contrast, visible focus, and text resizing without loss of content; its [target-size guidance](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum) sets a 24-by-24 CSS-pixel minimum or sufficient spacing for most pointer targets. The implementation moves toward these criteria, but needs a full keyboard, 200% zoom, contrast, and assistive-technology check.

### Phase 4 — Complete the incident workflow

Planned, not implemented in this pass:

1. Choose an operator authentication model for dashboard writes and incident browsing.
2. Add manual timeline entry with event type, source, confidence, and optional owner, using that authentication boundary.
3. Add a server-backed incident list for authorized operators across devices.
4. Mark demo incidents clearly at the incident level.
5. Test with incident commanders using realistic tasks: create, record, verify, resolve, draft, approve, and resume.

## Verification and remaining limits

- Backend API tests pass, including a conflict review data-contract test.
- Frontend type checking and production build pass.
- Browser review confirmed demo loading, incident URL restoration, return-home navigation, Recent incidents, voice-unavailable state, seeded evidence/conflict display, and draft confirmation display.
- The conflict review form, small-screen layout, keyboard-only flow, screen reader behavior, 200% zoom, and real voice session need dedicated end-to-end verification.
- Local “Recent incidents” begins tracking incidents opened after this update and is limited to the current browser.

**Release recommendation:** suitable for a guided local demo with the listed limitations. Treat Phase 4 and the remaining accessibility checks as release gates for a production incident-command workflow.
