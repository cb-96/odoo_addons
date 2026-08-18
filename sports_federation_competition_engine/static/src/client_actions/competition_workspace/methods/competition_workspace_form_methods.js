/** @odoo-module **/

export class CompetitionWorkspaceFormMethods {
    updateShellField(ev) {
        this.state.shellForm[ev.target.name] = ev.target.value;
    }

    updateDivisionField(ev) {
        this.state.divisionForm[ev.target.name] = ev.target.value;
        if (ev.target.name === "planning_format" && ev.target.value !== "pool_then_bracket") {
            this.state.divisionForm.pool_count = "2";
            this.state.divisionForm.pool_qualifier_count = "2";
        }
    }

    updateStageField(ev) {
        const fieldName = ev.target.name;
        this.state.stageForm[fieldName] = ev.target.type === "checkbox"
            ? ev.target.checked
            : ev.target.value;
    }

    async createStage() {
        const name = this.state.stageForm.name.trim();
        if (!name || !this.state.currentDivisionId) {
            this.notify("Provide a stage name before creating it.", "warning");
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_stage",
                [{
                    ...this.state.stageForm,
                    division_id: this.state.currentDivisionId,
                    sequence: this.state.stageForm.sequence
                        ? Number(this.state.stageForm.sequence)
                        : false,
                    source_stage_id: this.state.stageForm.source_stage_id
                        ? Number(this.state.stageForm.source_stage_id)
                        : false,
                    rank_from: Number(this.state.stageForm.rank_from || 1),
                    rank_to: Number(this.state.stageForm.rank_to || 1),
                }]
            );
            this.state.payload = result.payload;
            this.state.stageForm = {
                ...this.state.stageForm,
                name: "",
                sequence: "",
                source_stage_id: "",
                date_start: "",
                date_end: "",
            };
            this.notify("Stage created.", "success");
        } catch (error) {
            this.notify(error.message || "The stage could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async updateTeamEntryField(ev) {
        this.state.teamEntryForm[ev.target.name] = ev.target.value;
        if (["club_id", "search"].includes(ev.target.name)) {
            this.state.teamEntryForm.team_id = "";
            await this.loadTeamSearchData();
        }
    }

    async updateGamedayField(ev) {
        this.state.gamedayForm[ev.target.name] = ev.target.value;
        if (ev.target.name === "venue_id") {
            this.state.gamedayForm.courtIds = [];
            await this.loadCourtsForVenue(ev.target.value);
        }
    }

    updateFilterField(ev) {
        const name = ev.target.name;
        this.state.filters[name] = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
        this.clearPlannerSelection();
        this.resetPlannerPagination();
        this.persistUiState();
        if (this.state.currentGamedayId) {
            this.loadPlanner(this.state.currentGamedayId, {
                includeReferenceData: false,
                silent: true,
            });
        }
    }

    async updateMobileAssignField(ev) {
        this.state.mobileAssign[ev.target.name] = ev.target.value;
        if (ev.target.name === "gameday_id") {
            this.state.mobileAssign.slot_id = "";
            await this.loadPlanner(Number(ev.target.value), { silent: true });
        }
    }

    async updateDivisionPlanningRule(ev) {
        if (!this.state.currentDivisionId) {
            return;
        }
        const fieldName = ev.target.name;
        if (!["minimum_rest_minutes", "max_consecutive_matches_per_team"].includes(fieldName)) {
            return;
        }
        const rawValue = Number(ev.target.value || 0);
        const normalizedValue = fieldName === "minimum_rest_minutes"
            ? Math.max(rawValue, 0)
            : Math.max(rawValue || 1, 1);
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "update_division_planning_rules",
                [this.state.currentDivisionId, { [fieldName]: normalizedValue }]
            );
            this.state.payload = result.payload;
            this.notify("Planning rules updated.", "success");
        } catch (error) {
            this.notify(error.message || "Planning rules could not be updated.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    updatePendingOverrideReason(ev) {
        this.state.overrideReason.pending = ev.target.value;
    }

    updatePublishOverrideReason(ev) {
        this.state.overrideReason.publish = ev.target.value;
    }

    toggleCourt(ev) {
        const courtId = Number(ev.target.value);
        const selected = new Set(this.state.gamedayForm.courtIds);
        if (ev.target.checked) {
            selected.add(courtId);
        } else {
            selected.delete(courtId);
        }
        this.state.gamedayForm.courtIds = [...selected];
    }

    toggleSharedDivision(ev) {
        const divisionId = Number(ev.target.value);
        const selected = new Set(this.state.gamedayForm.sharedDivisionIds);
        const config = { ...this.state.gamedayForm.sharedDivisionConfig };
        if (ev.target.checked) {
            selected.add(divisionId);
            this.state.gamedayForm.sharedDivisionIds = [...selected];
            this.state.gamedayForm.sharedDivisionConfig = config;
            this.ensureSharedDivisionConfig(divisionId);
            return;
        } else {
            selected.delete(divisionId);
            delete config[String(divisionId)];
        }
        this.state.gamedayForm.sharedDivisionIds = [...selected];
        this.state.gamedayForm.sharedDivisionConfig = config;
    }

    updateSharedDivisionConfig(ev) {
        const divisionId = String(ev.target.dataset.divisionId || "");
        const fieldName = ev.target.name;
        if (!divisionId || !fieldName) {
            return;
        }
        const existingConfig = this.getSharedDivisionConfig(divisionId);
        const nextConfig = {
            ...existingConfig,
            [fieldName]: ev.target.value,
        };
        if (fieldName === "stage_id") {
            const roundOptions = this.getSharedDivisionRoundOptions(divisionId).filter(
                (roundItem) => String(roundItem.stage_id) === String(ev.target.value || "")
            );
            if (!roundOptions.some(
                (roundItem) => String(roundItem.round_number) === String(nextConfig.round_number)
            )) {
                nextConfig.round_number = roundOptions[0]?.round_number
                    ? String(roundOptions[0].round_number)
                    : "";
            }
        }
        this.state.gamedayForm.sharedDivisionConfig = {
            ...this.state.gamedayForm.sharedDivisionConfig,
            [divisionId]: nextConfig,
        };
    }

    async createCompetitionShell() {
        const name = this.state.shellForm.name.trim();
        const seasonId = this.state.shellForm.season_id
            ? Number(this.state.shellForm.season_id)
            : false;
        if (!name || !seasonId) {
            this.notify("Provide a competition name and a season before creating it.", "warning");
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_competition_shell",
                [{
                    competition_id: this.state.shellForm.competition_id ? Number(this.state.shellForm.competition_id) : false,
                    competition_vals: this.state.shellForm.competition_id ? {} : {
                        name,
                        competition_type: this.state.shellForm.competition_type,
                    },
                    date_end: this.state.shellForm.date_end || false,
                    date_start: this.state.shellForm.date_start || false,
                    name,
                    season_id: seasonId,
                }]
            );
            this.state.currentCompetitionId = result.competition_id;
            this.state.payload = result.payload;
            this.state.currentDivisionId = result.payload.selected_division_id || false;
            this.state.currentGamedayId = false;
            this.persistUiState();
            this.notify("Competition created.", "success");
        } catch (error) {
            this.notify(error.message || "The competition could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async createDivision() {
        if (!this.state.currentCompetitionId) {
            return;
        }
        this.state.saving = true;
        try {
            const vals = {
                category: this.state.divisionForm.category || false,
                date_end: this.state.divisionForm.date_end || false,
                date_start: this.state.divisionForm.date_start || false,
                gender: this.state.divisionForm.gender || false,
                max_consecutive_matches_per_team: Number(
                    this.state.divisionForm.max_consecutive_matches_per_team || 1
                ),
                minimum_rest_minutes: Number(this.state.divisionForm.minimum_rest_minutes || 30),
                name: this.state.divisionForm.name,
                planning_format: this.state.divisionForm.planning_format,
            };
            if (this.state.divisionForm.planning_format === "pool_then_bracket") {
                vals.pool_count = Number(this.state.divisionForm.pool_count || 2);
                vals.pool_qualifier_count = Number(
                    this.state.divisionForm.pool_qualifier_count || 2
                );
            }
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_division",
                [this.state.currentCompetitionId, vals]
            );
            this.state.payload = result.payload;
            this.state.currentDivisionId = result.division_id;
            this.state.currentGamedayId = false;
            this.persistUiState();
            if (this.state.activeSection === "teams") {
                await this.loadTeamSearchData();
            }
            this.notify("Division created.", "success");
        } catch (error) {
            this.notify(error.message || "The division could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async createTeamEntry() {
        if (!this.state.currentDivisionId || !this.state.teamEntryForm.team_id) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_team_entry",
                [this.state.currentDivisionId, {
                    seed: this.state.teamEntryForm.seed ? Number(this.state.teamEntryForm.seed) : false,
                    team_id: Number(this.state.teamEntryForm.team_id),
                }]
            );
            this.state.payload = result.payload;
            this.state.teamEntryForm.club_id = "";
            this.state.teamEntryForm.search = "";
            this.state.teamEntryForm.seed = "";
            this.state.teamEntryForm.team_id = "";
            await this.loadTeamSearchData();
            this.notify("Team entry added.", "success");
        } catch (error) {
            this.notify(error.message || "The team entry could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async confirmTeamEntry(ev) {
        const entryId = Number(ev.currentTarget.dataset.entryId);
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "confirm_team_entry",
                [entryId]
            );
            this.state.payload = result.payload;
            this.notify("Team entry confirmed.", "success");
        } catch (error) {
            this.notify(error.message || "The team entry could not be confirmed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async lockEntries() {
        if (!this.state.currentDivisionId) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "lock_team_entries",
                [this.state.currentCompetitionId || false, this.state.currentDivisionId]
            );
            this.state.payload = result.payload;
            this.notify("Participant list locked.", "success");
        } catch (error) {
            this.notify(error.message || "The participant list could not be locked.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async generateScheduleStructure() {
        if (!this.state.currentDivisionId) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "generate_schedule_structure",
                [this.state.currentDivisionId, false]
            );
            this.state.payload = result.payload;
            this.notify(`${result.match_count} match(es) generated.`, "success");
        } catch (error) {
            this.notify(error.message || "Schedule generation failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async generateRoundRobin() {
        await this.generateScheduleStructure();
    }

    async createGameday() {
        if (!this.state.currentDivisionId || !this.state.gamedayForm.round_date) {
            return;
        }
        this.state.saving = true;
        try {
            const sharedStageIds = {};
            const sharedRoundNumbers = {};
            for (const divisionId of this.state.gamedayForm.sharedDivisionIds) {
                const config = this.getSharedDivisionConfig(divisionId);
                if (config.stage_id) {
                    sharedStageIds[String(divisionId)] = Number(config.stage_id);
                }
                if (config.round_number) {
                    sharedRoundNumbers[String(divisionId)] = Number(config.round_number);
                }
            }
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_gameday",
                [{
                    division_id: this.state.currentDivisionId,
                    name: this.state.gamedayForm.name || false,
                    round_number: this.state.gamedayForm.round_number
                        ? Number(this.state.gamedayForm.round_number)
                        : false,
                    round_date: this.state.gamedayForm.round_date,
                    shared_division_ids: this.state.gamedayForm.sharedDivisionIds,
                    shared_round_numbers: sharedRoundNumbers,
                    shared_stage_ids: sharedStageIds,
                    stage_id: this.state.gamedayForm.stage_id
                        ? Number(this.state.gamedayForm.stage_id)
                        : false,
                    venue_id: this.state.gamedayForm.venue_id ? Number(this.state.gamedayForm.venue_id) : false,
                }]
            );
            this.state.payload = result.payload;
            this.state.currentGamedayId = result.gameday_id;
            this.state.gamedayForm.selected_gameday_id = String(result.gameday_id);
            this.state.gamedayForm.sharedDivisionIds = [];
            this.state.gamedayForm.sharedDivisionConfig = {};
            this.resetPlannerFilters();
            this.resetPlannerPagination();
            this.persistUiState();
            this.notify("Gameday created.", "success");
            await this.loadPlanner(result.gameday_id);
        } catch (error) {
            this.notify(error.message || "The gameday could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    requestDeleteGameday(ev) {
        const gamedayId = Number(ev.currentTarget.dataset.gamedayId || 0);
        const gameday = (this.selectedDivision?.gamedays || []).find(
            (record) => record.id === gamedayId
        );
        if (!gameday || this.state.saving) {
            return;
        }
        this.state.pendingGamedayDeletionId = gamedayId;
        this.openConfirmDialog({
            action: "delete_gameday",
            title: "Delete gameday",
            message: `Delete ${gameday.name}? This also removes its empty planning slots and any linked shared-division gamedays. Assigned or published gamedays cannot be deleted.`,
            confirmLabel: "Delete gameday",
            tone: "danger",
        });
    }

    async deleteGameday() {
        const gamedayId = this.state.pendingGamedayDeletionId;
        this.state.pendingGamedayDeletionId = false;
        if (!gamedayId || !this.state.currentDivisionId) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "delete_gameday",
                [gamedayId]
            );
            this.state.payload = result.payload;
            this.state.currentGamedayId = false;
            this.state.gamedayForm.selected_gameday_id = "";
            this.state.gamedayForm.courtIds = [];
            this.clearPlannerSelection();
            this.resetPlannerFilters();
            this.resetPlannerPagination();
            this.persistUiState();
            this.notify("Gameday deleted.", "success");
        } catch (error) {
            this.notify(error.message || "The gameday could not be deleted.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async generateSlots() {
        const gamedayId = Number(this.state.gamedayForm.selected_gameday_id || this.state.currentGamedayId || 0);
        if (!gamedayId || !this.state.gamedayForm.courtIds.length) {
            return;
        }
        this.state.saving = true;
        try {
            const expectedPlannerRevision = this.planner?.gameday?.planner_revision ?? false;
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "generate_slots",
                [
                    gamedayId,
                    this.state.gamedayForm.courtIds,
                    this.state.gamedayForm.start_time,
                    this.state.gamedayForm.end_time,
                    Number(this.state.gamedayForm.match_duration_minutes || 35),
                    Number(this.state.gamedayForm.buffer_minutes || 5),
                    [],
                    false,
                    expectedPlannerRevision,
                ]
            );
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId,
            });
            this.notify(`${result.slot_count} slot(s) generated.`, "success");
        } catch (error) {
            this.notify(error.message || "Slot generation failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async selectDivision(ev) {
        const divisionId = Number(ev.currentTarget.dataset.divisionId || 0);
        this.state.currentDivisionId = divisionId;
        this.state.currentGamedayId = false;
        this.resetPlannerFilters();
        this.state.gamedayForm.sharedDivisionIds = [];
        this.state.gamedayForm.sharedDivisionConfig = {};
        this.state.gamedayForm.round_number = "";
        this.state.gamedayForm.stage_id = "";
        this.clearPlannerSelection();
        this.clearPendingValidation();
        this.resetPlannerPagination();
        await this.loadWorkspace({
            competitionId: this.state.currentCompetitionId,
            divisionId,
            gamedayId: false,
        });
        if (this.state.activeSection === "teams") {
            await this.loadTeamSearchData();
        }
    }

    async selectGameday(ev) {
        const gamedayId = Number(ev.currentTarget.dataset.gamedayId || 0);
        this.clearPlannerSelection();
        this.clearPendingValidation();
        this.resetPlannerFilters();
        this.resetPlannerPagination();
        await this.loadPlanner(gamedayId);
    }

    async loadMoreUnscheduledMatches() {
        if (!this.planner?.unscheduled_has_more || !this.state.currentGamedayId) {
            return;
        }
        const nextLimit = this.state.plannerUnscheduledLimit + this.state.plannerPageSize;
        await this.loadPlanner(this.state.currentGamedayId, {
            includeReferenceData: false,
            unscheduledLimit: nextLimit,
        });
    }
}
