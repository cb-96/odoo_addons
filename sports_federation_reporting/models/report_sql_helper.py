import logging

from odoo import api, models, tools

_logger = logging.getLogger(__name__)


class FederationReportSqlHelper(models.AbstractModel):
    _name = "federation.report.sql.helper"
    _description = "Federation Reporting SQL Helper"

    @api.model
    def recreate_view(self, table_name, sql_query):
        """Drop and recreate a SQL view with shared logging and consistent behavior."""
        tools.drop_view_if_exists(self.env.cr, table_name)
        self.env.cr.execute(sql_query)

    @api.model
    def run_query(self, sql_query, params=None):
        """Execute parameterized SQL in one place for report service consistency."""
        self.env.cr.execute(sql_query, params or [])
        return self.env.cr.fetchall()

    @api.model
    def run_explain(self, sql_query, params=None):
        """Run EXPLAIN on a report SQL query for troubleshooting and CI snapshots."""
        explain_query = f"EXPLAIN {sql_query}"
        self.env.cr.execute(explain_query, params or [])
        plan = self.env.cr.fetchall()
        _logger.debug("EXPLAIN plan captured with %s line(s)", len(plan))
        return plan
