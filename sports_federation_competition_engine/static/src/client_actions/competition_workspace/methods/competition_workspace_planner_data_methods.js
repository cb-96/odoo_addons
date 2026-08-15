/** @odoo-module **/

export class CompetitionWorkspacePlannerDataMethods {
    syncPlannerSelection(planner = this.planner) {
        const validMatchIds = new Set();
        for (const match of planner?.unscheduled_matches || []) {
            validMatchIds.add(match.id);
        }
        for (const slot of planner?.slots || []) {
            if (slot.match?.id) {
                validMatchIds.add(slot.match.id);
            }
        }
        this.state.selectedMatchIds = (this.state.selectedMatchIds || []).filter((matchId) =>
            validMatchIds.has(Number(matchId))
        );
    }

    clearPlannerSelection() {
        this.state.selectedMatchIds = [];
        this.state.slotSuggestions = {
            items: [],
            loading: false,
            matchId: false,
        };
    }

    resetPlannerPagination() {
        this.state.plannerUnscheduledLimit = this.state.plannerPageSize;
    }

    resetPlannerFilters() {
        this.state.filters.divisionId = "";
        this.state.filters.roundNumber = "";
        this.state.filters.teamId = "";
        this.state.filters.conflictsOnly = false;
    }

    buildPlannerRpcFilters({ includeReferenceData = true, unscheduledLimit } = {}) {
        return {
            division_id: this.state.filters.divisionId || false,
            conflicts_only: this.state.filters.conflictsOnly,
            include_reference_data: includeReferenceData,
            round_number: this.state.filters.roundNumber || false,
            team_id: this.state.filters.teamId || false,
            unscheduled_limit: unscheduledLimit || this.state.plannerUnscheduledLimit,
        };
    }

    async reloadPlannerWorkspace({ includePlannerReferenceData = false } = {}) {
        await this.loadWorkspace({
            competitionId: this.state.currentCompetitionId,
            divisionId: this.state.currentDivisionId,
            gamedayId: this.state.currentGamedayId,
            includePlannerReferenceData,
            unscheduledLimit: this.state.plannerUnscheduledLimit,
        });
    }

    toggleMatchSelection(matchId) {
        const selectedMatchIds = new Set(this.state.selectedMatchIds || []);
        if (selectedMatchIds.has(matchId)) {
            selectedMatchIds.delete(matchId);
        } else {
            selectedMatchIds.add(matchId);
        }
        this.state.selectedMatchIds = [...selectedMatchIds];
        this.refreshSlotSuggestions();
    }

    toggleFilteredSelection() {
        const filteredMatchIds = this.filteredUnscheduledMatches.map((match) => match.id);
        if (!filteredMatchIds.length) {
            return;
        }
        const selectedMatchIds = new Set(this.state.selectedMatchIds || []);
        const allSelected = filteredMatchIds.every((matchId) => selectedMatchIds.has(matchId));
        for (const matchId of filteredMatchIds) {
            if (allSelected) {
                selectedMatchIds.delete(matchId);
            } else {
                selectedMatchIds.add(matchId);
            }
        }
        this.state.selectedMatchIds = [...selectedMatchIds];
        this.refreshSlotSuggestions();
    }

    async refreshSlotSuggestions() {
        if (!this.state.currentGamedayId || !this.shouldShowSlotSuggestions) {
            this.state.slotSuggestions = {
                items: [],
                loading: false,
                matchId: false,
            };
            return false;
        }

        const match = this.selectedUnscheduledMatches[0];
        this.state.slotSuggestions = {
            items: [],
            loading: true,
            matchId: match.id,
        };
        try {
            const suggestions = await this.orm.call(
                "federation.competition.workspace.service",
                "get_match_slot_suggestions",
                [match.id, this.state.currentGamedayId, 5]
            );
            if (this.state.slotSuggestions.matchId !== match.id) {
                return false;
            }
            this.state.slotSuggestions = {
                items: suggestions,
                loading: false,
                matchId: match.id,
            };
            return suggestions;
        } catch (error) {
            this.state.slotSuggestions = {
                items: [],
                loading: false,
                matchId: false,
            };
            this.notify(error.message || "Slot suggestions could not be loaded.", "warning");
            return false;
        }
    }

