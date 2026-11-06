/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { clashes, dayLabel, gridRows, matchesFilter, timeLabel } from "./season_board_helpers";

const MODEL = "federation.season.board";
const UNDO_LIMIT = 20;

/**
 * Season match board: unplanned matches on the left, a court × time grid of
 * the chosen game day on the right and every game day as a drop target.
 * Drag a match, or click it and then click a slot or a day. Changes apply
 * at once and can be undone.
 */
export class SeasonBoard extends Component {
    static template = "sports_federation_live_workspace.SeasonBoard";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.editionId = Number(this.props.action?.params?.edition_id);
        this.state = useState({
            data: null,
            loading: true,
            busy: false,
            error: "",
            dayId: null,
            picked: null,
            selected: [],
            dragId: null,
            dropTarget: null,
            undo: [],
            filters: {division: "", stage: "", round: "", text: ""},
            showPlanned: false,
            rejected: [],
        });
        this.onKeydown = (event) => {
            if (event.key === "Escape") {
                this.state.picked = null;
            }
        };
        window.addEventListener("keydown", this.onKeydown);
        onWillUnmount(() => window.removeEventListener("keydown", this.onKeydown));
        onWillStart(() => this.load());
    }

    // Loading ---------------------------------------------------------------
    async load() {
        this.state.loading = true;
        this.state.error = "";
        try {
            if (!this.editionId) {
                throw new Error(_t("Open the match board from a competition."));
            }
            this.accept(await this.orm.call(MODEL, "load", [this.editionId]));
        } catch (error) {
            this.state.error = error?.data?.message || error?.message || _t("Could not load the match board.");
        } finally {
            this.state.loading = false;
        }
    }

    accept(data) {
        this.state.data = data;
        const days = data.days;
        if (!days.find((day) => day.id === this.state.dayId)) {
            const firstOpen = days.find((day) => !day.locked && day.slots.length) || days[0];
            this.state.dayId = firstOpen ? firstOpen.id : null;
        }
        const known = new Set(data.fixtures.map((fixture) => fixture.id));
        this.state.selected = this.state.selected.filter((id) => known.has(id));
    }

    async command(method, args, {undoable = true} = {}) {
        if (this.state.busy) {
            return null;
        }
        this.state.busy = true;
        this.state.rejected = [];
        try {
            const result = await this.orm.call(MODEL, method, [this.editionId, ...args, this.state.data.signature]);
            this.accept(result);
            if (!result.ok) {
                this.state.rejected = result.rejected;
                this.notification.add(_t("Not moved: %s", result.rejected[0]), {type: "warning"});
            } else {
                if (undoable && result.changes.length) {
                    this.state.undo.push(result.changes);
                    this.state.undo.splice(0, Math.max(0, this.state.undo.length - UNDO_LIMIT));
                }
                if (result.notice) {
                    this.notification.add(result.notice, {type: "info"});
                }
            }
            return result;
        } catch (error) {
            this.notification.add(error?.data?.message || _t("That change could not be saved."), {type: "danger"});
            await this.load();
            return null;
        } finally {
            this.state.busy = false;
            this.state.picked = null;
        }
    }

    // Derived data ----------------------------------------------------------
    get data() {
        return this.state.data;
    }

    get day() {
        return this.data?.days.find((day) => day.id === this.state.dayId) || null;
    }

    get rows() {
        return this.day ? gridRows(this.day) : [];
    }

    get courts() {
        return this.day ? this.day.courts : [];
    }

    get unplanned() {
        return this.data.fixtures.filter((fixture) => !fixture.slot_id && matchesFilter(fixture, this.state.filters));
    }

    get waitingOnDay() {
        return this.day
            ? this.data.fixtures.filter((fixture) => fixture.day_id === this.day.id && !fixture.slot_id)
            : [];
    }

    get stages() {
        const division = Number(this.state.filters.division) || null;
        return this.data.stages.filter((stage) => !division || stage.division_id === division);
    }

    get rounds() {
        const values = new Set(this.data.fixtures.map((fixture) => fixture.round));
        return [...values].sort((a, b) => a - b);
    }

    get canUndo() {
        return this.state.undo.length > 0 && !this.state.busy && this.data.editable;
    }

    fixture(id) {
        return this.data.fixtures.find((item) => item.id === id);
    }

    fixtureOnSlot(slot) {
        return this.data.fixtures.find((item) => item.slot_id === slot.id);
    }

    dayUsage(day) {
        const used = this.data.fixtures.filter((fixture) => fixture.day_id === day.id && fixture.slot_id).length;
        return {used, total: day.playable_slots};
    }

    time(value) {
        return timeLabel(value, this.day?.timezone || "UTC");
    }

    dayName(day) {
        return dayLabel(day.date);
    }

    label(fixture) {
        return `${fixture.home} – ${fixture.away}`;
    }

    detail(fixture) {
        return `${fixture.division} · ${fixture.stage} · R${fixture.round}`;
    }

    activeFixture() {
        return this.fixture(this.state.dragId || this.state.picked);
    }

    slotHint(slot) {
        const fixture = this.activeFixture();
        if (!fixture || !this.day || slot.state !== "available") {
            return "";
        }
        if (this.day.division_ids.length && !this.day.division_ids.includes(fixture.division_id)) {
            return "blocked";
        }
        return clashes(fixture, slot, this.day, this.data.fixtures) ? "clash" : "free";
    }

    slotClass(slot) {
        const classes = ["sf-board-slot"];
        if (slot.state !== "available") {
            classes.push("sf-board-slot-off");
        }
        const hint = this.slotHint(slot);
        if (hint) {
            classes.push(`sf-board-hint-${hint}`);
        }
        if (this.state.dropTarget === `slot-${slot.id}`) {
            classes.push("sf-board-over");
        }
        return classes.join(" ");
    }

    cardClass(fixture) {
        const classes = ["sf-board-card"];
        if (fixture.errors.length) {
            classes.push("sf-board-card-error");
        } else if (fixture.warnings.length) {
            classes.push("sf-board-card-warning");
        }
        if (this.state.picked === fixture.id) {
            classes.push("sf-board-card-picked");
        }
        if (fixture.placeholder) {
            classes.push("sf-board-card-placeholder");
        }
        return classes.join(" ");
    }

    cardTitle(fixture) {
        return [this.detail(fixture), ...fixture.errors, ...fixture.warnings].join("\n");
    }

    canMove(fixture) {
        if (!this.data.editable || fixture.completed) {
            return false;
        }
        const day = fixture.day_id && this.data.days.find((item) => item.id === fixture.day_id);
        return !day || !day.locked;
    }

    // Selection and click-to-place -----------------------------------------
    pick(fixture) {
        if (!this.canMove(fixture)) {
            return;
        }
        this.state.picked = this.state.picked === fixture.id ? null : fixture.id;
    }

    toggleSelected(fixture, event) {
        const ids = new Set(this.state.selected);
        if (event.target.checked) {
            ids.add(fixture.id);
        } else {
            ids.delete(fixture.id);
        }
        this.state.selected = [...ids];
    }

    selectAllVisible(event) {
        this.state.selected = event.target.checked ? this.unplanned.map((fixture) => fixture.id) : [];
    }

    chooseDay(day) {
        if (this.state.picked) {
            return this.placeOnDay(day, [this.state.picked]);
        }
        this.state.dayId = day.id;
    }

    clickSlot(slot) {
        if (!this.state.picked) {
            const occupant = this.fixtureOnSlot(slot);
            if (occupant) {
                this.pick(occupant);
            }
            return;
        }
        return this.moveTo(this.state.picked, slot);
    }

    slotKey(slot, event) {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            return this.clickSlot(slot);
        }
    }

    slotAria(slot, court) {
        const occupant = this.fixtureOnSlot(slot);
        const when = `${this.time(slot.start)} ${court.name}`;
        return occupant ? `${when}: ${this.label(occupant)}` : `${when}: ${slot.state === "available" ? _t("free") : _t("not playable")}`;
    }

    scheduleLabel(state) {
        return {
            draft: _t("Working schedule"),
            changes_requested: _t("Changes requested"),
            ready_for_review: _t("In review"),
            approved: _t("Approved"),
            published: _t("Published"),
        }[state] || state;
    }

    // Commands ----------------------------------------------------------------
    moveTo(fixtureId, slot) {
        if (!this.day || this.day.locked || slot.state !== "available") {
            return;
        }
        return this.command("move", [fixtureId, slot.id]);
    }

    placeOnDay(day, fixtureIds) {
        if (day.locked || !fixtureIds.length) {
            return;
        }
        if (!day.slots.length) {
            this.notification.add(_t("%s has no time slots yet. Create them first.", day.name), {type: "warning"});
            return;
        }
        this.state.dayId = day.id;
        return this.command("place_on_day", [fixtureIds, day.id]);
    }

    placeSelected() {
        if (this.day) {
            return this.placeOnDay(this.day, this.state.selected).then(() => {
                this.state.selected = [];
            });
        }
    }

    unplan(fixture) {
        return this.command("unplan", [[fixture.id]]);
    }

    togglePin(fixture) {
        return this.command("set_pinned", [fixture.id, !fixture.pinned], {undoable: false});
    }

    generateSlots(day) {
        return this.command("generate_slots", [day.id], {undoable: false});
    }

    async undoLast() {
        const changes = this.state.undo.pop();
        if (!changes) {
            return;
        }
        const result = await this.command("restore", [changes], {undoable: false});
        if (!result || !result.ok) {
            this.state.undo = [];
        }
    }

    async autoPlan() {
        const action = await this.orm.call(MODEL, "auto_plan_action", [this.editionId]);
        await this.action.doAction(action, {onClose: () => this.load()});
        this.state.undo = [];
    }

    async openSchedule(day) {
        const action = await this.orm.call(MODEL, "open_day_schedule", [this.editionId, day.id]);
        await this.action.doAction(action);
    }

    // Drag and drop -----------------------------------------------------------
    dragStart(fixture, event) {
        if (!this.canMove(fixture)) {
            event.preventDefault();
            return;
        }
        this.state.dragId = fixture.id;
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(fixture.id));
    }

    dragEnd() {
        this.state.dragId = null;
        this.state.dropTarget = null;
    }

    dragOver(target, event, allowed = true) {
        if (!this.state.dragId || !allowed) {
            return;
        }
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        this.state.dropTarget = target;
    }

    dragLeave(target) {
        if (this.state.dropTarget === target) {
            this.state.dropTarget = null;
        }
    }

    draggedId(event) {
        return Number(event.dataTransfer.getData("text/plain")) || this.state.dragId;
    }

    dropOnSlot(slot, event) {
        event.preventDefault();
        const id = this.draggedId(event);
        this.dragEnd();
        if (id) {
            return this.moveTo(id, slot);
        }
    }

    dropOnDay(day, event) {
        event.preventDefault();
        const id = this.draggedId(event);
        this.dragEnd();
        if (id) {
            return this.placeOnDay(day, [id]);
        }
    }

    dropOnList(event) {
        event.preventDefault();
        const id = this.draggedId(event);
        this.dragEnd();
        const fixture = id && this.fixture(id);
        if (fixture && fixture.day_id) {
            return this.unplan(fixture);
        }
    }

    async backToPlanner() {
        try {
            const action = await this.orm.call("federation.competition.edition", "action_open_competition_planner", [[this.editionId]]);
            return this.action.doAction(action);
        } catch {
            return this.action.restore();
        }
    }
}

registry.category("actions").add("federation_season_board", SeasonBoard);
