# Module Scaffold Guide

Last updated: 2026-05-18
Owner: Federation Platform Team

This guide walks through the complete set of files required when adding a new
custom module to this repository. Follow it every time you scaffold a new addon.

---

## 1. Canonical Directory Layout

```
sports_federation_<name>/
├── __init__.py
├── __manifest__.py
├── README.md
├── models/
│   ├── __init__.py
│   └── federation_<entity>.py
├── security/
│   ├── res_groups.xml          # only if the module defines new groups
│   └── ir.model.access.csv
├── data/
│   └── ir_sequence.xml         # only if the module uses sequences
├── views/
│   ├── federation_<entity>_views.xml
│   └── menu_items.xml
├── wizards/                    # only if the module has transient models
│   ├── __init__.py
│   ├── my_wizard.py
│   └── my_wizard_views.xml
├── controllers/                # only if the module has HTTP routes
│   ├── __init__.py
│   └── my_controller.py
└── tests/
    ├── __init__.py
    └── test_<entity>.py
```

Only create directories that contain files. An empty `wizards/` directory is
a maintenance burden — delete it if you have no transient models.

---

## 2. Worked Example: `sports_federation_awards`

This fictional module tracks federation awards given to players at the end of
a season. It is a minimal but complete example.

### `__init__.py`

```python
from . import models
```

### `__manifest__.py`

```python
{
    "name": "Sports Federation Awards",
    "version": "19.0.1.0.0",
    "category": "Sports",
    "summary": "Season-end awards for players and teams",
    "author": "Sports Federation",
    "license": "LGPL-3",
    "depends": [
        "sports_federation_base",
        "sports_federation_people",
        "sports_federation_tournament",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/federation_award_views.xml",
        "views/menu_items.xml",
    ],
    "demo": [],
    "installable": True,
    "application": False,
    "auto_install": False,
}
```

**Key manifest rules:**
- `version` must follow `19.0.<major>.<minor>.<patch>` (Odoo major version prefix).
- `depends` lists only direct dependencies. Odoo resolves transitive deps.
- Every XML and CSV file that must be loaded appears in `data`. Order matters:
  `security/` before `views/`.
- `application: False` for domain modules that extend the base application.
  Only `sports_federation_base` sets `application: True`.

### `models/__init__.py`

```python
from . import federation_award
```

### `models/federation_award.py`

```python
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationAward(models.Model):
    _name = "federation.award"
    _description = "Federation Award"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "season_id desc, award_type, id"

    name = fields.Char(string="Award Name", required=True)
    season_id = fields.Many2one(
        "federation.season",
        string="Season",
        required=True,
        ondelete="restrict",
        index=True,
    )
    award_type = fields.Selection(
        [
            ("best_player", "Best Player"),
            ("top_scorer", "Top Scorer"),
            ("best_team", "Best Team"),
        ],
        string="Award Type",
        required=True,
    )
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        ondelete="restrict",
    )
    notes = fields.Text(string="Notes")

    _award_season_type_unique = models.Constraint(
        "unique(season_id, award_type)",
        "Only one award of each type may be given per season.",
    )

    @api.constrains("award_type", "player_id")
    def _check_player_required_for_individual_awards(self):
        individual_types = {"best_player", "top_scorer"}
        for rec in self:
            if rec.award_type in individual_types and not rec.player_id:
                raise ValidationError(
                    _("A player must be set for individual award type '%s'.")
                    % rec.award_type
                )
```

**Model conventions:**
- `_name` uses the `federation.` prefix.
- `_order` is always set explicitly.
- Constraints use the `models.Constraint` class (Odoo 19 style), not
  `_sql_constraints`.
- `@api.constrains` for Python-level validation.
- Use `ondelete="restrict"` for Many2one fields pointing to master data to
  prevent silent orphans.

### `security/ir.model.access.csv`

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_federation_award_user,federation.award.user,model_federation_award,sports_federation_base.group_federation_user,1,0,0,0
access_federation_award_manager,federation.award.manager,model_federation_award,sports_federation_base.group_federation_manager,1,1,1,1
```

**ACL rules:**
- Every model needs at least one ACL row. A missing row causes `AccessError`
  for non-superuser operations (including CI test setup).
- Use the group references from `sports_federation_base`: `group_federation_user`
  (read-only federation staff) and `group_federation_manager` (full control).
- The `id` column is the XML ID: `access_<model_snake_case>_<group_suffix>`.
- The `model_id:id` column is `model_` + model name with dots replaced by
  underscores: `federation.award` → `model_federation_award`.

### `views/federation_award_views.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="federation_award_view_list" model="ir.ui.view">
        <field name="name">federation.award.view.list</field>
        <field name="model">federation.award</field>
        <field name="arch" type="xml">
            <list string="Awards">
                <field name="name"/>
                <field name="season_id"/>
                <field name="award_type"/>
                <field name="player_id"/>
            </list>
        </field>
    </record>

    <record id="federation_award_view_form" model="ir.ui.view">
        <field name="name">federation.award.view.form</field>
        <field name="model">federation.award</field>
        <field name="arch" type="xml">
            <form string="Award">
                <sheet>
                    <group>
                        <field name="name"/>
                        <field name="season_id"/>
                        <field name="award_type"/>
                        <field name="player_id"
                               attrs="{'invisible': [('award_type', '=', 'best_team')]}"/>
                    </group>
                    <notebook>
                        <page string="Notes">
                            <field name="notes"/>
                        </page>
                    </notebook>
                </sheet>
                <div class="oe_chatter">
                    <field name="message_follower_ids"/>
                    <field name="activity_ids"/>
                    <field name="message_ids"/>
                </div>
            </form>
        </field>
    </record>

    <record id="federation_award_action" model="ir.actions.act_window">
        <field name="name">Awards</field>
        <field name="res_model">federation.award</field>
        <field name="view_mode">list,form</field>
    </record>