    async loadWorkspace({
        competitionId = this.state.currentCompetitionId,
        divisionId = this.state.currentDivisionId,
        gamedayId = this.state.currentGamedayId,
        includePlanner = Boolean(gamedayId),
        includePlannerReferenceData,
        unscheduledLimit,
    } = {}) {
        this.state.loading = true;
        this.state.error = null;
        try {
            const requestedGamedayId = gamedayId || false;
            const samePlannerTarget = Boolean(
                requestedGamedayId
                && this.planner?.gameday?.id
                && Number(this.planner.gameday.id) === Number(requestedGamedayId)
            );
            const resolvedIncludePlannerReferenceData = includePlannerReferenceData
                ?? !samePlannerTarget;
            const payload = await this.orm.call(
                "federation.competition.workspace.service",
                "get_competition_workspace_data",
                [competitionId || false, divisionId || false, {
                    gameday_id: requestedGamedayId,
                    include_planner: includePlanner,
                    include_planner_reference_data: resolvedIncludePlannerReferenceData,
                    planner_filters: requestedGamedayId
                        ? this.buildPlannerRpcFilters({
                            includeReferenceData: resolvedIncludePlannerReferenceData,
                            unscheduledLimit,
                        })
                        : false,
                }]
            );
            if (
                payload.planner
                && !resolvedIncludePlannerReferenceData
                && this.state.payload?.planner
            ) {
                payload.planner = {
                    ...this.state.payload.planner,
                    ...payload.planner,
                };
            }
            this.state.payload = payload;
            this.state.currentCompetitionId = payload.competition?.id || competitionId || false;
            this.state.currentDivisionId = payload.selected_division_id || divisionId || false;
            const resolvedRequestedGamedayId = payload.selected_division?.gamedays?.some(
                (day) => day.id === gamedayId
            )
                ? gamedayId
                : false;
            this.state.currentGamedayId = payload.planner?.gameday?.id
                || resolvedRequestedGamedayId
                || payload.selected_division?.gamedays?.[0]?.id
                || false;
            this.syncPlannerSelection(payload.planner);
            const stageOptions = payload.selected_division?.stage_options || [];
            if (stageOptions.length) {
                const defaultStageId = payload.planner?.gameday?.stage_id || stageOptions[0].id;
                const selectedStageId = String(this.state.gamedayForm.stage_id || "");
                if (!stageOptions.some((stage) => String(stage.id) === selectedStageId)) {
                    this.state.gamedayForm.stage_id = String(defaultStageId);
                }
            } else {
                this.state.gamedayForm.stage_id = "";
            }
            if (unscheduledLimit) {
                this.state.plannerUnscheduledLimit = unscheduledLimit;
            }
            if (resolvedRequestedGamedayId && !payload.planner) {
                await this.loadPlanner(resolvedRequestedGamedayId, {
                    includeReferenceData: resolvedIncludePlannerReferenceData,
                    silent: true,
                    unscheduledLimit,
                });
            }
            await this.loadCourtsForVenue(this.state.gamedayForm.venue_id || payload.planner?.gameday?.venue_id || false);
            await this.refreshCollaboration({
                activeSection: this.state.activeSection,
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                silent: true,
            });
            await this.refreshSlotSuggestions();
            this.persistUiState();
        } catch (error) {
            this.state.error = error.message || "The workspace could not be loaded.";
        } finally {
            this.state.loading = false;
        }
    }

