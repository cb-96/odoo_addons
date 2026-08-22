# Sports Federation Scheduling

The scheduling addon owns working schedules, fixture assignments, schedule
changes, and the weighted fairness auto-schedule preview.

The auto-schedule wizard previews deterministic assignments after applying hard
constraints and weighted fairness penalties. Applying a proposal records the
automatic assignments and schedule changes while checking the schedule revision
for concurrent edits.

All access-control rows, including the auto-schedule wizard permissions, are
loaded through `security/ir.model.access.csv`.