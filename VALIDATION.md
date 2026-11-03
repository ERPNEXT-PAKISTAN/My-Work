# Validation and operational notes

My Work has isolated Python service tests and JavaScript DOM, route, and native workflow-builder checks. Tests use synthetic data and mocked persistence boundaries; they do not submit financial transactions or send comments to a production site.

## Run the checks

From an installed Frappe v16 bench:

```bash
./env/bin/python -m unittest discover \
  -s apps/my_work/my_work/tests -p 'test_*.py' -q
npm --prefix apps/my_work/tests ci
npm --prefix apps/my_work/tests test
node --check apps/my_work/my_work/my_work/page/my_work/my_work.js
bench build --app my_work
```

The workflow-builder fixture lives in `tests/fixtures/workflow-layout.json`; it represents the optional example definition, not an installed site's business workflow. JavaScript dependencies are development-only and are installed inside `tests/`.

## Coverage

| Area | Examples checked |
|---|---|
| Access | Desk/Guest boundaries, parent read checks, other-assignee denial, field and child-table visibility. |
| Mutations | Stale versions, native submit/cancel dispatch, workflow precedence, native validation failures, escaped audit content. |
| Loading | Global record cap, per-type candidate bounds, early module/type/status constraints, explicit dates, scope labels. |
| Business details | Six-field order summaries, compact item columns, readable monetary totals/currencies/accounts. |
| Expense Claims | Separate approval/accounting decisions, payment/advance status, draft edits, native link validation. |
| Collaboration | Native assignments/sharing/tags/attachments, independent comments in every saved document status. |
| Audit | Recorded Version docstatus transitions and existing My Work action comments; no creator/last-editor substitution. |
| UI | Main-list status focus, non-duplicated Draft action, full-width remarks below tables, Review timeline, comment draft retention. |

## Optional installed-site read checks

Run these only in an environment where you are authorized to inspect the documents:

```bash
bench --site your-site.example execute my_work.validation.smoke
bench --site your-site.example execute my_work.validation.page_assets
bench --site your-site.example execute my_work.validation.loading_performance
```

These helpers inspect readable existing records. The local CLI's effective user determines the scope; `loading_performance` optionally accepts an explicitly supplied Desk User. They do not create demo transactions or post test comments. `audit_users` is an administrative read-only audit across enabled Desk users and should be used deliberately.

## Known limits

- Counters, search, and sorting apply to the loaded recent-work window, not the entire database. Default: latest 100 candidates updated within 30 days; maximum 500 full documents evaluated per request.
- Candidate queries are bounded per type, then merged into the global window. This does not guarantee a fixed number of database reads or constant latency on every permission query, custom hook, or large document.
- Selecting All dates still applies the record cap. Use type/module filters or an older updated-date interval to reach records outside the window.
- Native personal discovery includes owned records and supported employee/approver relationships, not every record an administrator can read.
- Submission attribution requires a recorded Version transition, native timeline event, or existing My Work native-action audit entry. Missing historical events are not invented. Version/action lookup is bounded in Review.
- App-specific child sections may be deliberately excluded from Review; the full native document remains available.
- DOM checks are not a substitute for browser accessibility, responsive-layout, or concurrency testing.

## Before a broad production rollout

Validate actual submit/cancel, amendment, permissions, user/company restrictions, custom workflows, financial/stock hooks, and concurrent use on staging. Keep the site's existing backup and recovery process. Performance measurements on one dataset are observations, not a guarantee for every deployment.
