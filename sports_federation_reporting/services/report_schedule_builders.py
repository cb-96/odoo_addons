from odoo.exceptions import UserError


def get_effective_season(schedule):
    """Return the explicit season or fall back to the active season snapshot."""
    return schedule.season_id or schedule.env["federation.season"].search(
        [
            ("active", "=", True),
        ],
        limit=1,
    )


def _get_season_scope(schedule):
    season = get_effective_season(schedule)
    domain = [("season_id", "=", season.id)] if season else []
    season_code = season.code if season else "all_seasons"
    return season, domain, season_code


def build_operational_rows(schedule):
    season, domain, season_code = _get_season_scope(schedule)
    rows = schedule.env["federation.report.operational"].search(
        domain, order="tournament_id asc"
    )
    headers = [
        "Season",
        "Tournament",
        "Tournament State",
        "Participants",
        "Confirmed Participants",
        "Participant Confirmation %",
        "Matches",
        "Completed Matches",
        "Match Completion %",
        "Frozen Standings",
        "Standing Coverage",
        "Pending Finance Events",
        "Pending Finance Amount",
        "Open Club Compliance Checks",
        "Readiness Status",
        "Readiness Note",
    ]
    data = [
        [
            row.season_id.name if row.season_id else "",
            row.tournament_id.name if row.tournament_id else "",
            row.tournament_state or "",
            row.participant_count,
            row.confirmed_participant_count,
            row.participant_confirmation_rate,
            row.match_count,
            row.completed_match_count,
            row.match_completion_rate,
            row.frozen_standing_count,
            row.standing_line_coverage,
            row.pending_finance_event_count,
            row.pending_finance_amount,
            row.open_club_compliance_count,
            row.readiness_status or "",
            row.readiness_note or "",
        ]
        for row in rows
    ]
    return headers, data, f"operational_{schedule.period_type}_{season_code}"


def build_standing_reconciliation_rows(schedule):
    season, domain, season_code = _get_season_scope(schedule)
    rows = schedule.env["federation.report.standing.reconciliation"].search(
        domain,
        order="tournament_id asc",
    )
    headers = [
        "Season",
        "Tournament",
        "Tournament State",
        "Confirmed Participants",
        "Covered Participants",
        "Frozen Standings",
        "Missing Participants",
        "Orphaned Participants",
        "Reconciliation Status",
        "Reconciliation Note",
    ]
    data = [
        [
            row.season_id.name if row.season_id else "",
            row.tournament_id.name if row.tournament_id else "",
            row.tournament_state or "",
            row.confirmed_participant_count,
            row.covered_participant_count,
            row.frozen_standing_count,
            row.missing_participant_count,
            row.orphaned_participant_count,
            row.reconciliation_status or "",
            row.reconciliation_note or "",
        ]
        for row in rows
    ]
    return (
        headers,
        data,
        f"standing_reconciliation_{schedule.period_type}_{season_code}",
    )


def build_finance_reconciliation_rows(schedule):
    rows = schedule.env["federation.report.finance.reconciliation"].search(
        [("needs_follow_up", "=", True)],
        order="follow_up_status asc, created_on desc",
    )
    headers = [
        "Finance Event",
        "Fee Type",
        "State",
        "Follow-up Status",
        "Counterparty",
        "Source Model",
        "Source Record ID",
        "Amount",
        "External Ref",
        "Invoice Ref",
        "Age (Days)",
        "Needs Follow-up",
    ]
    data = [
        [
            row.finance_event_id.name if row.finance_event_id else "",
            row.fee_type_id.name if row.fee_type_id else "",
            row.state or "",
            row.follow_up_status or "",
            row.counterparty_display or "",
            row.source_model or "",
            row.source_res_id,
            row.amount,
            row.external_ref or "",
            row.invoice_ref or "",
            row.age_days,
            row.needs_follow_up,
        ]
        for row in rows
    ]
    return headers, data, f"finance_reconciliation_{schedule.period_type}"


def build_workflow_exception_rows(schedule):
    season, domain, season_code = _get_season_scope(schedule)
    rows = schedule.env["federation.report.workflow.exception"].search(
        domain,
        order="age_days desc, raised_on asc",
    )
    headers = [
        "Season",
        "Tournament",
        "Reference",
        "State",
        "Exception Type",
        "Raised On",
        "Age (Days)",
        "Responsible User",
        "Note",
    ]
    selection = dict(
        schedule.env["federation.report.workflow.exception"]
        ._fields["exception_type"]
        .selection
    )
    data = [
        [
            row.season_id.name if row.season_id else "",
            row.tournament_id.name if row.tournament_id else "",
            row.reference_name or "",
            row.state or "",
            selection.get(row.exception_type, row.exception_type or ""),
            row.raised_on or "",
            row.age_days,
            row.responsible_user_id.name if row.responsible_user_id else "",
            row.exception_note or "",
        ]
        for row in rows
    ]
    return headers, data, f"workflow_exceptions_{schedule.period_type}_{season_code}"


