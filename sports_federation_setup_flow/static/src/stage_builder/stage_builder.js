/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Component, onWillStart, useState } from "@odoo/owl";

const MODEL = "federation.stage.builder";

/**
 * Stage builder: stages as cards in columns (first stages left, the stages
 * they feed to the right) and every link written out as a sentence.
 */
export class StageBuilder extends Component {
    static template = "sports_federation_setup_flow.StageBuilder";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.structureId = Number(this.props.action?.params?.structure_id);
        this.state = useState({
            data: null,
            loading: true,
            busy: false,
            error: "",
            form: null,
            templateOpen: false,
            templateName: "",
            focusStage: null,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            if (!this.structureId) {
                throw new Error(_t("Open the stage builder from a division format."));
            }
            this.state.data = await this.orm.call(MODEL, "load", [this.structureId]);
        } catch (error) {
            this.state.error = error?.data?.message || error?.message || _t("Could not load this format.");
        } finally {
            this.state.loading = false;
        }
    }

    async run(method, ...args) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        try {
            const result = await this.orm.call(MODEL, method, [this.structureId, ...args]);
            if (result?.structure) {
                this.state.data = result;
                this.structureId = result.structure.id;
            }
            return result || true;
        } catch (error) {
            this.notification.add(error?.data?.message || _t("That change could not be saved."), {type: "danger"});
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    get editable() {
        return Boolean(this.state.data?.structure.editable) && !this.state.busy;
    }

    get columns() {
        const data = this.state.data;
        const columns = [];
        for (let index = 0; index < data.columns; index++) {
            columns.push({
                index,
                label: index === 0 ? _t("Starts with") : _t("Then"),
                stages: data.stages.filter((stage) => stage.column === index),
            });
        }
        return columns;
    }

    stageName(stageId) {
        return this.state.data.stages.find((stage) => stage.id === Number(stageId))?.name || "";
    }

    linksOf(stage) {
        return this.state.data.links.filter((link) => link.source_id === stage.id);
    }

    focus(issue) {
        this.state.focusStage = issue.stage_id
            || this.state.data.links.find((link) => link.id === issue.link_id)?.source_id
            || null;
        const element = this.state.focusStage && document.getElementById(`sf-stage-${this.state.focusStage}`);
        element?.scrollIntoView({block: "nearest", inline: "center"});
        element?.focus();
    }

    // Forms ---------------------------------------------------------------
    openStageForm(afterStage = null) {
        this.state.form = {
            kind: "stage",
            name: afterStage ? "" : _t("League"),
            format_type: afterStage ? "knockout" : "single_round_robin",
            after_stage_id: afterStage ? String(afterStage.id) : "",
            places: afterStage ? String(Math.max(afterStage.places_free, 2)) : "",
        };
    }

    openLinkForm(source) {
        const first = source.next_free_place;
        this.state.form = {
            kind: "link",
            source_id: String(source.id),
            target_id: "",
            rank_from: String(first),
            rank_to: String(Math.max(first, source.teams)),
            target_seed_from: "",
        };
    }

    closeForm() {
        this.state.form = null;
    }

    async submitForm(event) {
        event?.preventDefault();
        const form = this.state.form;
        let result;
        if (form.kind === "stage") {
            result = await this.run("add_stage", {
                name: form.name,
                format_type: form.format_type,
                after_stage_id: form.after_stage_id ? Number(form.after_stage_id) : false,
                places: form.places ? Number(form.places) : false,
            });
        } else {
            result = await this.run("add_link", {
                source_id: Number(form.source_id),
                target_id: Number(form.target_id),
                rank_from: Number(form.rank_from),
                rank_to: Number(form.rank_to),
                target_seed_from: form.target_seed_from ? Number(form.target_seed_from) : false,
            });
        }
        if (result) {
            this.closeForm();
        }
    }

    // Inline edits ----------------------------------------------------------
    rename(stage, event) {
        const name = event.target.value.trim();
        if (name && name !== stage.name) {
            return this.run("update_stage", stage.id, {name});
        }
        event.target.value = stage.name;
    }

    changeFormat(stage, event) {
        return this.run("update_stage", stage.id, {format_type: event.target.value});
    }

    changeCarryover(stage, event) {
        return this.run("update_stage", stage.id, {carryover_policy: event.target.value});
    }

    removeStage(stage) {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Remove stage"),
            body: _t("Remove %s and the links to and from it?", stage.name),
            confirmLabel: _t("Remove"),
            confirm: () => this.run("delete_stage", stage.id),
            cancel: () => {},
        });
    }

    removeLink(link) {
        return this.run("delete_link", link.id);
    }

    // Structure actions -----------------------------------------------------
    async generate() {
        const action = await this.run("generate");
        if (action && action.type) {
            await this.action.doAction(action);
        }
    }

    async newVersion() {
        if (await this.run("new_version")) {
            this.notification.add(_t("You are editing a new version. The old one stays until you generate this one."), {type: "info"});
        }
    }

    async saveTemplate(event) {
        event?.preventDefault();
        const result = await this.run("save_template", this.state.templateName || this.state.data.structure.name);
        if (result) {
            this.state.templateOpen = false;
            this.notification.add(_t("Saved as “%s”. Choose it next season under “Start from a saved format”.", result.name), {type: "success"});
        }
    }

    async backToPlanner() {
        const editionId = this.state.data?.structure.edition_id;
        if (!editionId) {
            return this.action.restore();
        }
        const action = await this.orm.call("federation.competition.edition", "action_open_competition_planner", [[editionId]]);
        return this.action.doAction(action);
    }
}

registry.category("actions").add("federation_stage_builder", StageBuilder);
