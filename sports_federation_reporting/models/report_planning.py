from odoo import fields, models, tools


class FederationReportSeasonPortfolio(models.Model):
    _name = "federation.report.season.portfolio"
    _description = "Federation Season Portfolio Report"
    _auto = False
    _order = "date_start desc, season_id"

    STATUS_SELECTION = [
        ("healthy", "Healthy"),
        ("attention", "Attention"),
        ("blocked", "Blocked"),
    ]
    SEASON_STATE_SELECTION = [
        ("draft", "Draft"),
        ("open", "Open"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]

    season_id = fields.Many2one("federation.season", string="Season", readonly=True)
    season_state = fields.Selection(
        SEASON_STATE_SELECTION, string="Season State", readonly=True
    )
    date_start = fields.Date(string="Start Date", readonly=True)
    date_end = fields.Date(string="End Date", readonly=True)
    target_club_count = fields.Integer(string="Target Clubs", readonly=True)
    actual_club_count = fields.Integer(string="Actual Clubs", readonly=True)
    club_delta = fields.Integer(string="Club Delta", readonly=True)
    target_team_count = fields.Integer(string="Target Teams", readonly=True)
    actual_team_count = fields.Integer(string="Actual Teams", readonly=True)
    team_delta = fields.Integer(string="Team Delta", readonly=True)
    target_tournament_count = fields.Integer(string="Target Tournaments", readonly=True)
    actual_tournament_count = fields.Integer(string="Actual Tournaments", readonly=True)
    tournament_delta = fields.Integer(string="Tournament Delta", readonly=True)
    target_participant_count = fields.Integer(
        string="Target Participants", readonly=True
    )
    actual_participant_count = fields.Integer(
        string="Actual Participants", readonly=True
    )
    participant_delta = fields.Integer(string="Participant Delta", readonly=True)
    budget_amount = fields.Float(string="Budget", readonly=True)
    actual_finance_amount = fields.Float(string="Actual Finance", readonly=True)
    budget_variance_amount = fields.Float(string="Budget Variance", readonly=True)
    open_compliance_item_count = fields.Integer(
        string="Open Compliance Items", readonly=True
    )
    planning_status = fields.Selection(
        STATUS_SELECTION, string="Planning Status", readonly=True
    )
    planning_note = fields.Text(string="Planning Note", readonly=True)

    def init(self):
        """Handle init."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_season_portfolio AS (
                WITH team_stats AS (
                    SELECT
                        sr.season_id,
                        COUNT(DISTINCT sr.club_id) FILTER (WHERE sr.state = 'confirmed') AS actual_club_count,
                        COUNT(DISTINCT sr.team_id) FILTER (WHERE sr.state = 'confirmed') AS actual_team_count
                    FROM federation_season_registration sr
                    GROUP BY sr.season_id
                ),
                tournament_stats AS (
                    SELECT
                        t.season_id,
                        COUNT(*) FILTER (WHERE t.state <> 'cancelled') AS actual_tournament_count
                    FROM federation_tournament t
                    GROUP BY t.season_id
                ),
                participant_stats AS (
                    SELECT
                        t.season_id,
                        COUNT(*) FILTER (WHERE p.state = 'confirmed') AS actual_participant_count
                    FROM federation_tournament_participant p
                    JOIN federation_tournament t ON t.id = p.tournament_id
                    GROUP BY t.season_id
                ),
                budget_stats AS (
                    SELECT
                        b.season_id,
                        COALESCE(SUM(b.budget_amount), 0) AS budget_amount
                    FROM federation_season_budget b
                    GROUP BY b.season_id
                ),
                finance_stats AS (
                    SELECT
                        fe.season_id,
                        COALESCE(SUM(fe.amount) FILTER (WHERE fe.state IN ('confirmed', 'settled')), 0) AS actual_finance_amount
                    FROM federation_finance_event fe
                    WHERE fe.season_id IS NOT NULL
                    GROUP BY fe.season_id
                ),
                compliance_stats AS (
                    SELECT
                        sr.season_id,
                        COUNT(DISTINCT cc.id) AS open_compliance_item_count
                    FROM federation_season_registration sr
                    JOIN federation_compliance_check cc
                      ON cc.club_id = sr.club_id
                     AND cc.status <> 'compliant'
                    WHERE sr.state = 'confirmed'
                    GROUP BY sr.season_id
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY s.date_start DESC, s.id) AS id,
                    s.id AS season_id,
                    s.state AS season_state,
                    s.date_start,
                    s.date_end,
                    s.target_club_count,
                    COALESCE(ts.actual_club_count, 0) AS actual_club_count,
                    COALESCE(ts.actual_club_count, 0) - s.target_club_count AS club_delta,
                    s.target_team_count,
                    COALESCE(ts.actual_team_count, 0) AS actual_team_count,
                    COALESCE(ts.actual_team_count, 0) - s.target_team_count AS team_delta,
                    s.target_tournament_count,
                    COALESCE(tts.actual_tournament_count, 0) AS actual_tournament_count,
                    COALESCE(tts.actual_tournament_count, 0) - s.target_tournament_count AS tournament_delta,
                    s.target_participant_count,
                    COALESCE(ps.actual_participant_count, 0) AS actual_participant_count,
                    COALESCE(ps.actual_participant_count, 0) - s.target_participant_count AS participant_delta,
                    COALESCE(bs.budget_amount, 0) AS budget_amount,
                    COALESCE(fs.actual_finance_amount, 0) AS actual_finance_amount,
                    COALESCE(fs.actual_finance_amount, 0) - COALESCE(bs.budget_amount, 0) AS budget_variance_amount,
                    COALESCE(cs.open_compliance_item_count, 0) AS open_compliance_item_count,
                    CASE
                        WHEN COALESCE(cs.open_compliance_item_count, 0) > 0 THEN 'blocked'
                        WHEN (s.target_team_count > 0 AND COALESCE(ts.actual_team_count, 0)::numeric < (s.target_team_count::numeric * 0.75))
                          OR (s.target_participant_count > 0 AND COALESCE(ps.actual_participant_count, 0)::numeric < (s.target_participant_count::numeric * 0.75))
                        THEN 'blocked'
                        WHEN (s.target_team_count > 0 AND COALESCE(ts.actual_team_count, 0) < s.target_team_count)
                          OR (s.target_tournament_count > 0 AND COALESCE(tts.actual_tournament_count, 0) < s.target_tournament_count)
                          OR (s.target_participant_count > 0 AND COALESCE(ps.actual_participant_count, 0) < s.target_participant_count)
                          OR (COALESCE(bs.budget_amount, 0) = 0 AND COALESCE(fs.actual_finance_amount, 0) > 0)
                          OR (COALESCE(bs.budget_amount, 0) > 0 AND COALESCE(fs.actual_finance_amount, 0) > COALESCE(bs.budget_amount, 0))
                        THEN 'attention'
                        ELSE 'healthy'
                    END AS planning_status,
                    CASE
                        WHEN COALESCE(cs.open_compliance_item_count, 0) > 0 THEN 'Clubs in this season still have unresolved compliance items.'
                        WHEN s.target_participant_count > 0 AND COALESCE(ps.actual_participant_count, 0) < s.target_participant_count THEN 'Confirmed tournament participation is currently below the season target.'
                        WHEN s.target_team_count > 0 AND COALESCE(ts.actual_team_count, 0) < s.target_team_count THEN 'Confirmed team registrations are below the season target.'
                        WHEN COALESCE(bs.budget_amount, 0) = 0 AND COALESCE(fs.actual_finance_amount, 0) > 0 THEN 'Season finance activity exists without a budget baseline.'
                        WHEN COALESCE(bs.budget_amount, 0) > 0 AND COALESCE(fs.actual_finance_amount, 0) > COALESCE(bs.budget_amount, 0) THEN 'Confirmed finance activity is above the planned season budget.'
                        ELSE 'Season delivery is currently at or ahead of the recorded planning baseline.'
                    END AS planning_note
                FROM federation_season s
                LEFT JOIN team_stats ts ON ts.season_id = s.id
                LEFT JOIN tournament_stats tts ON tts.season_id = s.id
                LEFT JOIN participant_stats ps ON ps.season_id = s.id
                LEFT JOIN budget_stats bs ON bs.season_id = s.id
                LEFT JOIN finance_stats fs ON fs.season_id = s.id
                LEFT JOIN compliance_stats cs ON cs.season_id = s.id
            )
            """)