def build_season_checklist_rows(schedule):
    season, domain, season_code = _get_season_scope(schedule)
    rows = schedule.env["federation.report.season.checklist"].search(
        domain, order="season_id asc"
    )
    headers = [
        "Season",
        "Season State",
        "Draft Season Registrations",
        "Submitted Season Registrations",
        "Draft Tournament Registrations",
        "Submitted Tournament Registrations",
        "Live Tournaments",
        "Published Tournaments",
        "Unpublished Tournaments",
        "Workflow Exceptions",
        "Checklist Status",
        "Checklist Note",
    ]
    data = [
        [
            row.season_id.name if row.season_id else "",
            row.season_state or "",
            row.draft_season_registration_count,
            row.submitted_season_registration_count,
            row.draft_tournament_registration_count,
            row.submitted_tournament_registration_count,
            row.live_tournament_count,
            row.published_tournament_count,
            row.unpublished_tournament_count,
            row.workflow_exception_count,
            row.checklist_status or "",
            row.checklist_note or "",
        ]
        for row in rows
    ]
    return headers, data, f"season_checklist_{schedule.period_type}_{season_code}"


def build_season_portfolio_rows(schedule):
    season, domain, season_code = _get_season_scope(schedule)
    rows = schedule.env["federation.report.season.portfolio"].search(
        domain, order="date_start desc, season_id asc"
    )
    headers = [
        "Season",
        "Season State",
        "Target Clubs",
        "Actual Clubs",
        "Club Delta",
        "Target Teams",
        "Actual Teams",
        "Team Delta",
        "Target Tournaments",
        "Actual Tournaments",
        "Tournament Delta",
        "Target Participants",
        "Actual Participants",
        "Participant Delta",
        "Budget",
        "Actual Finance",
        "Budget Variance",
        "Open Compliance Items",
        "Planning Status",
        "Planning Note",
    ]
    data = [
        [
            row.season_id.name if row.season_id else "",
            row.season_state or "",
            row.target_club_count,
            row.actual_club_count,
            row.club_delta,
            row.target_team_count,
            row.actual_team_count,
            row.team_delta,
            row.target_tournament_count,
            row.actual_tournament_count,
            row.tournament_delta,
            row.target_participant_count,
            row.actual_participant_count,
            row.participant_delta,
            row.budget_amount,
            row.actual_finance_amount,
            row.budget_variance_amount,
            row.open_compliance_item_count,
            row.planning_status or "",
            row.planning_note or "",
        ]
        for row in rows
    ]
    return headers, data, f"season_portfolio_{schedule.period_type}_{season_code}"


def build_club_performance_rows(schedule):
    season, domain, season_code = _get_season_scope(schedule)
    rows = schedule.env["federation.report.club.performance"].search(
        domain,
        order="season_id desc, club_id asc",
    )
    headers = [
        "Season",
        "Club",
        "Confirmed Teams",
        "Tournament Entries",
        "Confirmed Entries",
        "Completed Matches",
        "Wins",
        "Draws",
        "Losses",
        "Goals For",
        "Goals Against",
        "Goal Difference",
        "Win Rate %",
        "Pending Finance Events",
        "Open Compliance Items",
        "Performance Status",
        "Performance Note",
    ]
    data = [
        [
            row.season_id.name if row.season_id else "",
            row.club_id.name if row.club_id else "",
            row.confirmed_team_count,
            row.tournament_entry_count,
            row.confirmed_tournament_entry_count,
            row.completed_match_count,
            row.win_count,
            row.draw_count,
            row.loss_count,
            row.goals_for,
            row.goals_against,
            row.goal_difference,
            row.win_rate,
            row.pending_finance_event_count,
            row.open_compliance_item_count,
            row.performance_status or "",
            row.performance_note or "",
        ]
        for row in rows
    ]
    return headers, data, f"club_performance_{schedule.period_type}_{season_code}"


def build_compliance_summary_rows(schedule):
    rows = schedule.env["federation.report.compliance"].search(
        [], order="target_model asc"
    )
    headers = [
        "Target Model",
        "Compliant",
        "Missing",
        "Pending",
        "Expired",
        "Non Compliant",
    ]
    data = [
        [
            row.target_model or "",
            row.compliant_count,
            row.missing_count,
            row.pending_count,
            row.expired_count,
            row.non_compliant_count,
        ]
        for row in rows
    ]
    return headers, data, f"compliance_summary_{schedule.period_type}"


