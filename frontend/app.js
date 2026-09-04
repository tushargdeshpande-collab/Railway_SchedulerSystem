"use strict";

const API_BASE = "/api/v1";

const state = {
    dashboard: null,
    health: null,
    tasks: [],
    schedules: [],
    comparison: [],
    disruption: null,
    replanning: null,
    approval: null,
    planningHorizon: "weekly",
};

const pageTitles = {
    overview: "Operations Overview",
    planner: "Weekly Block Planner",
    comparison: "Plan Comparison",
    maintenance: "Maintenance Tasks",
    disruption: "Dynamic Replanning",
    sandbox: "Live Scenario Sandbox",
};


function byId(id) {
    return document.getElementById(id);
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


function firstObject(value) {
    if (Array.isArray(value)) {
        return value[0] ?? {};
    }

    if (value && typeof value === "object") {
        return value;
    }

    return {};
}


function formatDateTime(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value).replace("T", " ");
    }

    return new Intl.DateTimeFormat("en-IN", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    }).format(date);
}


function formatTime(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return String(value);
    }

    return new Intl.DateTimeFormat("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
    }).format(date);
}


function normalizeClass(value) {
    return String(value ?? "")
        .trim()
        .toLowerCase()
        .replaceAll("&", "and")
        .replaceAll(/[^a-z0-9]+/g, "-")
        .replaceAll(/^-|-$/g, "");
}


async function fetchJson(endpoint) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
            Accept: "application/json",
        },
    });

    if (!response.ok) {
        let detail =
            `${response.status} ${response.statusText}`;

        try {
            const errorBody = await response.json();
            detail = errorBody.detail ?? detail;
        } catch {
            // Retain the HTTP error message.
        }

        throw new Error(`${endpoint}: ${detail}`);
    }

    return response.json();
}


async function postJson(endpoint, payload) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        let detail =
            `${response.status} ${response.statusText}`;

        try {
            const errorBody = await response.json();

            if (Array.isArray(errorBody.detail)) {
                detail = errorBody.detail
                    .map((item) => item.msg)
                    .join("; ");
            } else {
                detail = errorBody.detail ?? detail;
            }
        } catch {
            // Retain the HTTP error message.
        }

        throw new Error(detail);
    }

    return response.json();
}


function setLoading(isLoading) {
    byId("loading-screen").classList.toggle(
        "hidden",
        !isLoading,
    );
}


function showError(message) {
    byId("error-message").textContent = message;
    byId("error-banner").classList.remove("hidden");
}


function hideError() {
    byId("error-banner").classList.add("hidden");
}


function renderSystemHealth() {
    const healthy =
        state.health?.status === "healthy"
        && state.health?.all_required_files_available === true;

    const statusElement = byId("system-status");
    const dotElement = byId("system-status-dot");

    statusElement.textContent = healthy
        ? "System healthy"
        : "System degraded";

    dotElement.classList.remove(
        "healthy",
        "unhealthy",
    );

    dotElement.classList.add(
        healthy ? "healthy" : "unhealthy",
    );
}


function renderKpis() {
    const kpis = state.dashboard?.kpis ?? {};

    const isMonthly =
        state.planningHorizon === "monthly";

    byId("kpi-maintenance-tasks").textContent =
        kpis.maintenance_tasks ?? "—";

    byId("kpi-scheduled-tasks").textContent =
        kpis.revised_scheduled_tasks ?? "—";

    byId("kpi-scheduled-detail").textContent =
        isMonthly
            ? `${kpis.revised_scheduled_tasks ?? "—"} of `
                + `${kpis.maintenance_tasks ?? "—"} tasks `
                + "in optimized monthly plan"
            : `${kpis.revised_scheduled_tasks ?? "—"} of `
                + `${kpis.maintenance_tasks ?? "—"} tasks `
                + "in revised weekly plan";

    byId("kpi-revised-blocks").textContent =
        kpis.revised_blocks ?? "—";

    const originalBlocks =
        Number(kpis.original_blocks ?? 0);

    const revisedBlocks =
        Number(kpis.revised_blocks ?? 0);

    const blockDifference =
        originalBlocks - revisedBlocks;

    byId("kpi-block-reduction").textContent =
        blockDifference > 0
            ? `${blockDifference} fewer than the original plan`
            : `Original plan used ${originalBlocks} blocks`;

    if (isMonthly) {
        const blockReduction =
            Number(
                kpis.block_reduction_percent ?? 0,
            );

        const utilization =
            Number(
                kpis.average_block_utilization_percent
                ?? 0,
            );

        byId(
            "planning-performance-description",
        ).textContent =
            "Validated 30-day strategic maintenance plan "
            + "across multiple synthetic corridors.";

        byId("kpi-card-four-label").textContent =
            "Blocks avoided";

        byId("kpi-direct-conflicts").textContent =
            kpis.blocks_reduced_after_replanning
            ?? blockDifference;

        byId("kpi-card-four-detail").textContent =
            `${blockReduction.toFixed(1)}% reduction `
            + "against decentralized baseline";

        byId("kpi-card-five-label").textContent =
            "Bundled blocks";

        byId("kpi-replanning-scope").textContent =
            kpis.bundled_blocks ?? "—";

        byId("kpi-card-five-detail").textContent =
            `${kpis.tasks_in_bundled_blocks ?? "—"} `
            + "tasks coordinated in shared blocks";

        byId("kpi-card-six-label").textContent =
            "Average utilization";

        byId("kpi-remaining-conflicts").textContent =
            `${utilization.toFixed(2)}%`;

        byId("kpi-card-six-detail").textContent =
            `Across ${revisedBlocks} optimized `
            + "maintenance blocks";

        byId("flow-conflicts").textContent =
            `${blockDifference} blocks avoided`;
    } else {
        byId(
            "planning-performance-description",
        ).textContent =
            "Validated maintenance and operational "
            + "outcomes after dynamic replanning.";

        byId("kpi-card-four-label").textContent =
            "Direct conflicts detected";

        byId("kpi-direct-conflicts").textContent =
            kpis.direct_freight_conflicts ?? "—";

        byId("kpi-card-four-detail").textContent =
            "Priority perishable freight event";

        byId("kpi-card-five-label").textContent =
            "Replanning scope";

        byId("kpi-replanning-scope").textContent =
            kpis.replanning_scope_tasks ?? "—";

        byId("kpi-card-five-detail").textContent =
            "Direct, resource and dependency effects";

        byId("kpi-card-six-label").textContent =
            "Remaining conflicts";

        byId("kpi-remaining-conflicts").textContent =
            kpis.remaining_freight_conflicts ?? "—";

        byId("kpi-card-six-detail").textContent =
            "Normal trains and priority freight";

        byId("flow-conflicts").textContent =
            `${kpis.direct_freight_conflicts ?? "—"} `
            + "direct tasks";
    }

    byId("solver-status").textContent =
        `Solver ${kpis.solver_status ?? "—"}`;

    byId("validation-status").textContent =
        `Validation ${kpis.validation_status ?? "—"}`;

    byId("flow-runtime").textContent =
        `${kpis.solver_runtime_seconds ?? "—"} seconds`;
}

