# Dashboard performance acceptance — 0.12.2

This is the supported-host field check for the Dashboard background-load fix shipped in 0.12.2. It supplements canonical CI; it does not replace it.

- Install/update to the committed 0.12.2 wheel and verify its SHA-256 against `release/release-manifest.json`.
- Open the Dashboard overview while no Task/agent is active. Network refreshes should settle to roughly 12-second intervals rather than unconditional 2-second polling.
- Start active Task work. Dashboard refresh cadence may increase to roughly 3 seconds while work is active.
- Hide/background the Dashboard browser tab and verify periodic Dashboard API requests stop until the tab becomes visible again.
- Open a project with a large repository and leave the Dashboard visible while idle. Passive Dashboard refreshes must not invoke authoritative `task_next` repository drift/provenance scans or repository hashing; those guards remain owned by an explicit Task navigator call.
- Open a project with several Epics and confirm the Epic list remains responsive while individual Epic detail pages still show full specification/audit/plan history.
- Confirm Task status, active stage, next projected action, project state, Epic status and skill counts continue to update correctly.
- Run `ai-layer doctor --all-projects` after the check and confirm no new project-local footprint or workflow-state mutation was introduced by merely viewing the Dashboard.

A failure here is a Dashboard/read-side defect. Do not restore passive calls into the authoritative Task navigator as a workaround.
