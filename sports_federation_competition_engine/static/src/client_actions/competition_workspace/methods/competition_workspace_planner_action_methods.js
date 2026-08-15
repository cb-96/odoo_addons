/** @odoo-module **/

export class CompetitionWorkspacePlannerActionMethods {
    onDragStartMatch(matchId) {
        this.state.mobileAssign.match_id = String(matchId);
    }

    async assignMatch(matchId, slotId, force = false, overrideReason = false) {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const resolvedOverrideReason = overrideReason || (force
                ? this.state.overrideReason.pending.trim()
                : false);
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "assign_match_to_slot",
                [
                    matchId,
                    slotId,
                    force,
                    this.currentPlannerRevision,
                    resolvedOverrideReason || false,
                ]
            );
            if (!result.ok) {
                if (!force) {
                    this.state.overrideReason.pending = "";
                }
                this.state.pendingValidation = {
                    action: "assign",
                    allowForce: true,
                    matchId,
                    slotId,
                    title: "Assignment review",
                    validation: result.validation,
                };
                this.notify("Assignment needs attention before it can be saved.", "warning");
                return;
            }
            this.state.pendingValidation = null;
            this.state.overrideReason.pending = "";
            this.clearPlannerSelection();
            await this.reloadPlannerWorkspace();
            this.notify("Match assignment saved.", "success");
        } catch (error) {
            this.notify(error.message || "The match could not be assigned.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async unassignMatch(matchId) {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call(
                "federation.competition.workspace.service",
                "unassign_match",
                [matchId, this.currentPlannerRevision]
            );
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.reloadPlannerWorkspace();
            this.notify("Match unassigned.", "success");
        } catch (error) {
            this.notify(error.message || "The match could not be unassigned.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async handleDropMatch(matchId, slotId) {
        await this.assignMatch(matchId, slotId, false);
    }

    async bulkAssignMatches(matchIds, force = false, overrideReason = false) {
        if (!this.state.currentGamedayId || !matchIds.length) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const resolvedOverrideReason = overrideReason || (force
                ? this.state.overrideReason.pending.trim()
                : false);
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "bulk_assign_matches",
                [
                    this.state.currentGamedayId,
                    matchIds,
                    force,
                    this.currentPlannerRevision,
                    resolvedOverrideReason || false,
                ]
            );
            if (!result.ok) {
                if (!force) {
                    this.state.overrideReason.pending = "";
                }
                this.state.pendingValidation = {
                    action: "bulk_assign",
                    allowForce: true,
                    matchIds: [...matchIds],
                    title: "Bulk assignment review",
                    validation: result.validation,
                };
                this.notify("Bulk assignment needs attention before it can be saved.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            this.state.overrideReason.pending = "";
            await this.reloadPlannerWorkspace();
            this.notify(`${result.operation_count || matchIds.length} match(es) assigned.`, "success");
        } catch (error) {
            this.notify(error.message || "Bulk assignment failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async bulkAssignSelected() {
        if (this.hasMixedPlannerSelection) {
            this.notify(
                "Select only unscheduled matches or only scheduled matches before using a bulk action.",
                "warning"
            );
            return;
        }
        await this.bulkAssignMatches(this.selectedUnscheduledMatches.map((match) => match.id), false);
    }

    async bulkUnassignSelected() {
        if (this.hasMixedPlannerSelection) {
            this.notify(
                "Select only unscheduled matches or only scheduled matches before using a bulk action.",
                "warning"
            );
            return;
        }
        const matchIds = this.selectedAssignedMatches.map((match) => match.id);
        if (!this.state.currentGamedayId || !matchIds.length) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "bulk_unassign_matches",
                [this.state.currentGamedayId, matchIds, this.currentPlannerRevision]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "bulk_unassign",
                    allowForce: false,
                    matchIds: [...matchIds],
                    title: "Bulk unassignment review",
                    validation: result.validation,
                };
                this.notify("Bulk unassignment could not be completed.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.reloadPlannerWorkspace();
            this.notify(`${result.operation_count || matchIds.length} match(es) unassigned.`, "success");
        } catch (error) {
            this.notify(error.message || "Bulk unassignment failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    requestUnassignAllMatches() {
        if (!this.state.currentGamedayId || !this.plannerAssignedMatchCount) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.openConfirmDialog({
            action: "unassign_all",
            title: "Unassign all matches",
            message: `Unassign all ${this.plannerAssignedMatchCount} assigned match(es) on this gameday?`,
            confirmLabel: "Unassign all",
            tone: "danger",
        });
    }

    async unassignAllMatches() {
        if (!this.state.currentGamedayId || !this.plannerAssignedMatchCount || this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "unassign_all_matches",
                [this.state.currentGamedayId, this.currentPlannerRevision]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "unassign_all",
                    allowForce: false,
                    title: "Unassign all review",
                    validation: result.validation,
                };
                this.notify("Unassign all could not be completed.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.reloadPlannerWorkspace();
            this.notify(`${result.operation_count || 0} match(es) unassigned.`, "success");
        } catch (error) {
            this.notify(error.message || "Unassign all failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async autoScheduleGameday() {
        if (!this.state.currentGamedayId) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "auto_schedule_gameday",
                [
                    this.state.currentGamedayId,
                    this.currentPlannerRevision,
                    false,
                ]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "auto_schedule",
                    allowForce: false,
                    title: "Auto-schedule review",
                    validation: result.validation,
                };
                this.notify(
                    result.validation?.blocking?.[0]?.message
                        || "Auto-schedule could not be completed.",
                    "warning"
                );
                return;
            }

            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.reloadPlannerWorkspace();

            const assignedCount = Number(result.assigned_count || 0);
            const skippedCount = Number((result.skipped || []).length || 0);
            const skippedSummary = (result.skipped_reason_summary || [])
                .map((item) => `${item.code}: ${item.count}`)
                .join(", ");
            this.notify(
                `Auto-schedule assigned ${assignedCount} match(es)`
                + (skippedCount
                    ? `, skipped ${skippedCount}${skippedSummary ? ` (${skippedSummary})` : ""}.`
                    : "."),
                assignedCount ? "success" : "warning"
            );
        } catch (error) {
            this.notify(error.message || "Auto-schedule failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async undoPlannerAction() {
        if (!this.state.currentGamedayId) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "undo_last_planner_operation",
                [this.state.currentGamedayId, this.currentPlannerRevision]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "undo",
                    allowForce: false,
                    title: "Undo review",
                    validation: result.validation,
                };
                this.notify("The last planner action could not be undone.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.reloadPlannerWorkspace();
            this.notify("Last planner action undone.", "success");
        } catch (error) {
            this.notify(error.message || "Undo failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async redoPlannerAction() {
        if (!this.state.currentGamedayId) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "redo_last_planner_operation",
                [this.state.currentGamedayId, this.currentPlannerRevision]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "redo",
                    allowForce: false,
                    title: "Redo review",
                    validation: result.validation,
                };
                this.notify("The last planner action could not be redone.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.reloadPlannerWorkspace();
            this.notify("Last planner action redone.", "success");
        } catch (error) {
            this.notify(error.message || "Redo failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async forcePendingAssignment() {
        if (!this.state.pendingValidation) {
            return;
        }
        const overrideReason = this.state.overrideReason.pending.trim();
        if (this.state.pendingValidation.action === "bulk_assign") {
            await this.bulkAssignMatches(
                this.state.pendingValidation.matchIds || [],
                true,
                overrideReason
            );
            return;
        }
        await this.assignMatch(
            this.state.pendingValidation.matchId,
            this.state.pendingValidation.slotId,
            true,
            overrideReason
        );
    }

    async assignSelectedToSlot(slotId) {
        if (this.selectedUnscheduledMatches.length !== 1) {
            this.notify(
                "Select exactly one unscheduled match before assigning it to a slot.",
                "warning"
            );
            return;
        }
        await this.assignMatch(this.selectedUnscheduledMatches[0].id, slotId, false);
    }

    openMobileAssign(matchId) {
        this.state.mobileAssign.open = true;
        this.state.mobileAssign.match_id = String(matchId);
        this.state.mobileAssign.gameday_id = String(this.state.currentGamedayId || this.gamedayOptions[0]?.id || "");
        this.state.mobileAssign.slot_id = "";
    }

    closeMobileAssign() {
        this.state.mobileAssign.open = false;
        this.state.mobileAssign.match_id = "";
        this.state.mobileAssign.slot_id = "";
    }

    async confirmMobileAssign() {
        if (!this.state.mobileAssign.match_id || !this.state.mobileAssign.slot_id) {
            return;
        }
        await this.assignMatch(
            Number(this.state.mobileAssign.match_id),
            Number(this.state.mobileAssign.slot_id),
            false
        );
        this.closeMobileAssign();
    }

    clearPendingValidation() {
        this.state.pendingValidation = null;
        this.state.overrideReason.pending = "";
    }
}
