from odoo.tests import tagged

from .test_simulate_tournament import TestSimulateTournament


@tagged("-at_install", "post_install", "sf_production_simulation")
class TestProductionLikeTournamentSimulation(TestSimulateTournament):
    """Dedicated RC lane for the existing 12-team portal-to-final simulation."""

    pass