    async loadPlanner(
        gamedayId,
        { silent = false, includeReferenceData, unscheduledLimit } = {}
    ) {
        if (!gamedayId) {
            return false;
        }
        if (!silent) {
            this.state.plannerLoading = true;
        }
        try {
            const requestedLimit = unscheduledLimit || this.state.plannerUnscheduledLimit;
            const samePlannerTarget = Boolean(
                this.planner?.gameday?.id
                && Number(this.planner.gameday.id) === Number(gamedayId)
            );
            const resolvedIncludeReferenceData = includeReferenceData ?? !samePlannerTarget;
            const planner = await this.orm.call(
                "federation.competition.workspace.service",
                "get_gameday_planner_data",
                [
                    gamedayId,
                    this.buildPlannerRpcFilters({
                        includeReferenceData: resolvedIncludeReferenceData,
                        unscheduledLimit: requestedLimit,
                    }),
                ]
            );
            const nextPlanner = !resolvedIncludeReferenceData && this.state.payload?.planner
                ? {
                    ...this.state.payload.planner,
                    ...planner,
                }
                : planner;
            if (this.state.payload) {
                this.state.payload.planner = nextPlanner;
            }
            this.state.currentGamedayId = nextPlanner.gameday.id;
            this.state.gamedayForm.selected_gameday_id = String(nextPlanner.gameday.id);
            this.state.gamedayForm.stage_id = nextPlanner.gameday.stage_id
                ? String(nextPlanner.gameday.stage_id)
                : "";
            this.state.gamedayForm.round_number = nextPlanner.gameday.sequence
                ? String(nextPlanner.gameday.sequence)
                : "";
            this.state.plannerUnscheduledLimit = requestedLimit;
            if (nextPlanner.gameday.venue_id) {
                this.state.gamedayForm.venue_id = String(nextPlanner.gameday.venue_id);
                await this.loadCourtsForVenue(nextPlanner.gameday.venue_id);
            }
            this.syncPlannerSelection(nextPlanner);
            await this.refreshCollaboration({
                activeSection: this.state.activeSection,
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: nextPlanner.gameday.id,
                silent: true,
            });
            await this.refreshSlotSuggestions();
            this.persistUiState();
            return nextPlanner;
        } catch (error) {
            this.notify(error.message || "The planner could not be refreshed.", "danger");
            return false;
        } finally {
            this.state.plannerLoading = false;
        }
    }

    async loadAvailableClubs() {
        this.state.availableClubs = await this.orm.searchRead(
            "federation.club",
            [],
            ["display_name"],
            { order: "name asc" }
        );
    }

    async loadTeamSearchData() {
        if (!this.state.currentDivisionId) {
            this.state.availableTeams = [];
            return;
        }
        this.state.teamSearchLoading = true;
        try {
            if (!this.state.availableClubs.length) {
                await this.loadAvailableClubs();
            }
            this.state.availableTeams = await this.orm.call(
                "federation.competition.workspace.service",
                "search_available_teams",
                [this.state.currentDivisionId, {
                    club_id: this.state.teamEntryForm.club_id
                        ? Number(this.state.teamEntryForm.club_id)
                        : false,
                    limit: 40,
                    query: this.state.teamEntryForm.search || false,
                }]
            );
        } catch (error) {
            this.notify(error.message || "Team search could not be refreshed.", "danger");
        } finally {
            this.state.teamSearchLoading = false;
        }
    }

    async loadCourtsForVenue(venueId) {
        if (!venueId) {
            this.state.availableCourts = [];
            return;
        }
        this.state.availableCourts = await this.orm.searchRead(
            "federation.playing.area",
            [["venue_id", "=", Number(venueId)]],
            ["display_name", "venue_id"],
            { order: "name asc" }
        );
    }

    async refreshCollaboration({
        competitionId = this.state.currentCompetitionId,
        divisionId = this.state.currentDivisionId,
        gamedayId = this.state.currentGamedayId,
        activeSection = this.state.activeSection,
        silent = true,
    } = {}) {
        if (!competitionId && !divisionId) {
            this.state.collaboration.workspace = false;
            this.state.collaboration.planner = false;
            return false;
        }
        try {
            const summary = await this.orm.call(
                "federation.competition.workspace.service",
                "heartbeat_workspace_presence",
                [competitionId || false, divisionId || false, gamedayId || false, activeSection || "overview"]
            );
            this.state.collaboration.workspace = summary.workspace_collaboration || false;
            this.state.collaboration.planner = summary.planner_collaboration || false;
            return summary;
        } catch (error) {
            if (!silent) {
                this.notify(
                    error.message || "Workspace collaboration status could not be refreshed.",
                    "warning"
                );
            }
            return false;
        }
    }

    notify(message, type = "info") {
        this.notification.add(message, { type });
    }

    setSection(section) {
        this.state.activeSection = section;
        if (section === "planner" && (this.state.currentGamedayId || this.gamedayOptions[0]?.id)) {
            this.loadPlanner(this.state.currentGamedayId || this.gamedayOptions[0].id, {
                includeReferenceData: !this.planner,
                silent: true,
            });
        }
        if (section === "teams") {
            this.loadTeamSearchData();
        }
        this.refreshCollaboration({
            activeSection: section,
            silent: true,
        });
        this.persistUiState();
    }
}
