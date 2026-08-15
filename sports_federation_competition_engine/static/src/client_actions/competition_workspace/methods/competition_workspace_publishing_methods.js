/** @odoo-module **/

export class CompetitionWorkspacePublishingMethods {
    async validateSchedule() {
        if (!this.state.currentCompetitionId && !this.state.currentDivisionId) {
            return;
        }
        try {
            this.state.validationSnapshot = await this.orm.call(
                "federation.competition.workspace.service",
                "validate_competition_schedule",
                [this.state.currentCompetitionId || false, this.state.currentDivisionId || false]
            );
            this.notify("Schedule validation refreshed.", "info");
        } catch (error) {
            this.notify(error.message || "Schedule validation failed.", "danger");
        }
    }

    requestConfirmValidation() {
        if (!this.canConfirmValidation) {
            return;
        }
        this.openConfirmDialog({
            action: "confirm_validation",
            title: "Confirm validation",
            message: "Mark this gameday as validated after reviewing the schedule?",
            confirmLabel: "Confirm validation",
            tone: "success",
        });
    }

    openConfirmDialog({ action, title, message, confirmLabel = "Confirm", tone = "primary" }) {
        this.state.confirmDialog = {
            action,
            confirmLabel,
            message,
            open: true,
            title,
            tone,
        };
    }

    closeConfirmDialog() {
        this.state.confirmDialog = {
            action: false,
            confirmLabel: "Confirm",
            message: "",
            open: false,
            title: "Please confirm",
            tone: "primary",
        };
    }

    async confirmPendingAction() {
        const action = this.state.confirmDialog.action;
        this.closeConfirmDialog();
        if (action === "confirm_validation") {
            await this.confirmValidation();
            return;
        }
        if (action === "publish_gameday") {
            await this.publishGameday();
            return;
        }
        if (action === "publish_competition") {
            await this.publishCompetition();
            return;
        }
        if (action === "unassign_all") {
            await this.unassignAllMatches();
        }
    }

    requestPublishGameday() {
        if (!this.state.currentGamedayId || this.state.publishing) {
            return;
        }
        this.openConfirmDialog({
            action: "publish_gameday",
            title: "Publish gameday",
            message: "Publish this gameday and lock routine edits?",
            confirmLabel: "Publish gameday",
            tone: "primary",
        });
    }

    requestPublishCompetition() {
        if (this.state.publishing) {
            return;
        }
        this.openConfirmDialog({
            action: "publish_competition",
            title: "Publish competition",
            message: "Publish the competition schedule and lock routine edits?",
            confirmLabel: "Publish competition",
            tone: "primary",
        });
    }

    async publishGameday() {
        if (!this.state.currentGamedayId) {
            return;
        }
        this.state.publishing = true;
        try {
            const expectedPlannerRevision = this.planner?.gameday?.planner_revision ?? false;
            const overrideReason = this.state.overrideReason.publish.trim();
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "publish_gameday",
                [this.state.currentGamedayId, expectedPlannerRevision, overrideReason || false]
            );
            if (!result.ok) {
                this.state.validationSnapshot = result.validation;
                this.notify("The gameday still has blocking issues.", "warning");
                return;
            }
            this.state.payload = result.payload;
            this.state.overrideReason.publish = "";
            this.notify("Gameday published.", "success");
        } catch (error) {
            this.notify(error.message || "The gameday could not be published.", "danger");
        } finally {
            this.state.publishing = false;
        }
    }

    async publishCompetition() {
        if (!this.state.currentCompetitionId && !this.state.currentDivisionId) {
            return;
        }
        this.state.publishing = true;
        try {
            const overrideReason = this.state.overrideReason.publish.trim();
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "publish_competition_schedule",
                [
                    this.state.currentCompetitionId || false,
                    this.state.currentDivisionId || false,
                    overrideReason || false,
                ]
            );
            if (!result.ok) {
                this.state.validationSnapshot = result.validation;
                this.notify("The schedule still has blocking issues.", "warning");
                return;
            }
            this.state.payload = result.payload;
            this.state.overrideReason.publish = "";
            this.notify("Competition schedule published.", "success");
        } catch (error) {
            this.notify(error.message || "The competition schedule could not be published.", "danger");
        } finally {
            this.state.publishing = false;
        }
    }

    async confirmValidation() {
        if (!this.state.currentGamedayId) {
            return;
        }
        this.state.saving = true;
        try {
            const expectedPlannerRevision = this.currentPlannerRevision;
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "confirm_gameday_validation",
                [this.state.currentGamedayId, expectedPlannerRevision]
            );
            if (!result.ok) {
                this.state.validationSnapshot = result.validation;
                this.notify("The gameday still has blocking issues.", "warning");
                return;
            }
            this.state.validationSnapshot = result.validation;
            this.state.payload = result.payload;
            this.notify("Gameday validation confirmed.", "success");
        } catch (error) {
            this.notify(error.message || "The gameday could not be validated.", "danger");
        } finally {
            this.state.saving = false;
        }
    }
}