function renderDistribution(containerId, data, type) {
    const container = byId(containerId);
    const entries = Object.entries(data ?? {});

    if (entries.length === 0) {
        container.innerHTML =
            '<div class="empty-state">'
            + "No distribution data."
            + "</div>";
        return;
    }

    const maximum = Math.max(
        ...entries.map(
            ([, count]) => Number(count),
        ),
        1,
    );

    container.innerHTML = entries
        .map(([label, count], index) => {
            const width =
                (Number(count) / maximum) * 100;

            const fillClass =
                type === "priority"
                    ? normalizeClass(label)
                    : `department-${index}`;

            return `
                <div class="distribution-row">
                    <span class="distribution-label">
                        ${escapeHtml(label)}
                    </span>

                    <div class="distribution-bar">
                        <div
                            class="distribution-fill ${fillClass}"
                            style="width: ${width}%"
                        ></div>
                    </div>

                    <span class="distribution-value">
                        ${escapeHtml(count)}
                    </span>
                </div>
            `;
        })
        .join("");
}


function renderOverview() {
    renderKpis();

    renderDistribution(
        "priority-distribution",
        state.dashboard?.priority_distribution,
        "priority",
    );

    renderDistribution(
        "department-distribution",
        state.dashboard?.department_distribution,
        "department",
    );
}


function populateSectionFilters() {
    const sectionIds = [
        ...new Set(
            state.schedules
                .map(
                    (schedule) =>
                        schedule.section_id,
                )
                .filter(Boolean),
        ),
    ].sort();

    const options = sectionIds
        .map(
            (sectionId) => `
                <option value="${escapeHtml(sectionId)}">
                    ${escapeHtml(sectionId)}
                </option>
            `,
        )
        .join("");

    byId("planner-section-filter").innerHTML =
        '<option value="">All sections</option>'
        + options;
}


function utilizationMarkup(value) {
    const number = Math.max(
        0,
        Math.min(
            100,
            Number(value ?? 0),
        ),
    );

    return `
        <div class="utilization">
            <span>${number.toFixed(1)}%</span>

            <div class="utilization-track">
                <div
                    class="utilization-fill"
                    style="width: ${number}%"
                ></div>
            </div>
        </div>
    `;
}



function renderApprovalPanel() {
    const approval =
        state.approval ?? {};

    const plan =
        approval.plan ?? {};

    const status =
        plan.status ?? "Pending";

    const statusElement =
        byId("plan-approval-status");

    statusElement.textContent = status;

    statusElement.classList.remove(
        "approval-approved",
        "approval-rejected",
        "approval-pending",
    );

    statusElement.classList.add(
        status === "Approved"
            ? "approval-approved"
            : (
                status === "Rejected"
                    ? "approval-rejected"
                    : "approval-pending"
            ),
    );

    const lockedCount =
        Number(
            approval.locked_block_count ?? 0,
        );

    byId("locked-block-count").textContent =
        `${lockedCount} locked `
        + (
            lockedCount === 1
                ? "block"
                : "blocks"
        );

    if (plan.approver_name) {
        byId("approval-name").value =
            plan.approver_name;
    }

    if (plan.approver_role) {
        byId("approval-role").value =
            plan.approver_role;
    }

    if (plan.remarks) {
        byId("approval-remarks").value =
            plan.remarks;
    }

    const selectedBlock =
        byId("approval-block-id").value;

    const lockedIds = new Set(
        (approval.locked_blocks ?? [])
            .filter((item) => item.locked)
            .map((item) => item.block_id),
    );

    const blockOptions = state.schedules
        .map((schedule) => schedule.block_id)
        .filter(Boolean)
        .filter(
            (blockId, index, array) =>
                array.indexOf(blockId) === index,
        )
        .sort()
        .map((blockId) => {
            const suffix =
                lockedIds.has(blockId)
                    ? " — Locked"
                    : "";

            return `
                <option value="${escapeHtml(blockId)}">
                    ${escapeHtml(blockId + suffix)}
                </option>
            `;
        })
        .join("");

    byId("approval-block-id").innerHTML =
        '<option value="">Select a block</option>'
        + blockOptions;

    if (
        selectedBlock
        && state.schedules.some(
            (schedule) =>
                schedule.block_id === selectedBlock,
        )
    ) {
        byId("approval-block-id").value =
            selectedBlock;
    }
}


