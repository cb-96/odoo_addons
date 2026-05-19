# Route Inventory

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release

This is the maintainer-facing inventory of the primary browser and API entry
points that carry federation workflows. The goal is traceability: a maintainer
should be able to answer "which controller owns this route and which model or
service performs the write?" without reading source first.

Detailed route tables still live in module READMEs. This file highlights the
critical workflows, write boundaries, and external contracts.

These routes are backed by module-owned smoke suites in the portal,
public-site, compliance, and reporting addons. Inventory changes should land
with matching smoke coverage in the same branch so new owner modules or routes
cannot drift without test coverage.

## Browser and Portal Flows

| Route | Owner Module | Controller Entry Point | Downstream Model / Service | Notes |
|---|---|---|---|---|
| `GET /web/login` | `sports_federation_portal` | `FederationWebsiteLogin.web_login` | Website login wrapper | Preserves website context and recovers stale-CSRF submissions with a guided retry message. |
| `GET /sports/tournament/<id>/operations` | `sports_federation_portal` | `FederationTournamentOperationsPortal.portal_tournament_operations_page` | `federation.tournament._operations_get_payload` | Owl-powered tournament-day operations board with server-side access scoping and fast result actions. |
| `POST /my/teams/new` | `sports_federation_portal` | `FederationClubPortal.portal_my_teams_create` | `federation.team._portal_create_team` | Portal club ownership is validated before the privileged create. |
| `POST /my/players/new` | `sports_federation_portal` | `FederationClubPortal.portal_my_players_create` | `federation.player._portal_create_player` | Portal club ownership is validated before the privileged create; triggers optional member registration finance event. |
| `POST /my/season-registration/new` | `sports_federation_portal` | `FederationRegistrationPortal.portal_season_registration_submit` | `federation.season.registration._portal_submit_registration_request` | Submits season registrations through the shared ORM entry point. |
| `POST /my/referee-assignments/<id>/respond` | `sports_federation_portal` | `FederationOfficiatingPortal.portal_my_referee_assignment_respond` | `federation.match.referee._portal_action_confirm` / `_portal_action_decline` | Official self-service confirm / decline flow. |
| `POST /tournaments/<slug>/register` | `sports_federation_public_site` | `PublicTournamentHubController.tournament_register_submit` | `federation.tournament.registration._portal_submit_registration_request` | Shared registration helper used by both public-site and portal flows. |
| `POST /my/compliance/<requirement>/<target_model>/<target_id>/submit` | `sports_federation_compliance` | `FederationCompliancePortal.portal_my_compliance_submit` | `federation.document.submission._portal_submit_submission` | Portal uploads and submission writes stay inside the model boundary. |

## Reporting and Export Routes

| Route | Owner Module | Controller Entry Point | Downstream Model / Service | Notes |
|---|---|---|---|---|
| `GET /reporting/export/standings/<tournament_id>` | `sports_federation_reporting` | `KpiExportController.export_standings_csv` | `federation.standing` | Authenticated CSV contract `standings_csv`. |
| `GET /reporting/export/participation/<season_id>` | `sports_federation_reporting` | `KpiExportController.export_participation_csv` | `federation.tournament.participant` | Authenticated CSV contract `participation_csv`. |
| `GET /reporting/export/finance` | `sports_federation_reporting` | `KpiExportController.export_finance_csv` | `federation.report.finance` | Authenticated CSV contract `finance_summary_csv`. |
| `GET /reporting/export/finance/events` | `sports_federation_reporting` | `KpiExportController.export_finance_event_handoff_csv` | `federation.finance.event.get_handoff_export_row` | Authenticated CSV contract `finance_event_v1`. |

## Managed Integration Routes

| Route | Owner Module | Controller Entry Point | Downstream Model / Service | Notes |
|---|---|---|---|---|
| `GET /integration/v1/contracts` | `sports_federation_import_tools` | `FederationIntegrationApi.integration_contracts` | `federation.integration.partner.authenticate_partner` | Contract manifest for subscribed partners. |
| `GET /integration/v1/outbound/finance/events` | `sports_federation_import_tools` | `FederationIntegrationApi.integration_finance_events` | `federation.finance.event` | Partner-authenticated outbound finance handoff. |
| `POST /integration/v1/inbound/<contract_code>/deliveries` | `sports_federation_import_tools` | `FederationIntegrationApi.integration_stage_inbound_delivery` | `federation.integration.delivery.stage_partner_delivery` | Stages inbound payloads into the governed import pipeline. |

## Operator Surfaces

| Surface | Owner Module | Entry Point | Backing Model |
|---|---|---|---|
| Reporting operator checklist | `sports_federation_reporting` | Federation > Reporting > Operator Checklist | `federation.report.operator.checklist` |
| Scheduled report monitoring | `sports_federation_reporting` | Federation > Reporting > Report Schedules | `federation.report.schedule` |
| Inbound delivery monitoring | `sports_federation_import_tools` | Federation > Import Tools > Inbound Deliveries | `federation.integration.delivery` |
