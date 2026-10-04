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
            this.notification.add(
                _t("Open the planner from a competition."),
                {type: "warning"}
            );
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

    async openStep(step) {
        const result = await this.orm.call(
            "federation.competition.edition",
            "action_open_planner_step",
            [[this.editionId], step]
        );
        return this.action.doAction(result, {
            onClose: () => this.load(),
        });
    }

    openCurrent() {
        return this.openStep(this.state.data.current_step);
    }

    openBasics() {
        return this.openStep("basics");
    }

    statusIcon(step) {
        if (step.status === "complete") {
            return "fa-check";
        }
        if (step.status === "current") {
            return "fa-arrow-right";
        }
        return "fa-lock";
    }

    statusLabel(step) {
        if (step.status === "complete") {
            return _t("Complete");
        }
        if (step.status === "current") {
            return _t("Current step");
        }
        return _t("Waiting");
    }
}

registry.category("actions").add(
    "sports_federation_setup_flow.CompetitionPlanner",
    CompetitionPlanner
);