class FederationReportClubPerformance(models.Model):
    _name = "federation.report.club.performance"
    _description = "Federation Club Performance Report"
    _auto = False
    _order = "season_id desc, club_id"

    STATUS_SELECTION = FederationReportSeasonPortfolio.STATUS_SELECTION

    season_id = fields.Many2one("federation.season", string="Season", readonly=True)
    club_id = fields.Many2one("federation.club", string="Club", readonly=True)
    confirmed_team_count = fields.Integer(string="Confirmed Teams", readonly=True)
    tournament_entry_count = fields.Integer(string="Tournament Entries", readonly=True)
    confirmed_tournament_entry_count = fields.Integer(
        string="Confirmed Entries", readonly=True
    )
    completed_match_count = fields.Integer(string="Completed Matches", readonly=True)
    win_count = fields.Integer(string="Wins", readonly=True)
    draw_count = fields.Integer(string="Draws", readonly=True)
    loss_count = fields.Integer(string="Losses", readonly=True)
    goals_for = fields.Integer(string="Goals For", readonly=True)
    goals_against = fields.Integer(string="Goals Against", readonly=True)
    goal_difference = fields.Integer(string="Goal Difference", readonly=True)
    win_rate = fields.Float(string="Win Rate %", readonly=True, digits=(16, 2))
    pending_finance_event_count = fields.Integer(
        string="Pending Finance Events", readonly=True
    )
    open_compliance_item_count = fields.Integer(
        string="Open Compliance Items", readonly=True
    )
    performance_status = fields.Selection(
        STATUS_SELECTION, string="Performance Status", readonly=True
    )
    performance_note = fields.Text(string="Performance Note", readonly=True)

    def init(self):
        """Handle init."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_club_performance AS (
                WITH confirmed_teams AS (
                    SELECT
                        sr.season_id,
                        sr.club_id,
                        COUNT(DISTINCT sr.team_id) AS confirmed_team_count
                    FROM federation_season_registration sr
                    WHERE sr.state = 'confirmed'
                    GROUP BY sr.season_id, sr.club_id
                ),
                entry_stats AS (
                    SELECT
                        t.season_id,
                        tm.club_id,
                        COUNT(DISTINCT p.id) AS tournament_entry_count,
                        COUNT(DISTINCT p.id) FILTER (WHERE p.state = 'confirmed') AS confirmed_tournament_entry_count
                    FROM federation_tournament_participant p
                    JOIN federation_tournament t ON t.id = p.tournament_id
                    JOIN federation_team tm ON tm.id = p.team_id
                    GROUP BY t.season_id, tm.club_id
                ),
                match_side_rows AS (
                    SELECT
                        t.season_id,
                        ht.club_id,
                        m.state AS match_state,
                        COALESCE(m.home_score, 0) AS goals_for,
                        COALESCE(m.away_score, 0) AS goals_against
                    FROM federation_match m
                    JOIN federation_tournament t ON t.id = m.tournament_id
                    JOIN federation_team ht ON ht.id = m.home_team_id

                    UNION ALL

                    SELECT
                        t.season_id,
                        at.club_id,
                        m.state AS match_state,
                        COALESCE(m.away_score, 0) AS goals_for,
                        COALESCE(m.home_score, 0) AS goals_against
                    FROM federation_match m
                    JOIN federation_tournament t ON t.id = m.tournament_id
                    JOIN federation_team at ON at.id = m.away_team_id
                ),
                match_stats AS (
                    SELECT
                        msr.season_id,
                        msr.club_id,
                        COUNT(*) FILTER (WHERE msr.match_state = 'done') AS completed_match_count,
                        COUNT(*) FILTER (WHERE msr.match_state = 'done' AND msr.goals_for > msr.goals_against) AS win_count,
                        COUNT(*) FILTER (WHERE msr.match_state = 'done' AND msr.goals_for = msr.goals_against) AS draw_count,
                        COUNT(*) FILTER (WHERE msr.match_state = 'done' AND msr.goals_for < msr.goals_against) AS loss_count,
                        COALESCE(SUM(msr.goals_for) FILTER (WHERE msr.match_state = 'done'), 0) AS goals_for,
                        COALESCE(SUM(msr.goals_against) FILTER (WHERE msr.match_state = 'done'), 0) AS goals_against
                    FROM match_side_rows msr
                    GROUP BY msr.season_id, msr.club_id
                ),
                finance_stats AS (
                    SELECT
                        fe.season_id,
                        fe.club_id,
                        COUNT(*) FILTER (WHERE fe.state IN ('draft', 'confirmed')) AS pending_finance_event_count
                    FROM federation_finance_event fe
                    WHERE fe.season_id IS NOT NULL
                      AND fe.club_id IS NOT NULL
                    GROUP BY fe.season_id, fe.club_id
                ),
                compliance_stats AS (
                    SELECT
                        sr.season_id,
                        cc.club_id,
                        COUNT(DISTINCT cc.id) AS open_compliance_item_count
                    FROM federation_season_registration sr
                    JOIN federation_compliance_check cc
                      ON cc.club_id = sr.club_id
                     AND cc.status <> 'compliant'
                    WHERE sr.state = 'confirmed'
                    GROUP BY sr.season_id, cc.club_id
                ),
                clubs_in_scope AS (
                    SELECT season_id, club_id FROM confirmed_teams
                    UNION
                    SELECT season_id, club_id FROM entry_stats
                    UNION
                    SELECT season_id, club_id FROM match_stats
                    UNION
                    SELECT season_id, club_id FROM finance_stats
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY s.date_start DESC, c.name, c.id) AS id,
                    scope.season_id,
                    scope.club_id,
                    COALESCE(ct.confirmed_team_count, 0) AS confirmed_team_count,
                    COALESCE(es.tournament_entry_count, 0) AS tournament_entry_count,
                    COALESCE(es.confirmed_tournament_entry_count, 0) AS confirmed_tournament_entry_count,
                    COALESCE(ms.completed_match_count, 0) AS completed_match_count,
                    COALESCE(ms.win_count, 0) AS win_count,
                    COALESCE(ms.draw_count, 0) AS draw_count,
                    COALESCE(ms.loss_count, 0) AS loss_count,
                    COALESCE(ms.goals_for, 0) AS goals_for,
                    COALESCE(ms.goals_against, 0) AS goals_against,
                    COALESCE(ms.goals_for, 0) - COALESCE(ms.goals_against, 0) AS goal_difference,
                    ROUND(
                        CASE
                            WHEN COALESCE(ms.completed_match_count, 0) = 0 THEN 0
                            ELSE (COALESCE(ms.win_count, 0)::numeric / ms.completed_match_count::numeric) * 100
                        END,
                        2
                    ) AS win_rate,
                    COALESCE(fs.pending_finance_event_count, 0) AS pending_finance_event_count,
                    COALESCE(cs.open_compliance_item_count, 0) AS open_compliance_item_count,
                    CASE
                        WHEN COALESCE(cs.open_compliance_item_count, 0) > 0 THEN 'blocked'
                        WHEN COALESCE(fs.pending_finance_event_count, 0) > 0
                          OR (COALESCE(ct.confirmed_team_count, 0) > 0 AND COALESCE(es.confirmed_tournament_entry_count, 0) = 0)
                        THEN 'attention'
                        ELSE 'healthy'
                    END AS performance_status,
                    CASE
                        WHEN COALESCE(cs.open_compliance_item_count, 0) > 0 THEN 'Club compliance issues still need remediation before the season can be considered clean.'
                        WHEN COALESCE(fs.pending_finance_event_count, 0) > 0 THEN 'The club still has open finance events for this season.'
                        WHEN COALESCE(ct.confirmed_team_count, 0) > 0 AND COALESCE(es.confirmed_tournament_entry_count, 0) = 0 THEN 'Confirmed season teams have not yet converted into tournament participation.'
                        ELSE 'Club activity, compliance, and finance queues are currently aligned.'
                    END AS performance_note
                FROM clubs_in_scope scope
                JOIN federation_season s ON s.id = scope.season_id
                JOIN federation_club c ON c.id = scope.club_id
                LEFT JOIN confirmed_teams ct ON ct.season_id = scope.season_id AND ct.club_id = scope.club_id
                LEFT JOIN entry_stats es ON es.season_id = scope.season_id AND es.club_id = scope.club_id
                LEFT JOIN match_stats ms ON ms.season_id = scope.season_id AND ms.club_id = scope.club_id
                LEFT JOIN finance_stats fs ON fs.season_id = scope.season_id AND fs.club_id = scope.club_id
                LEFT JOIN compliance_stats cs ON cs.season_id = scope.season_id AND cs.club_id = scope.club_id
            )
            """)