function getApprovalIdentity() {
    const actorName =
        byId("approval-name")
            .value
            .trim();

    const actorRole =
        byId("approval-role")
            .value
            .trim();

    const remarks =
        byId("approval-remarks")
            .value
            .trim();

    if (
        actorName.length < 2
        || actorRole.length < 2
    ) {
        throw new Error(
            "Approver name and role are required.",
        );
    }

    return {
        actorName,
        actorRole,
        remarks: remarks || null,
    };
}


async function refreshApprovalStatus() {
    state.approval = await fetchJson(
        `/approvals?planning_horizon=${
            state.planningHorizon
        }`,
    );

    renderApprovalPanel();
}


async function submitPlanDecision(decision) {
    hideError();

    try {
        const identity =
            getApprovalIdentity();

        const result = await postJson(
            "/approvals/decision",
            {
                planning_horizon:
                    state.planningHorizon,

                decision,

                approver_name:
                    identity.actorName,

                approver_role:
                    identity.actorRole,

                remarks:
                    identity.remarks,
            },
        );

        byId("approval-message").textContent =
            result.message;

        await refreshApprovalStatus();
    } catch (error) {
        console.error(error);
        showError(error.message);
    }
}


async function submitBlockLock(locked) {
    hideError();

    try {
        const identity =
            getApprovalIdentity();

        const blockId =
            byId("approval-block-id").value;

        if (!blockId) {
            throw new Error(
                "Select a maintenance block first.",
            );
        }

        const result = await postJson(
            `/blocks/${
                encodeURIComponent(blockId)
            }/lock`,
            {
                planning_horizon:
                    state.planningHorizon,

                locked,

                actor_name:
                    identity.actorName,

                actor_role:
                    identity.actorRole,

                reason:
                    identity.remarks,
            },
        );

        byId("approval-message").textContent =
            result.message;

        await refreshApprovalStatus();

        byId("approval-block-id").value =
            blockId;
    } catch (error) {
        console.error(error);
        showError(error.message);
    }
}


function renderScheduleTable() {
    const department =
        byId("planner-department-filter").value;

    const sectionId =
        byId("planner-section-filter").value;

    const trackId =
        byId("planner-track-filter").value;

    const filtered = state.schedules.filter(
        (schedule) => {
            const departmentMatches =
                !department
                || (schedule.departments ?? [])
                    .includes(department);

            const sectionMatches =
                !sectionId
                || schedule.section_id === sectionId;

            const trackMatches =
                !trackId
                || schedule.track_id === trackId;

            return (
                departmentMatches
                && sectionMatches
                && trackMatches
            );
        },
    );

    const body =
        byId("schedule-table-body");

    const emptyState =
        byId("schedule-empty-state");

    if (filtered.length === 0) {
        body.innerHTML = "";
        emptyState.classList.remove("hidden");
        return;
    }

    emptyState.classList.add("hidden");

    body.innerHTML = filtered
        .map((schedule) => {
            const tasks = (
                schedule.task_ids ?? []
            )
                .map(
                    (taskId) => `
                        <span class="task-chip">
                            ${escapeHtml(taskId)}
                        </span>
                    `,
                )
                .join("");

            const departments = (
                schedule.departments ?? []
            )
                .map(
                    (departmentName) => `
                        <span class="department-chip">
                            ${escapeHtml(departmentName)}
                        </span>
                    `,
                )
                .join("");

            let trackLabel = schedule.track_id;

            if (schedule.track_id === "PL-UP") {
                trackLabel = "Pune → Lonavala";
            }

            if (schedule.track_id === "PL-DOWN") {
                trackLabel = "Lonavala → Pune";
            }

            return `
                <tr>
                    <td>
                        <span class="table-primary">
                            ${formatDateTime(
                                schedule.scheduled_start,
                            )}
                        </span>

                        <span class="table-secondary">
                            Until
                            ${formatTime(
                                schedule.scheduled_end,
                            )}
                        </span>
                    </td>

                    <td>
                        <span class="table-primary">
                            ${escapeHtml(
                                schedule.section_id,
                            )}
                        </span>

                        <span class="table-secondary">
                            ${escapeHtml(
                                schedule.block_id,
                            )}
                        </span>
                    </td>

                    <td>
                        ${escapeHtml(trackLabel)}
                    </td>

                    <td>
                        <div class="task-list">
                            ${tasks}
                        </div>
                    </td>

                    <td>
                        <div class="department-list">
                            ${departments}
                        </div>
                    </td>

                    <td>
                        ${utilizationMarkup(
                            schedule.utilization_percent,
                        )}
                    </td>

                    <td>
                        <span class="status-chip">
                            ${escapeHtml(
                                schedule.status,
                            )}
                        </span>
                    </td>
                </tr>
            `;
        })
        .join("");
}


