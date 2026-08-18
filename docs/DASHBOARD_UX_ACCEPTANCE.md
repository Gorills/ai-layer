# Dashboard UX acceptance

The Dashboard is a local operational workspace, not a catalog of AI Layer entities. Its primary user question is **“what is happening in this project, what happened recently, what changed, and what needs my attention?”**

## Audit findings

The previous information architecture was entity-first: Work, Managed Tasks, Epics, Skills, Knowledge, Rules, Monitoring and Activity were separate destinations. The project selector acted only as a route filter. A user could open a project, follow a sidebar link, lose the project scope and have to select it again. The project page itself mostly exposed workflow/runtime diagnostics and links to other screens, so reconstructing project history required manual navigation and mental joins.

The global overview mixed runtime diagnostics, project state, transport activity and three parallel Work panels at similar visual priority. It was attractive but expensive to scan for the two operational questions that matter first: **what needs attention** and **what is happening now**.

## Information architecture

- **Overview** is a portfolio: attention first, live work second, recent outcomes third, then project entry points. System health is compact and secondary.
- **Project** is the durable workspace context. Selecting/opening a project keeps that project selected across Work, Tasks, Epics, Knowledge, Skills, Rules, Activity and Monitoring.
- **Project summary** answers in one view:
  - what is happening now;
  - what requires attention;
  - what was completed recently;
  - what files/checks/execution evidence were involved;
  - what AI Layer already knows about the project.
- **Project Work hub** presents ordinary Work, Managed Tasks and Epics together while keeping their durable models distinct.
- **Project Knowledge hub** presents Project Knowledge, Project Map, project rules and available skills together.
- Full entity lists and deep links remain available for inspection and compatibility; they are no longer required to understand normal project state.

## Interaction acceptance

1. Open a project from Overview. The project identity and project-local navigation remain visible while moving through normal project screens.
2. From that project, open Work, Managed Tasks, Epics, Knowledge, Skills, Rules, Activity and Monitoring. The project selector must stay on the same project and sidebar links must carry that scope.
3. Switching the project selector while on a scoped page must keep the current section when possible instead of returning to an unrelated global screen.
4. Opening Project Knowledge without a selected project must ask the user to choose a project. It must never silently pick the first registered project.
5. The project summary must show current Work, actionable attention, recent terminal Work outcomes and concise execution evidence without requiring navigation to another screen.
6. Overview must make attention and live work visually prior to runtime diagnostics. Each project card must be a direct entry to its project workspace.
7. Dashboard reads must remain read-only: no Task navigator calls, project mutation, repository hashing, or repository-local AI Layer footprint may be introduced by viewing these screens.

## Performance acceptance

The existing `DASHBOARD_PERFORMANCE_ACCEPTANCE.md` remains authoritative. Project Work and Knowledge hubs may compose existing bounded local read APIs in parallel; they must not introduce unbounded histories or passive authoritative workflow scans.