</odoo>
```

### `views/menu_items.xml`

Attach the new menu under the existing Sports Federation top-level menu:

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <menuitem
        id="menu_federation_awards"
        name="Awards"
        parent="sports_federation_base.menu_federation_main"
        action="federation_award_action"
        sequence="90"
        groups="sports_federation_base.group_federation_user"/>

</odoo>
```

### `README.md`

Every module must have a README. Minimum content:

```markdown
# Sports Federation Awards

Season-end awards for players and teams.

## Purpose

Tracks which player or team received each award type at the end of a season.
Prevents duplicate awards of the same type per season via a DB constraint.

## Dependencies

- `sports_federation_base` — clubs, teams, seasons, groups
- `sports_federation_people` — `federation.player`
- `sports_federation_tournament` — season context

## Models

### `federation.award`

| Field | Type | Description |
|---|---|---|
| `name` | Char | Award label |
| `season_id` | Many2one(`federation.season`) | Season the award belongs to |
| `award_type` | Selection | `best_player`, `top_scorer`, `best_team` |
| `player_id` | Many2one(`federation.player`) | Required for individual award types |
| `notes` | Text | Optional notes |

**Constraints:** One award of each type per season (`unique(season_id, award_type)`).
```

### `tests/__init__.py`

```python
from . import test_award
```

### `tests/test_award.py`

```python
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestFederationAward(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create({
            "name": "Awards Season",
            "code": "AWS26",
            "date_start": "2026-01-01",
            "date_end": "2026-12-31",
        })
        cls.club = cls.env["federation.club"].create({
            "name": "Award Club", "code": "AWC",
        })
        cls.player = cls.env["federation.player"].create({
            "first_name": "Award", "last_name": "Winner", "club_id": cls.club.id,
        })

    def test_create_best_player_award(self):
        award = self.env["federation.award"].create({
            "name": "Best Player 2026",
            "season_id": self.season.id,
            "award_type": "best_player",
            "player_id": self.player.id,
        })
        self.assertTrue(award.id)
        self.assertEqual(award.award_type, "best_player")

    def test_individual_award_requires_player(self):
        with self.assertRaises(ValidationError):
            self.env["federation.award"].create({
                "name": "Top Scorer 2026",
                "season_id": self.season.id,
                "award_type": "top_scorer",
                # player_id intentionally omitted
            })

    def test_duplicate_award_type_per_season_is_blocked(self):
        self.env["federation.award"].create({
            "name": "Best Player 2026",
            "season_id": self.season.id,
            "award_type": "best_player",
            "player_id": self.player.id,
        })
        with self.assertRaises(Exception):
            self.env["federation.award"].create({
                "name": "Best Player 2026 Dup",
                "season_id": self.season.id,
                "award_type": "best_player",
                "player_id": self.player.id,
            })
            self.env.cr.flush()
```

---

## 3. Checklist

Use this checklist before opening a PR for a new module:

- [ ] `__manifest__.py` — `version`, `depends`, `data` list, `license`
- [ ] `models/__init__.py` — all model files imported
- [ ] `security/ir.model.access.csv` — one row per model per group
- [ ] All XML/CSV files registered in `__manifest__.py` `data`
- [ ] `README.md` — purpose, dependencies, model table
- [ ] `tests/__init__.py` — test file imported
- [ ] At least one test: happy path + one constraint/validation failure case
- [ ] `MODULE_OWNERS.yaml` — new module added with owner
- [ ] `CONTEXT.md` — module listed in the module inventory section
- [ ] `_workflows/*.md` — updated if module introduces a new workflow step

---

## 4. Using the `module-change-scaffold` Copilot Skill

For iterative changes to existing modules, use the `module-change-scaffold`
skill in GitHub Copilot. It returns a patch covering all required wiring
(model file, `__init__.py`, ACL row, views, manifest, test) in a single pass.

Prompt example:

> Add a new persistent model `federation.award` with fields `name`, `season_id`,
> `award_type`, `player_id`, `notes`; add ACLs, a basic list/form view, and unit
> tests. Show me the patch with files changed.

The skill references this guide and `copilot-instructions.md` to ensure all
wiring is included.