function renderComparisonSummary() {
    const counts = {};

    for (const change of state.comparison) {
        const classification =
            change.classification ?? "Modified";

        counts[classification] =
            (counts[classification] ?? 0) + 1;
    }

    byId("comparison-summary").innerHTML =
        Object.entries(counts)
            .map(
                ([classification, count]) => `
                    <span class="summary-pill">
                        ${escapeHtml(classification)}:
                        ${escapeHtml(count)}
                    </span>
                `,
            )
            .join("");
}


function renderComparisonTable() {
    byId("comparison-table-body").innerHTML =
        state.comparison
            .map((change) => {
                const customImpactLabel =
                    change.impact_label;

                const impactClass =
                    customImpactLabel
                        ? "cascade"
                        : (
                            change.direct_freight_conflict
                                ? "direct"
                                : "cascade"
                        );

                const impactLabel =
                    customImpactLabel
                    ?? (
                        change.direct_freight_conflict
                            ? "Direct"
                            : "Cascade"
                    );

                const classification =
                    change.classification ?? "Modified";

                return `
                    <tr>
                        <td>
                            <span class="table-primary">
                                ${escapeHtml(change.task_id)}
                            </span>
                        </td>

                        <td>
                            <span
                                class="impact-chip ${impactClass}"
                            >
                                ${impactLabel}
                            </span>
                        </td>

                        <td>
                            ${formatDateTime(
                                change.original_start,
                            )}
                        </td>

                        <td>
                            ${formatDateTime(
                                change.revised_start,
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                change.original_block_id
                                ?? "—",
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                change.revised_block_id
                                ?? "—",
                            )}
                        </td>

                        <td>
                            <span
                                class="
                                    classification-chip
                                    ${normalizeClass(
                                        classification,
                                    )}
                                "
                            >
                                ${escapeHtml(classification)}
                            </span>
                        </td>
                    </tr>
                `;
            })
            .join("");

    renderComparisonSummary();
}


function renderTaskTable() {
    const department =
        byId("task-department-filter").value;

    const priority =
        byId("task-priority-filter").value;

    const search =
        byId("task-search")
            .value
            .trim()
            .toLowerCase();

    const filtered = state.tasks.filter(
        (task) => {
            const departmentMatches =
                !department
                || task.department === department;

            const priorityMatches =
                !priority
                || task.priority_level === priority;

            const searchableText = [
                task.task_id,
                task.asset_id,
                task.asset_type,
                task.defect_type,
                task.section_id,
                task.required_team,
            ]
                .filter(Boolean)
                .join(" ")
                .toLowerCase();

            const searchMatches =
                !search
                || searchableText.includes(search);

            return (
                departmentMatches
                && priorityMatches
                && searchMatches
            );
        },
    );

    byId("task-table-body").innerHTML =
        filtered
            .map((task) => {
                const overdueDays =
                    Number(task.overdue_days ?? 0);

                return `
                    <tr>
                        <td>
                            <span class="table-primary">
                                ${escapeHtml(task.task_id)}
                            </span>

                            <span class="table-secondary">
                                ${escapeHtml(
                                    task.source_system,
                                )}
                            </span>
                        </td>

                        <td>
                            ${escapeHtml(task.department)}
                        </td>

                        <td>
                            <span class="table-primary">
                                ${escapeHtml(task.asset_id)}
                            </span>

                            <span class="table-secondary">
                                ${escapeHtml(task.asset_type)}
                            </span>
                        </td>

                        <td>
                            ${escapeHtml(task.section_id)}
                        </td>

                        <td>
                            <span
                                class="
                                    priority-chip
                                    ${normalizeClass(
                                        task.priority_level,
                                    )}
                                "
                            >
                                ${escapeHtml(
                                    task.priority_level,
                                )}
                            </span>
                        </td>

                        <td>
                            <span class="table-primary">
                                ${Number(
                                    task.priority_score ?? 0,
                                ).toFixed(1)}
                            </span>
                        </td>

                        <td>
                            ${
                                overdueDays > 0
                                    ? `${overdueDays} days`
                                    : "On time"
                            }
                        </td>

                        <td>
                            ${escapeHtml(task.required_team)}
                        </td>
                    </tr>
                `;
            })
            .join("");
}


function findValue(objects, keys, fallback = "—") {
    for (const object of objects) {
        if (
            !object
            || typeof object !== "object"
        ) {
            continue;
        }

        for (const key of keys) {
            const value = object[key];

            if (
                value !== undefined
                && value !== null
                && value !== ""
            ) {
                return value;
            }
        }
    }

    return fallback;
}


