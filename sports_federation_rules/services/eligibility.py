"""
Eligibility Service — central service for player/roster/match eligibility.

Answers queries like:
  - Is this player eligible to compete in this tournament/competition?
  - Which players on this roster are ineligible, and why?
  - Is this match roster compliant with the rule set?

The service evaluates ``federation.eligibility.rule`` records from the
effective rule set and returns structured results so callers can decide
whether to block, warn, or log without coupling business logic to the rules.

Usage::

    service = self.env["federation.eligibility.service"]
    result = service.check_player_eligibility(player, rule_set, context={})
    if not result["eligible"]:
        raise ValidationError("\\n".join(result["reasons"]))
"""

from datetime import date

from odoo import api, fields, models


class EligibilityResult:
    """Lightweight data class for an eligibility check outcome."""

    def __init__(self, eligible=True, reasons=None):
        """Handle init."""
        self.eligible = eligible
        self.reasons = reasons or []

    def merge(self, other):
        """Merge another result into this one."""
        if not other.eligible:
            self.eligible = False
        self.reasons.extend(other.reasons)
        return self

    def to_dict(self):
        """Convert the value to dict."""
        return {"eligible": self.eligible, "reasons": self.reasons}


class FederationEligibilityService(models.AbstractModel):
    """Central eligibility evaluation service.

    All public methods return a dict:
    ``{"eligible": bool, "reasons": list[str]}``

    *Reasons* are human-readable messages explaining why a check failed.
    An empty reasons list with ``eligible=True`` means all checks passed.
    """

    _name = "federation.eligibility.service"
    _description = "Federation Eligibility Service"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def check_player_eligibility(self, player, rule_set, context=None):
        """Check a single player against all active, non-placeholder rules.

        Args:
            player: ``federation.player`` record.
            rule_set: ``federation.rule.set`` record.
            context: Optional dict with extra context keys:
                - ``tournament_id``: int — to check registration rule
                - ``competition_id``: int — to check registration rule
                - ``season_id``: int — to resolve season-scoped license or registration rules
                - ``club_id``: int — to resolve club-scoped license rules
                - ``team_id``: int — to resolve registration rules
                - ``license_id``: int — selected license to validate explicitly
                - ``match_date``: date — overrides today for age calculation

        Returns:
            dict with keys ``eligible`` (bool) and ``reasons`` (list of str).
        """
        if context is None:
            context = {}

        result = EligibilityResult()

        if not rule_set:
            return result.to_dict()

        rules = self.env["federation.eligibility.rule"].search(
            [
                ("rule_set_id", "=", rule_set.id),
                ("active", "=", True),
                ("is_placeholder", "=", False),
            ],
            order="sequence",
        )

        for rule in rules:
            check = self._evaluate_rule(rule, player, context)
            result.merge(check)

        return result.to_dict()

    @api.model
    def check_roster_eligibility(self, roster, rule_set=None):
        """Check all players on a roster for eligibility.

        Args:
            roster: ``federation.team.roster`` record.
            rule_set: Optional ``federation.rule.set`` override.
                      Falls back to ``roster.rule_set_id``.

        Returns:
            dict of ``{player_id: {"eligible": bool, "reasons": list}}``.
        """
        effective_rule_set = rule_set or roster.rule_set_id
        results = {}
        reference_date_getter = getattr(roster, "_get_reference_date", None)
        reference_date = (
            reference_date_getter() if callable(reference_date_getter) else date.today()
        )
        for line in roster.line_ids:
            player = getattr(line, "player_id", None)
            if not player:
                continue
            context = {
                "match_date": reference_date,
            }
            if roster.season_id:
                context["season_id"] = roster.season_id.id
            if roster.club_id:
                context["club_id"] = roster.club_id.id
            if roster.team_id:
                context["team_id"] = roster.team_id.id
            if roster.competition_id:
                context["competition_id"] = roster.competition_id.id
            if getattr(line, "license_id", False):
                context["license_id"] = line.license_id.id
            results[player.id] = self.check_player_eligibility(
                player, effective_rule_set, context
            )
        return results

    @api.model
    def check_match_eligibility(self, match, team, players):
        """Check whether a set of players can play for a team in a match.

        Derives the rule set from the match → stage → tournament → competition chain.

        Args:
            match: ``federation.match`` record.
            team: ``federation.team`` record.
            players: recordset of ``federation.player`` records.

        Returns:
            dict of ``{player_id: {"eligible": bool, "reasons": list}}``.
        """
        rule_set = self._resolve_rule_set(match)
        context = {
            "tournament_id": match.tournament_id.id if match.tournament_id else None,
            "match_date": (
                match.date_scheduled.date() if match.date_scheduled else date.today()
            ),
        }
        if match.tournament_id and match.tournament_id.season_id:
            context["season_id"] = match.tournament_id.season_id.id
        if team:
            context["team_id"] = team.id
            if team.club_id:
                context["club_id"] = team.club_id.id
        results = {}
        for player in players:
            results[player.id] = self.check_player_eligibility(
                player, rule_set, context
            )
        return results

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def _evaluate_rule(self, rule, player, context):
        """Dispatch to the correct evaluation method for a rule type.

        Unknown rule types return eligible=True (fail-open default).
        """
        etype = rule.eligibility_type
        if etype == "age_min":
            return self._check_age_min(rule, player, context)
        if etype == "age_max":
            return self._check_age_max(rule, player, context)
        if etype == "gender":
            return self._check_gender(rule, player)
        if etype == "license_valid":
            return self._check_license(player, context)
        if etype == "suspension":
            return self._check_suspension(player, context)
        if etype == "registration":
            return self._check_registration(player, context)
        # "custom" and unknown → pass-through (no enforcement yet)
        return EligibilityResult(eligible=True)

    # ------------------------------------------------------------------
    # Individual rule checks
    # ------------------------------------------------------------------

    def _player_age(self, player, reference_date=None):
        """Compute player age in full years at the reference_date."""
        if not player.birth_date:
            return None
        ref = reference_date or date.today()
        born = player.birth_date
        return ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))

    def _check_age_min(self, rule, player, context):
        """Validate age min."""
        ref = context.get("match_date") or date.today()
        age = self._player_age(player, ref)
        if age is None:
            return EligibilityResult(
                eligible=False,
                reasons=[f"Rule '{rule.name}': player has no birth date set."],
            )
        if age < rule.age_limit:
            return EligibilityResult(
                eligible=False,
                reasons=[
                    f"Rule '{rule.name}': player age {age} is below minimum {rule.age_limit}."
                ],
            )
        return EligibilityResult()

    def _check_age_max(self, rule, player, context):
        """Validate age max."""
        ref = context.get("match_date") or date.today()
        age = self._player_age(player, ref)
        if age is None:
            return EligibilityResult(
                eligible=False,
                reasons=[f"Rule '{rule.name}': player has no birth date set."],
            )
        if age > rule.age_limit:
            return EligibilityResult(
                eligible=False,
                reasons=[
                    f"Rule '{rule.name}': player age {age} exceeds maximum {rule.age_limit}."
                ],
            )
        return EligibilityResult()

    def _check_gender(self, rule, player):
        """Validate gender."""
        if not rule.allowed_categories:
            return EligibilityResult()
        allowed = [c.strip().lower() for c in rule.allowed_categories.split(",")]
        player_gender = (player.gender or "").lower()
        if player_gender not in allowed:
            return EligibilityResult(
                eligible=False,
                reasons=[
                    f"Rule '{rule.name}': player gender '{player_gender}' not in "
                    f"allowed list [{', '.join(allowed)}]."
                ],
            )
        return EligibilityResult()

    def _check_license(self, player, context=None):
        """Check that the player has at least one active license.

        The ``federation.player.license`` model is in ``sports_federation_people``.
        If the model is absent (module not installed), this check is skipped.
        """
        context = context or {}
        License = self.env.get("federation.player.license")
        if License is None:
            return EligibilityResult()

        reference_date = context.get("match_date") or date.today()
        if isinstance(reference_date, str):
            reference_date = fields.Date.to_date(reference_date)

        season_id = context.get("season_id")
        club_id = context.get("club_id")
        selected_license_id = context.get("license_id")

        if selected_license_id:
            selected_license = License.browse(selected_license_id)
            reasons = []
            if not selected_license.exists() or selected_license.player_id != player:
                reasons.append(
                    f"Player '{player.name}' does not have the selected license."
                )
            else:
                if selected_license.state != "active":
                    reasons.append(
                        f"Selected license '{selected_license.name}' is not active."
                    )
                if (
                    selected_license.issue_date
                    and selected_license.issue_date > reference_date
                ):
                    reasons.append(
                        f"Selected license '{selected_license.name}' is not valid yet for {reference_date}."
                    )
                if (
                    selected_license.expiry_date
                    and selected_license.expiry_date < reference_date
                ):
                    reasons.append(
                        f"Selected license '{selected_license.name}' expired before {reference_date}."
                    )
                if season_id and selected_license.season_id.id != season_id:
                    reasons.append(
                        f"Selected license '{selected_license.name}' does not cover the required season."
                    )
                if club_id and selected_license.club_id.id != club_id:
                    reasons.append(
                        f"Selected license '{selected_license.name}' does not belong to the required club."
                    )
            if reasons:
                return EligibilityResult(eligible=False, reasons=reasons)
            return EligibilityResult()

        domain = [
            ("player_id", "=", player.id),
            ("state", "=", "active"),
            ("issue_date", "<=", reference_date),
            "|",
            ("expiry_date", "=", False),
            ("expiry_date", ">=", reference_date),
        ]
        if season_id:
            domain.append(("season_id", "=", season_id))
        if club_id:
            domain.append(("club_id", "=", club_id))

        active_license = License.search(domain, limit=1)
        if not active_license:
            scope_bits = []
            if season_id:
                season = self.env["federation.season"].browse(season_id)
                if season.exists():
                    scope_bits.append(f"season '{season.name}'")
            if club_id:
                club = self.env["federation.club"].browse(club_id)
                if club.exists():
                    scope_bits.append(f"club '{club.name}'")
            scope = " for " + " and ".join(scope_bits) if scope_bits else ""
            return EligibilityResult(
                eligible=False,
                reasons=[
                    f"Player '{player.name}' has no active license{scope} on {reference_date}."
                ],
            )
        return EligibilityResult()

    def _check_suspension(self, player, context=None):
        """Check that the player is not suspended for the operational date."""
        context = context or {}
        reference_date = fields.Date.to_date(context.get("match_date") or date.today())
        Suspension = self.env.get("federation.suspension")

        if Suspension is not None:
            active_suspension = Suspension.search(
                [
                    ("player_id", "=", player.id),
                    ("state", "=", "active"),
                    ("date_start", "<=", reference_date),
                    ("date_end", ">=", reference_date),
                ],
                order="date_start desc, id desc",
                limit=1,
            )
            if active_suspension:
                return EligibilityResult(
                    eligible=False,
                    reasons=[
                        (
                            f"Player '{player.name}' is suspended from "
                            f"{active_suspension.date_start} to {active_suspension.date_end}."
                        )
                    ],
                )

        if player.state == "suspended":
            return EligibilityResult(
                eligible=False,
                reasons=[f"Player '{player.name}' is currently suspended."],
            )
        return EligibilityResult()

    def _check_registration(self, player, context):
        """Check that the team context is registered for the season.

        The current data model ties season registration to teams, not directly
        to individual players. When a registration rule is active in a roster or
        match workflow, the player's selected team must therefore hold a
        non-cancelled season registration for the current season.
        """
        Registration = self.env.get("federation.season.registration")
        if Registration is None:
            return EligibilityResult()

        season_id = context.get("season_id")
        team_id = context.get("team_id")
        if not season_id or not team_id:
            return EligibilityResult()

        reg = Registration.search(
            [
                ("team_id", "=", team_id),
                ("season_id", "=", season_id),
                ("state", "!=", "cancelled"),
            ],
            limit=1,
        )
        if not reg:
            team = self.env["federation.team"].browse(team_id)
            season = self.env["federation.season"].browse(season_id)
            return EligibilityResult(
                eligible=False,
                reasons=[
                    f"Team '{team.display_name}' is not registered for season '{season.name}'."
                ],
            )
        return EligibilityResult()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_rule_set(self, match):
        """Walk match → stage → tournament → competition for a rule set."""
        if match.stage_id and getattr(match.stage_id, "rule_set_id", False):
            return match.stage_id.rule_set_id
        if match.tournament_id and match.tournament_id.rule_set_id:
            return match.tournament_id.rule_set_id
        if match.tournament_id and match.tournament_id.competition_id:
            comp = match.tournament_id.competition_id
            if comp.rule_set_id:
                return comp.rule_set_id
        return self.env["federation.rule.set"].browse([])
