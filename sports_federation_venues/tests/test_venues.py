from odoo.tests.common import TransactionCase


class TestVenues(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.venue = cls.env["federation.venue"].create(
            {
                "name": "Test Stadium",
                "city": "Test City",
            }
        )
        cls.playing_area = cls.env["federation.playing.area"].create(
            {
                "name": "Main Field",
                "venue_id": cls.venue.id,
                "code": "MF-01",
                "surface_type": "outdoor",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "code": "TTOUR",
                "season_id": cls.env["federation.season"]
                .create(
                    {
                        "name": "Test Season",
                        "code": "TVTS",
                        "date_start": "2024-01-01",
                        "date_end": "2024-12-31",
                    }
                )
                .id,
                "date_start": "2024-06-01",
            }
        )

    def test_create_venue(self):
        """Test venue creation with basic fields."""
        venue = self.env["federation.venue"].create(
            {
                "name": "New Stadium",
                "city": "New City",
                "capacity": 50000,
            }
        )
        self.assertEqual(venue.name, "New Stadium")
        self.assertEqual(venue.city, "New City")
        self.assertEqual(venue.capacity, 50000)
        self.assertTrue(venue.active)

    def test_create_playing_area(self):
        """Test playing area creation and venue relationship."""
        self.assertEqual(self.playing_area.name, "Main Field")
        self.assertEqual(self.playing_area.venue_id, self.venue)
        self.assertEqual(self.playing_area.code, "MF-01")
        self.assertEqual(self.playing_area.surface_type, "outdoor")

    def test_match_playing_area_belongs_to_venue(self):
        """Test that playing area must belong to the selected venue."""
        other_venue = self.env["federation.venue"].create(
            {
                "name": "Other Stadium",
                "city": "Other City",
            }
        )
        other_area = self.env["federation.playing.area"].create(
            {
                "name": "Other Field",
                "venue_id": other_venue.id,
            }
        )
        with self.assertRaises(Exception):
            self.env["federation.match"].create(
                {
                    "tournament_id": self.tournament.id,
                    "venue_id": self.venue.id,
                    "playing_area_id": other_area.id,
                }
            )

    def test_tournament_venue_link(self):
        """Test venue linkage on tournament."""
        self.tournament.venue_id = self.venue.id
        self.assertEqual(self.tournament.venue_id, self.venue)

    def test_unique_playing_area_name_per_venue(self):
        """Test that playing area name is unique per venue."""
        with self.assertRaises(Exception):
            self.env["federation.playing.area"].create(
                {
                    "name": "Main Field",
                    "venue_id": self.venue.id,
                }
            )