function renderDisruption() {
    const disruption =
        state.disruption ?? {};

    const event =
        firstObject(disruption.event);

    const analysis =
        firstObject(disruption.analysis);

    const movements =
        Array.isArray(disruption.movements)
            ? disruption.movements
            : [];

    const metrics =
        state.replanning?.metrics ?? {};

    const eventSources = [
        event,
        analysis,
        metrics,
    ];

    byId("event-type").textContent =
        findValue(
            eventSources,
            [
                "event_type",
                "name",
                "disruption_event",
            ],
            "Priority Perishable Goods Movement",
        );

    byId("event-direction").textContent =
        findValue(
            [
                event,
                movements[0],
                analysis,
            ],
            ["direction"],
        );

    const entryValue =
        findValue(
            eventSources,
            [
                "corridor_entry",
                "event_corridor_entry",
                "scheduled_entry",
                "start_time",
            ],
            null,
        );

    const exitValue =
        findValue(
            eventSources,
            [
                "corridor_exit",
                "event_corridor_exit",
                "scheduled_exit",
                "end_time",
            ],
            null,
        );

    byId("event-entry").textContent =
        entryValue
            ? formatDateTime(entryValue)
            : "—";

    byId("event-exit").textContent =
        exitValue
            ? formatDateTime(exitValue)
            : "—";

    byId("event-movements").textContent =
        String(movements.length);

    byId("impact-direct").textContent =
        metrics.directly_conflicting_tasks ?? "—";

    byId("impact-cascade").textContent =
        metrics.resource_or_dependency_cascade_tasks
        ?? "—";

    byId("impact-preserved").textContent =
        metrics.unaffected_schedules_preserved
        ?? "—";

    byId("impact-conflicts").textContent =
        metrics.remaining_priority_freight_conflicts
        ?? "—";

    const timeline =
        byId("freight-timeline");

    if (movements.length === 0) {
        timeline.innerHTML =
            '<div class="empty-state">'
            + "No priority freight movements available."
            + "</div>";
        return;
    }

    timeline.innerHTML = movements
        .sort(
            (first, second) =>
                String(
                    first.scheduled_entry,
                ).localeCompare(
                    String(
                        second.scheduled_entry,
                    ),
                ),
        )
        .map(
            (movement) => `
                <div class="freight-segment">
                    <strong>
                        ${escapeHtml(
                            movement.section_id,
                        )}
                    </strong>

                    <span>
                        ${formatTime(
                            movement.scheduled_entry,
                        )}
                        –
                        ${formatTime(
                            movement.scheduled_exit,
                        )}
                    </span>

                    <span>
                        ${escapeHtml(
                            movement.track_id,
                        )}
                    </span>
                </div>
            `,
        )
        .join("");
}

function classifySandboxChange(change) {
    if (!change.revised_start) {
        return "Unscheduled";
    }

    const sameStart =
        change.original_start
        === change.revised_start;

    const sameBlock =
        change.original_block_id
        === change.revised_block_id;

    if (!sameStart) {
        return "Rescheduled";
    }

    if (!sameBlock) {
        return "Reassigned";
    }

    return "Unchanged";
}



function uniqueSorted(values) {
    return [
        ...new Set(
            values
                .filter(Boolean)
                .map(String),
        ),
    ].sort();
}


function renderSandboxMetricDetails(
    valueElementId,
    summaryText,
    items,
) {
    const detailsIdByValueId = {
        "sandbox-conflicting-blocks":
            "sandbox-conflicting-block-details",

        "sandbox-direct-tasks":
            "sandbox-direct-task-details",

        "sandbox-scope":
            "sandbox-scope-task-details",
    };

    const detailsId =
        detailsIdByValueId[valueElementId];

    const details =
        byId(detailsId);

    if (!details) {
        return;
    }

    const safeItems =
        items.length > 0
            ? items
            : ["No records"];

    details.open = false;

    details.innerHTML = `
        <summary>
            ${escapeHtml(summaryText)}
            <span class="details-arrow">⌄</span>
        </summary>

        <div class="metric-detail-list">
            ${safeItems
                .map(
                    (item) => `
                        <div class="metric-detail-item">
                            ${escapeHtml(item)}
                        </div>
                    `,
                )
                .join("")}
        </div>
    `;
}

function renderSandboxDrilldowns(result) {
    const conflicts =
        result.conflicts ?? [];

    const changes =
        result.changes ?? [];

    const originalSchedules =
        result.original_schedule ?? [];

    const scheduleByTaskId =
        new Map();

    for (const schedule of originalSchedules) {
        for (
            const taskId
            of schedule.task_ids ?? []
        ) {
            scheduleByTaskId.set(
                String(taskId),
                schedule,
            );
        }
    }

    const conflictTaskIds = [];
    const explicitConflictBlockIds = [];

    for (const conflict of conflicts) {
        const taskIds =
            conflict.task_ids
            ?? conflict.affected_task_ids
            ?? conflict.maintenance_task_ids
            ?? [];

        conflictTaskIds.push(...taskIds);

        const explicitBlockId =
            conflict.block_id
            ?? conflict.maintenance_block_id
            ?? conflict.schedule_block_id
            ?? conflict.schedule?.block_id;

        if (explicitBlockId) {
            explicitConflictBlockIds.push(
                explicitBlockId,
            );
        }
    }

    const directTaskIds =
        uniqueSorted([
            ...conflictTaskIds,

            ...changes
                .filter(
                    (change) =>
                        change.direct_freight_conflict,
                )
                .map(
                    (change) =>
                        change.task_id,
                ),
        ]);

    const derivedBlockIds =
        directTaskIds
            .map(
                (taskId) =>
                    scheduleByTaskId
                        .get(taskId)
                        ?.block_id,
            )
            .filter(Boolean);

    const conflictingBlockIds =
        uniqueSorted([
            ...explicitConflictBlockIds,
            ...derivedBlockIds,
        ]);

    const scopeItems =
        changes
            .filter(
                (change) =>
                    change.task_id,
            )
            .map((change) => {
                const impact =
                    change.direct_freight_conflict
                        ? "Direct"
                        : "Cascade";

                const classification =
                    change.classification
                    ?? classifySandboxChange(change);

                return (
                    `${change.task_id} — `
                    + `${impact}, `
                    + `${classification}`
                );
            });

    renderSandboxMetricDetails(
        "sandbox-conflicting-blocks",
        `View ${conflictingBlockIds.length} block(s)`,
        conflictingBlockIds,
    );

    renderSandboxMetricDetails(
        "sandbox-direct-tasks",
        `View ${directTaskIds.length} direct task(s)`,
        directTaskIds,
    );

    renderSandboxMetricDetails(
        "sandbox-scope",
        `View ${scopeItems.length} scope task(s)`,
        scopeItems,
    );
}


