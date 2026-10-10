/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class CompetitionPlanner extends Component {
    static template = "sports_federation_setup_flow.CompetitionPlanner";

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.state = useState({loading: true, data: null});
        this.editionId = Number(this.props.action.params?.edition_id);
        onWillStart(() => this.load());
    }

    async load() {
        if (!this.editionId) {
            this.notification.add(_t("Open the planner from a competition."), {type: "warning"});
            this.state.loading = false;
            return;
        }
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "federation.competition.edition",
                "get_competition_planner_data",
                [[this.editionId]]
            );
        } finally {
            this.state.loading = false;
        }
    }

    async doPlannerAction(method, argument) {
        const args = argument === undefined ? [[this.editionId]] : [[this.editionId], argument];
        const result = await this.orm.call(
            "federation.competition.edition", method, args
        );
        return this.action.doAction(result, {onClose: () => this.load()});
    }

    openStep(step) {
        return this.doPlannerAction("action_open_planner_step", step);
    }

    openIssue(issue) {
        return this.doPlannerAction("action_open_planner_issue", issue.key);
    }

    openOperation(operation) {
        return this.doPlannerAction("action_open_planner_operation", operation);
    }

    openCurrent() {
        return this.openPrimary();
    }

    openPrimary() {
        const primary = this.state.data.primary_action;
        return primary.kind === "issue"
            ? this.doPlannerAction("action_open_planner_issue", primary.key)
            : this.openOperation(primary.key);
    }

    openAdvanced() {
        return this.doPlannerAction("action_open_planner_advanced");
    }

    openAdministration() {
        return this.doPlannerAction("action_open_planner_administration");
    }

    openBasics() {
        return this.openStep("basics");
    }

    statusIcon(step) {
        if (step.status === "complete") return "fa-check";
        if (step.status === "current") return "fa-arrow-right";
        return "fa-clock-o";
    }

    statusLabel(step) {
        if (step.status === "complete") return _t("Complete");
        if (step.status === "current") return _t("Current action");
        return _t("Not ready");
    }
}

registry.category("actions").add(
    "sports_federation_setup_flow.CompetitionPlanner", CompetitionPlanner
);