def build_compliance_remediation_rows(schedule):
    rows = schedule.env["federation.report.compliance.remediation"].search(
        [],
        order="sla_status desc, age_days desc, created_on asc",
    )
    headers = [
        "Submission",
        "Requirement",
        "Target Model",
        "Target",
        "Status",
        "Queue Owner",
        "Created On",
        "Reviewed On",
        "Age (Days)",
        "SLA Due On",
        "SLA Status",
        "Remediation Note",
    ]
    data = [
        [
            row.submission_id.name if row.submission_id else "",
            row.requirement_id.name if row.requirement_id else "",
            row.target_model or "",
            row.target_display or "",
            row.status or "",
            row.queue_owner_display or "",
            row.created_on or "",
            row.reviewed_on or "",
            row.age_days,
            row.sla_due_on or "",
            row.sla_status or "",
            row.remediation_note or "",
        ]
        for row in rows
    ]
    return headers, data, f"compliance_remediation_{schedule.period_type}"


def build_board_pack_rows(schedule):
    snapshot_model = schedule.env["federation.report.snapshot"]
    snapshot_model.capture_snapshot()
    snapshots = snapshot_model.search([], order="snapshot_on desc, snapshot_type asc")
    latest_by_type = {}
    for snapshot in snapshots:
        latest_by_type.setdefault(snapshot.snapshot_type, snapshot)
    ordered = [
        latest_by_type[snapshot_type]
        for snapshot_type, _label in snapshot_model._fields["snapshot_type"].selection
        if snapshot_type in latest_by_type
    ]
    headers = [
        "Snapshot Type",
        "Snapshot Date",
        "Current Value",
        "Previous Value",
        "Delta",
        "Status",
        "Summary",
    ]
    data = [
        [
            dict(snapshot_model._fields["snapshot_type"].selection).get(
                row.snapshot_type, row.snapshot_type
            ),
            row.snapshot_on,
            row.current_value,
            row.previous_value,
            row.delta_value,
            row.status or "",
            row.note or "",
        ]
        for row in ordered
    ]
    return headers, data, f"board_pack_{schedule.period_type}"


def build_audit_pack_rows(schedule):
    rows = schedule.env["federation.report.operator.checklist"].search([])
    headers = [
        "Queue",
        "Status",
        "Owner",
        "Open Items",
        "Escalated Items",
        "Oldest Age (Days)",
        "Summary",
    ]
    data = [
        [
            row.queue_name or "",
            row.status or "",
            row.owner_display or "",
            row.open_count,
            row.escalated_count,
            row.oldest_age_days,
            row.summary or "",
        ]
        for row in rows
    ]
    return headers, data, f"audit_pack_{schedule.period_type}"


REPORT_SPECS = {
    "operational": {
        "label": "Operational Summary",
        "builder": build_operational_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_operational",
        "season_scoped": True,
    },
    "standing_reconciliation": {
        "label": "Standings Reconciliation",
        "builder": build_standing_reconciliation_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_standing_reconciliation",
        "season_scoped": True,
    },
    "finance_reconciliation": {
        "label": "Finance Reconciliation",
        "builder": build_finance_reconciliation_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_finance_reconciliation",
        "action_context": {"search_default_needs_follow_up": 1},
    },
    "workflow_exceptions": {
        "label": "Workflow Exceptions",
        "builder": build_workflow_exception_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_workflow_exception",
        "season_scoped": True,
    },
    "season_checklist": {
        "label": "Season Checklist",
        "builder": build_season_checklist_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_season_checklist",
        "season_scoped": True,
    },
    "season_portfolio": {
        "label": "Season Portfolio",
        "builder": build_season_portfolio_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_season_portfolio",
        "season_scoped": True,
    },
    "club_performance": {
        "label": "Club Performance",
        "builder": build_club_performance_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_club_performance",
        "season_scoped": True,
    },
    "compliance_summary": {
        "label": "Compliance Summary",
        "builder": build_compliance_summary_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_compliance",
    },
    "compliance_remediation": {
        "label": "Compliance Remediation",
        "builder": build_compliance_remediation_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_compliance_remediation",
    },
    "board_pack": {
        "label": "Board Pack",
        "builder": build_board_pack_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_snapshot",
    },
    "audit_pack": {
        "label": "Audit Pack",
        "builder": build_audit_pack_rows,
        "action_xmlid": "sports_federation_reporting.action_federation_report_operator_checklist",
    },
}

REPORT_TYPE_SELECTION = [
    (report_type, spec["label"]) for report_type, spec in REPORT_SPECS.items()
]


def get_report_spec(report_type):
    """Return the registry entry for the requested scheduled report type."""
    spec = REPORT_SPECS.get(report_type)
    if spec is None:
        raise UserError(f"Unsupported scheduled report type: {report_type}")
    return spec


def build_report_rows(schedule):
    """Build the row payload for one scheduled report."""
    schedule.ensure_one()
    return get_report_spec(schedule.report_type)["builder"](schedule)