function renderSandboxResult(result) {
    const metrics =
        result.metrics ?? {};

    const changes =
        result.changes ?? [];

    const conflicts =
        result.conflicts ?? [];

    const status =
        result.status
        ?? metrics.replanning_solver_status
        ?? "UNKNOWN";

    const statusElement =
        byId("sandbox-result-status");

    statusElement.textContent = status;

    statusElement.classList.remove(
        "sandbox-status-success",
        "sandbox-status-warning",
        "sandbox-status-error",
    );

    if (
        status === "OPTIMAL"
        || status === "FEASIBLE"
    ) {
        statusElement.classList.add(
            "sandbox-status-success",
        );
    } else if (
        status === "NO_REPLANNING_REQUIRED"
        || status
            === "MANUAL_INTERVENTION_REQUIRED"
    ) {
        statusElement.classList.add(
            "sandbox-status-warning",
        );
    } else {
        statusElement.classList.add(
            "sandbox-status-error",
        );
    }

    byId("sandbox-conflicting-blocks").textContent =
        conflicts.length;

    byId("sandbox-direct-tasks").textContent =
        metrics.directly_conflicting_tasks ?? 0;

    byId("sandbox-scope").textContent =
        metrics.total_replanning_scope_tasks ?? 0;

    byId("sandbox-rescheduled").textContent =
        metrics.affected_tasks_rescheduled ?? 0;

    byId("sandbox-remaining").textContent =
        metrics.remaining_priority_freight_conflicts
        ?? 0;

    const runtime = Number(
        metrics.replanning_runtime_seconds ?? 0,
    );

    byId("sandbox-runtime").textContent =
        `${runtime.toFixed(3)}s`;

    byId("sandbox-scenario-id").textContent =
        `Scenario ${result.scenario_id ?? "—"}`;

    renderSandboxDrilldowns(result);

    const eventData =
        result.event ?? {};

    const requestedConflicts = Number(
        eventData.conflicts_at_requested_time
        ?? conflicts.length,
    );

    const finalConflicts = Number(
        eventData.conflicts_after_delay
        ?? conflicts.length,
    );

    const conflictsAvoided = Number(
        eventData.conflicts_avoided_by_delay
        ?? 0,
    );

    const maximumDelay = Number(
        eventData.maximum_permissible_delay_minutes
        ?? 0,
    );

    const appliedDelay = Number(
        eventData.delay_applied_minutes
        ?? 0,
    );

    const optionsEvaluated = Number(
        metrics.delay_options_evaluated
        ?? result.delay_evaluations?.length
        ?? 1,
    );

    const requestedEntry =
        eventData.requested_corridor_entry
        ?? eventData.corridor_entry;

    const finalEntry =
        eventData.corridor_entry;

    const delaySummary =
        `Requested ${formatDateTime(requestedEntry)}; `
        + `final movement ${formatDateTime(finalEntry)}. `
        + `${optionsEvaluated} timing option(s) evaluated `
        + `within the ${maximumDelay}-minute allowance. `
        + `${appliedDelay} minute(s) applied, reducing `
        + `conflicting blocks from ${requestedConflicts} `
        + `to ${finalConflicts} `
        + `(${conflictsAvoided} avoided). `;

    if (
        status
        === "MANUAL_INTERVENTION_REQUIRED"
    ) {
        const lockedConflictCount =
            Number(
                metrics.locked_conflicting_blocks
                ?? result.locked_conflicts?.length
                ?? 0,
            );

        byId(
            "sandbox-result-description",
        ).textContent =
            delaySummary
            + `${lockedConflictCount} conflict(s) `
            + "involve an authorized locked block. "
            + "Automatic movement was stopped. "
            + "A controller must unlock the block, "
            + "change the train timing or issue an "
            + "authorized operational override.";
    } else if (
        status === "NO_REPLANNING_REQUIRED"
    ) {
        byId(
            "sandbox-result-description",
        ).textContent =
            delaySummary
            + "No maintenance replanning was required; "
            + "the approved base plan remains valid.";
    } else {
        byId(
            "sandbox-result-description",
        ).textContent =
            delaySummary
            + `${
                metrics.total_replanning_scope_tasks
                ?? 0
            } maintenance task(s) were re-optimized, `
            + "producing a validated conflict-free plan.";
    }

    const body =
        byId("sandbox-change-table-body");

    const noChanges =
        byId("sandbox-no-changes");

    if (changes.length === 0) {
        body.innerHTML = "";
        noChanges.classList.remove("hidden");
    } else {
        noChanges.classList.add("hidden");

        body.innerHTML = changes
            .map((change) => {
                const impactClass =
                    change.direct_freight_conflict
                        ? "direct"
                        : "cascade";

                const impactLabel =
                    change.direct_freight_conflict
                        ? "Direct"
                        : "Cascade";

                const classification =
                    classifySandboxChange(change);

                return `
                    <tr>
                        <td>
                            <span class="table-primary">
                                ${escapeHtml(change.task_id)}
                            </span>
                        </td>

                        <td>
                            <span
                                class="
                                    impact-chip
                                    ${impactClass}
                                "
                            >
                                ${impactLabel}
                            </span>
                        </td>

                        <td>
                            ${formatDateTime(
                                change.original_start,
                            )}
                        </td>

                        <td>
                            ${formatDateTime(
                                change.revised_start,
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                change.original_block_id
                                ?? "—",
                            )}
                        </td>

                        <td>
                            ${escapeHtml(
                                change.revised_block_id
                                ?? "—",
                            )}
                        </td>

                        <td>
                            <span
                                class="
                                    classification-chip
                                    ${normalizeClass(
                                        classification,
                                    )}
                                "
                            >
                                ${escapeHtml(classification)}
                            </span>
                        </td>
                    </tr>
                `;
            })
            .join("");
    }

    byId("sandbox-result").classList.remove(
        "hidden",
    );

    byId("sandbox-result").scrollIntoView({
        behavior: "smooth",
        block: "start",
    });
}




const sandboxTrainIdsByEvent = {
    "Urgent Perishable Goods Movement":
        "PL-LIVE-PERISHABLE-001",

    "Urgent Medical Relief Goods Movement":
        "PL-MEDICAL-RELIEF-001",

    "Priority Defence Logistics Movement":
        "PL-DEFENCE-LOGISTICS-001",

    "Emergency Disaster Relief Movement":
        "PL-DISASTER-RELIEF-001",
};


function syncSandboxTrainId() {
    const eventTypeElement =
        byId("sandbox-event-type");

    const trainIdElement =
        byId("sandbox-train-id");

    const correspondingTrainId =
        sandboxTrainIdsByEvent[
            eventTypeElement.value
        ];

    if (correspondingTrainId) {
        trainIdElement.value =
            correspondingTrainId;
    }
}


async function runSandboxScenario(event) {
    event.preventDefault();
    hideError();

    const entry =
        byId("sandbox-entry").value;

    const exitTime =
        byId("sandbox-exit").value;

    if (!entry || !exitTime) {
        showError(
            "Corridor entry and exit are required.",
        );
        return;
    }

    const entryDate =
        new Date(entry);

    const exitDate =
        new Date(exitTime);

    if (exitDate <= entryDate) {
        showError(
            "Corridor exit must be after corridor entry.",
        );
        return;
    }

    const corridorDurationMinutes =
        (
            exitDate.getTime()
            - entryDate.getTime()
        ) / 60000;

    if (corridorDurationMinutes < 15) {
        showError(
            "Corridor movement must be at least "
            + "15 minutes long.",
        );
        return;
    }

    if (corridorDurationMinutes > 240) {
        showError(
            "Corridor movement cannot exceed "
            + "4 hours in this demonstration. "
            + "Check the entry and exit dates.",
        );
        return;
    }

    const payload = {
        event_type:
            byId("sandbox-event-type")
                .value
                .trim(),

        train_id:
            byId("sandbox-train-id")
                .value
                .trim(),

        corridor_entry: entry,

        corridor_exit: exitTime,

        direction:
            byId("sandbox-direction").value,

        priority: Number(
            byId("sandbox-priority").value,
        ),

        maximum_permissible_delay_minutes:
            Number(
                byId("sandbox-delay").value,
            ),

        description:
            byId("sandbox-description")
                .value
                .trim()
            || null,
    };

    const runningElement =
        byId("sandbox-running");

    const resultElement =
        byId("sandbox-result");

    const button =
        byId("run-sandbox-button");

    runningElement.classList.remove("hidden");
    resultElement.classList.add("hidden");

    button.disabled = true;
    button.textContent = "Optimizing…";

    try {
        const result = await postJson(
            "/scenario-sandbox/run",
            payload,
        );

        renderSandboxResult(result);
    } catch (error) {
        console.error(error);

        showError(
            `Scenario execution failed: `
            + error.message,
        );
    } finally {
        runningElement.classList.add("hidden");
        button.disabled = false;
        button.textContent = "Run scenario";
    }
}


function switchSection(sectionName) {
    document
        .querySelectorAll(".nav-item")
        .forEach((button) => {
            button.classList.toggle(
                "active",
                button.dataset.section
                === sectionName,
            );
        });

    document
        .querySelectorAll(".page-section")
        .forEach((section) => {
            section.classList.remove("active");
        });

    const selectedSection =
        byId(`${sectionName}-section`);

    if (selectedSection) {
        selectedSection.classList.add("active");
    }

    byId("page-title").textContent =
        pageTitles[sectionName]
        ?? "GatiPatha";
}


function bindEvents() {
    byId("sandbox-event-type").addEventListener(
        "change",
        syncSandboxTrainId,
    );

    syncSandboxTrainId();

    document
        .querySelectorAll(".nav-item")
        .forEach((button) => {
            button.addEventListener(
                "click",
                () => {
                    switchSection(
                        button.dataset.section,
                    );
                },
            );
        });

    byId(
        "planner-department-filter",
    ).addEventListener(
        "change",
        renderScheduleTable,
    );

    byId(
        "planner-section-filter",
    ).addEventListener(
        "change",
        renderScheduleTable,
    );

    byId(
        "planner-track-filter",
    ).addEventListener(
        "change",
        renderScheduleTable,
    );

    byId(
        "task-department-filter",
    ).addEventListener(
        "change",
        renderTaskTable,
    );

    byId(
        "task-priority-filter",
    ).addEventListener(
        "change",
        renderTaskTable,
    );

    byId("task-search").addEventListener(
        "input",
        renderTaskTable,
    );

    byId("approve-plan-button").addEventListener(
        "click",
        () => submitPlanDecision("approve"),
    );

    byId("reject-plan-button").addEventListener(
        "click",
        () => submitPlanDecision("reject"),
    );

    byId("reset-plan-button").addEventListener(
        "click",
        () => submitPlanDecision("reset"),
    );

    byId("lock-block-button").addEventListener(
        "click",
        () => submitBlockLock(true),
    );

    byId("unlock-block-button").addEventListener(
        "click",
        () => submitBlockLock(false),
    );

    byId("planning-horizon").addEventListener(
        "change",
        loadDashboard,
    );

    byId("refresh-button").addEventListener(
        "click",
        loadDashboard,
    );

    byId("retry-button").addEventListener(
        "click",
        loadDashboard,
    );

    byId("sandbox-form").addEventListener(
        "submit",
        runSandboxScenario,
    );
}




function getPlanningHorizon() {
    return byId("planning-horizon")?.value
        ?? "weekly";
}


function updatePlanningHorizonLabels() {
    const isMonthly =
        state.planningHorizon === "monthly";

    pageTitles.planner = isMonthly
        ? "Monthly Block Planner"
        : "Weekly Block Planner";

    const plannerButton =
        document.querySelector(
            '[data-section="planner"]',
        );

    if (plannerButton) {
        plannerButton.innerHTML =
            '<span class="nav-icon">▤</span>'
            + (
                isMonthly
                    ? "Monthly Planner"
                    : "Weekly Planner"
            );
    }

    const contextElement =
        byId("planning-context");

    if (contextElement) {
        contextElement.textContent =
            isMonthly
                ? "30-Day Multi-Corridor Plan"
                : "Pune–Lonavala Corridor";
    }

    const activeSection =
        document.querySelector(
            ".page-section.active",
        );

    if (
        activeSection
        && activeSection.id === "planner-section"
    ) {
        byId("page-title").textContent =
            pageTitles.planner;
    }
}


async function loadDashboard() {
    setLoading(true);
    hideError();

    state.planningHorizon =
        getPlanningHorizon();

    const isMonthly =
        state.planningHorizon === "monthly";

    const dashboardEndpoint =
        isMonthly
            ? "/monthly/dashboard"
            : "/dashboard";

    const taskEndpoint =
        isMonthly
            ? "/tasks?scenario=base&limit=500"
            : "/tasks?limit=500";

    const scheduleEndpoint =
        isMonthly
            ? "/monthly/schedules"
            : "/schedules/revised";

    const comparisonEndpoint =
        isMonthly
            ? "/monthly/comparison"
            : "/comparison";

    try {
        const [
            health,
            dashboard,
            taskResponse,
            scheduleResponse,
            comparisonResponse,
            disruption,
            replanning,
            approval,
        ] = await Promise.all([
            fetchJson("/health"),
            fetchJson(dashboardEndpoint),
            fetchJson(taskEndpoint),
            fetchJson(scheduleEndpoint),
            fetchJson(comparisonEndpoint),
            fetchJson("/disruption"),
            fetchJson("/replanning"),
            fetchJson(
                `/approvals?planning_horizon=${
                    state.planningHorizon
                }`,
            ),
        ]);

        state.health = health;
        state.dashboard = dashboard;
        state.tasks =
            taskResponse.tasks ?? [];

        state.schedules =
            scheduleResponse.schedules ?? [];

        state.comparison =
            comparisonResponse.changes ?? [];

        state.disruption = disruption;
        state.replanning = replanning;
        state.approval = approval;

        updatePlanningHorizonLabels();
        renderSystemHealth();
        renderOverview();
        populateSectionFilters();
        renderScheduleTable();
        renderApprovalPanel();
        renderComparisonTable();
        renderTaskTable();
        renderDisruption();
    } catch (error) {
        console.error(error);

        byId("system-status").textContent =
            "API unavailable";

        byId("system-status-dot")
            .classList
            .remove("healthy");

        byId("system-status-dot")
            .classList
            .add("unhealthy");

        showError(
            `Unable to load dashboard data: `
            + error.message,
        );
    } finally {
        setLoading(false);
    }
}


document.addEventListener(
    "DOMContentLoaded",
    () => {
        bindEvents();
        loadDashboard();
    },
);