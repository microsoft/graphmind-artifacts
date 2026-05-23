"""Synthetic incident-trace generator.

Every service, component, error family, table, host, alias, incident
number, work-item number, and failure narrative below is invented. The
two output files are pure fiction over a fixed schema.

Emits two files:

  data/incident_rca/test_input_A.json
      Long-running trace with an empty `root_cause` list and a long
      mid-sequence run of automated notifications reflecting a multi-week
      pause between the diagnostic phase and the fix-landing phase.

  data/incident_rca/test_input_B.json
      Shorter trace with denser human back-and-forth, a populated
      `root_cause` element, no long contiguous automated run, and a
      diagnostic arc that reaches an actual root cause.

Determinism: everything is driven from `SEED` (no wall-clock reads, no
process-entropy reads). Rerunning produces byte-identical files.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
SEED = 0xC0FFEE

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "incident_rca"

# All identifiers below are invented.
SERVICE = "Nimbus Ledger"
GUID_PREFIX = "00000000-0000-4000-8000-"  # visibly synthetic RFC-4122 shape

# Fictional aliases and display names. `nl-bot-sre` is the automation account.
ALIASES = {
    "nl-bot-sre":   None,
    "nl-oncall-01": "Alex Rivera",
    "nl-oncall-02": "Priya Chen",
    "nl-oncall-03": "Marcus Hoffmann",
    "nl-arch-41":   "Karim Osei",
    "nl-arch-42":   "Emeka Yusuf",
    "nl-sre-11":    "Jamie Levinson",
    "nl-dev-21":    "Sana Iqbal",
    "nl-dev-22":    "Ricardo Alves",
    "nl-dev-23":    "Miguel Santoro",
    "nl-mgr-31":    "Yuki Tanaka",
    "nl-oncall-04": "Zora Kensington",
}

# Screenshots terminator. Constant — a bare "SCREENSHOTS:" line with
# no suffix and no formatting variation.
SCREENSHOTS_TERMINATOR = "\nSCREENSHOTS:"


def sguid(n: int) -> str:
    """Deterministic synthetic-shape GUID."""
    return f"{GUID_PREFIX}{n:012x}"


def ss() -> str:
    """Return the SCREENSHOTS: terminator line (schema §8)."""
    return SCREENSHOTS_TERMINATOR


# ----------------------------------------------------------------------
# Bot state — tracks counter monotonicity and SLA firing
# ----------------------------------------------------------------------
@dataclass
class BotState:
    incident_num: str
    hours_since_human: int = 0
    hours_open: int = 0
    sla_fired: set = field(default_factory=set)
    status: str = "New"

    def human_posted(self) -> None:
        # Counter resets when a human posts (schema §7 of user's Phase-2 rules).
        self.hours_since_human = 0

    def advance(self, delta: int) -> None:
        self.hours_since_human += delta
        self.hours_open += delta


def bot_create(rng: random.Random, st: BotState, team: str, err: str,
               component: str) -> dict:
    st.status = "New"
    txt = (
        f"Incident {st.incident_num} created via automated correlation. "
        f"Owning team: {team}. Primary signal: error {err} on component "
        f"{component}." + ss()
    )
    return {"ChangedBy": "nl-bot-sre", "Text": txt}


def bot_route(rng: random.Random, st: BotState, team: str, rule: str) -> dict:
    txt = (
        f"Incident {st.incident_num} routed to team {team} by policy rule "
        f"{rule}." + ss()
    )
    return {"ChangedBy": "nl-bot-sre", "Text": txt}


def bot_periodic(rng: random.Random, st: BotState) -> dict:
    txt = (
        f"Periodic notification: incident {st.incident_num} still open. "
        f"Time since last human update: {st.hours_since_human}h." + ss()
    )
    return {"ChangedBy": "nl-bot-sre", "Text": txt}


def bot_sla(rng: random.Random, st: BotState, threshold: int) -> dict:
    st.sla_fired.add(threshold)
    txt = (
        f"SLA reminder: incident {st.incident_num} approaching {threshold}h "
        f"unmitigated threshold. Please update status." + ss()
    )
    return {"ChangedBy": "nl-bot-sre", "Text": txt}


def bot_status(rng: random.Random, st: BotState, new_status: str) -> dict:
    st.status = new_status
    txt = f"Status changed to {new_status} by policy engine." + ss()
    return {"ChangedBy": "nl-bot-sre", "Text": txt}


def bot_close_note(rng: random.Random, st: BotState) -> dict:
    txt = (
        f"Post-resolution monitoring: incident {st.incident_num} in "
        f"observation window. Hours since resolution: {st.hours_since_human}h."
        + ss()
    )
    return {"ChangedBy": "nl-bot-sre", "Text": txt}


# ----------------------------------------------------------------------
# Automated block emitters
# ----------------------------------------------------------------------
def emit_auto_gap(rng: random.Random, st: BotState, n: int,
                  step_range=(1, 3)) -> list[dict]:
    """A short automated gap between two human posts.

    Advances the "hours since last human" counter monotonically. Emits mostly
    periodic notifications. Fires SLA reminders when a threshold is crossed
    for the first time. Sprinkles occasional status oscillations.
    """
    entries: list[dict] = []
    for i in range(n):
        st.advance(rng.randint(*step_range))
        # Fire an SLA reminder if we just crossed a threshold.
        fired = None
        for t in (24, 48, 72):
            if t not in st.sla_fired and st.hours_since_human >= t:
                fired = t
                break
        if fired is not None:
            entries.append(bot_sla(rng, st, fired))
            continue
        # Small chance of a status oscillation mid-gap.
        r = rng.random()
        if r < 0.10:
            new = rng.choice(("Active", "Investigating"))
            if new != st.status:
                entries.append(bot_status(rng, st, new))
                continue
        entries.append(bot_periodic(rng, st))
    return entries


def emit_auto_long_run(rng: random.Random, st: BotState, n: int) -> list[dict]:
    """The multi-week silent period in story A.

    Counter climbs into the low hundreds of hours. All three SLA thresholds
    (24h, 48h, 72h) fire in order. Status oscillates between Investigating
    and Active a handful of times to reflect an incident that keeps being
    poked by the policy engine without a human update.
    """
    entries: list[dict] = []
    for i in range(n):
        # Vary the step so the counter rises unevenly.
        step = rng.choice((1, 2, 2, 3, 3, 4, 5, 6, 8))
        st.advance(step)
        # Fire the next SLA threshold if crossed.
        fired = None
        for t in (24, 48, 72):
            if t not in st.sla_fired and st.hours_since_human >= t:
                fired = t
                break
        if fired is not None:
            entries.append(bot_sla(rng, st, fired))
            continue
        # Roughly one entry in eight is a status oscillation.
        if rng.random() < 0.12:
            new = rng.choice(("Investigating", "Active", "Investigating"))
            if new != st.status:
                entries.append(bot_status(rng, st, new))
                continue
        entries.append(bot_periodic(rng, st))
    return entries


def emit_auto_tail(rng: random.Random, st: BotState, n: int) -> list[dict]:
    """Trailing automated block after the final human closure.

    Counter starts near zero and rises monotonically. Contains a single
    Resolved -> Closed status transition and a mix of post-resolution
    monitoring notes.
    """
    entries: list[dict] = []
    # Force one Resolved status change in the first quarter of the tail.
    resolved_at = max(1, n // 4)
    closed_at = max(resolved_at + 1, (3 * n) // 4)
    for i in range(n):
        st.advance(rng.choice((1, 2, 2, 3, 3, 4)))
        if i == resolved_at:
            entries.append(bot_status(rng, st, "Resolved"))
            continue
        if i == closed_at:
            entries.append(bot_status(rng, st, "Closed"))
            continue
        entries.append(bot_close_note(rng, st))
    return entries


# ----------------------------------------------------------------------
# Hand-authored human beats (each used at most once per file)
# ----------------------------------------------------------------------
# Each beat is (author_alias, text, refs).
#   - `refs` = list of prior human-beat indices this one responds to.
#   - The first beat may have an empty refs list (it responds to the
#     incident creation).
#   - Beat texts differ in length, register, signoff style, and format
#     (some are queries, some pastes, some terse acks, some prose).
#
# NO TEMPLATES. Each text below is written once.

# ---------- Story A: recurring lease-renewal oscillation --------------
A_INCIDENT = "999000001"
A_TEAM = "nl-sre-primary"
A_HUMANS: list[tuple[str, str, list[int]]] = [
    # 0 — first responder posts a symptom and initial telemetry reading.
    (
        "nl-oncall-01",
        "Alex here — picking this up. Two NLX-4207 bursts in the last 30 "
        "min, both around 4 minutes long, both cleared before the pager "
        "even hit my phone. Grabbing lease-manager logs on "
        "lease-17.eastus.nimbus-ledger.example.net while they're still "
        "warm. Will post an initial read within the hour.",
        [],
    ),
    # 1 — second responder proposes a cause and cites specific evidence.
    (
        "nl-oncall-02",
        "@nl-oncall-01 lease-manager peer clock offset in westus is 640ms "
        "right now. That's higher than anything I've seen this cluster "
        "do. My reading: primary election is thrashing between two "
        "candidate replicas whenever a renewal packet misses the 800ms "
        "deadline. Pulling nl_lease_events grouped by candidate_id for "
        "the last 6h to check.",
        [0],
    ),
    # 2 — canary/config change based on the hypothesis in beat 1.
    (
        "nl-oncall-02",
        "Rolling a 5% canary on lease-manager in westus with "
        "renewal_timeout bumped from 800ms to 1200ms. If the peer-offset "
        "theory is right, this should silence NLX-4207 on the canary "
        "group without touching the other regions. Reporting in 40 min. "
        "Not proposing this as a fix — 1200ms means writes stall 400ms "
        "longer under any real delay — I want a diagnostic window.",
        [1],
    ),
    # 3 — the RESULT of the canary change is reported. Partial improvement.
    (
        "nl-oncall-02",
        "40-min update on the westus canary. NLX-4207 rate on the canary "
        "group: 0 for the whole window. NLX-4207 rate on the non-canary "
        "group: unchanged, still peaking around 90/min. So the timeout "
        "bump works locally but it's a symptom mask, not a fix. Reverting "
        "the canary now and handing back to the room.",
        [2],
    ),
    # 4 — disagreement with beat 1's hypothesis, by name.
    (
        "nl-arch-41",
        "I don't buy Priya's 800ms threshold story. I pulled the "
        "peer-offset history back to February and westus has sat above "
        "600ms plenty of times without triggering any of this. The "
        "trigger has to be something else. My guess is a change on the "
        "write-coordinator side. Reading the deploy log now.",
        [1],
    ),
    # 5 — a query paste, unsigned, lowercase, terse.
    (
        "nl-mgr-31",
        "quick pull:\n"
        "```\n"
        "nl_lease_events\n"
        "| where err_code == 'NLX-4207'\n"
        "| where TIMESTAMP > ago(24h)\n"
        "| summarize count() by region\n"
        "```\n"
        "westus 4102, northeu 3980, eastus 0, southasia 12. eastus is "
        "completely clean. anyone know what's different about eastus.",
        [4],
    ),
    # 6 — @-mention that connects two threads and pinpoints the change.
    (
        "nl-dev-22",
        "@nl-arch-41 to your point: write-coordinator on eastus is still "
        "on build 8814. Everywhere else went to 8901 two weeks ago. If "
        "your instinct is right, the trigger is in the 8901 diff.",
        [4, 5],
    ),
    # 7 — pushback / alternative hypothesis, no signoff, lowercase.
    (
        "nl-sre-11",
        "before we blame 8901: eastus takes maybe 40% of the traffic "
        "northeu takes. lower load could easily be why we're not seeing "
        "the oscillation there. i want eastus deliberately loaded to "
        "peer-region rate before we call it a build regression.",
        [6],
    ),
    # 8 — experiment that answers the challenge.
    (
        "nl-sre-11",
        "Loaded eastus to peer-region rate for 90 min starting 14:00 "
        "UTC. NLX-4207 on eastus: 0 across the whole window. NLX-4210 "
        "same. So it isn't load-driven. Handing back to WCoord team to "
        "look at the 8901 diff on their side.",
        [7, 6],
    ),
    # --- long silent period of automated notifications goes here ------
    # 9 — terse restart after the silent period; proposes controlled revert.
    (
        "nl-oncall-03",
        "ok. picking this back up. WCoord team came back after their "
        "read of the 8901 diff. plan: revert eastus to 8901 and see the "
        "oscillation on eastus for the first time. if we see it, the "
        "diff is real and we file it against WCoord as a build "
        "regression.",
        [8, 6],
    ),
    # 10 — fix (revert) lands and is referenced by a work-item number.
    (
        "nl-oncall-04",
        "Rolled eastus back to 8901 at 16:12 UTC. First 4 hours on "
        "eastus: 47 NLX-4207 bursts, shape matches westus and northeu. "
        "So the regression is real and it's in 8901. Filed against the "
        "write-coordinator team as work item 9990000021. They own the "
        "follow-up.",
        [9],
    ),
    # 11 — long diagnostic summary (this is the long-form entry for A;
    # ~4.5 KB, single beat: timeline, metrics, rejected hypotheses,
    # runbook steps, dashboards, handoff notes, and the residual
    # argument that keeps root_cause empty on this ticket).
    (
        "nl-arch-41",
        "Karim: writing this up because we've been at it long enough "
        "that I want the timeline in one place for anyone coming to this "
        "cold.\n"
        "\n"
        "Rough timeline (all times UTC, all relative to open):\n"
        "  t+00h   Alex picks up on two short NLX-4207 bursts, both "
        "self-cleared before paging arrived. First reading is on the "
        "westus lease-manager pool.\n"
        "  t+02h   Priya's peer-clock-offset hypothesis is posted "
        "(claim: 800ms deadline is the trigger).\n"
        "  t+04h   Priya's 5% canary bumps renewal_timeout to 1200ms on "
        "lease-manager in westus. NLX-4207 goes to zero on the canary "
        "group only. Canary reverted 40 min in.\n"
        "  t+05h   I pushed back on the 800ms story. Offset history "
        "doesn't support it. Deploy log shows 8901 rolled two weeks ago "
        "on write-coordinator to all regions except eastus.\n"
        "  t+05h   Yuki pulled the per-region NLX-4207 counts and "
        "flagged eastus as suspiciously clean.\n"
        "  t+07h   Ricardo confirmed the build gap: eastus on 8814, "
        "everyone else on 8901.\n"
        "  t+08h   Jamie's counterpoint: eastus is a lower-traffic "
        "region, could be load not build.\n"
        "  t+09h   Jamie loaded eastus to peer-region rate for 90 min. "
        "NLX-4207 stayed at 0. So it isn't load.\n"
        "  t+11h   Handed off to the write-coordinator team for their "
        "read on the 8901 diff.\n"
        "  t+11h..t+18d   Silent period on our side. WCoord team's read: "
        "a single change to the renewal-ack path in 8901 reorders the "
        "renewal-received callback against the primary-election callback "
        "under contention.\n"
        "  t+18d   Zora (fresh oncall rotation) reverted eastus to 8901 "
        "for a controlled confirmation. NLX-4207 pattern on eastus "
        "reproduced within 4h. Filed 9990000021 against WCoord.\n"
        "  t+19d   Fix commit lands as 9901 (targeted revert of the "
        "reordering change) and rolls to all regions overnight.\n"
        "  t+19d   NLX-4207 drops to baseline in westus, eastus, "
        "northeu.\n"
        "\n"
        "What's still open:\n"
        "  Southasia is NOT clean. It has a low-rate NLX-4207 stream "
        "that predates 8901 entirely — I pulled the offset table back "
        "past the 8901 rollout and southasia had the same trickle then. "
        "So southasia is a separate failure mode wearing the same error "
        "code. Its bursts are ~10x smaller, don't correlate with "
        "renewal-packet timing, and look correlated with shard placement "
        "drift instead.\n"
        "\n"
        "Metrics reference (all pulled from the nl_lease_events "
        "dashboard, 24h window ending at t+19d):\n"
        "  - westus NLX-4207 rate: baseline 0.2/s, peak 210/s during "
        "storms.\n"
        "  - northeu NLX-4207 rate: baseline 0.3/s, peak 197/s during "
        "storms.\n"
        "  - eastus NLX-4207 rate before revert: 0/s. After revert: "
        "peak 84/s within 4h, matching westus and northeu shape.\n"
        "  - southasia NLX-4207 rate (persistent trickle): baseline "
        "4/s, peak 11/s during unrelated shard rebalances. Never "
        "crosses the 40/s threshold that the primary regions crossed.\n"
        "  - Peer clock offset in the westus lease-manager pool: "
        "sustained above 500ms for the whole incident duration. Never "
        "below 400ms.\n"
        "\n"
        "Hypotheses we tested and ruled out along the way:\n"
        "  - Renewal-timeout hard limit is the trigger (Priya's "
        "original read): ruled out by peer-offset history predating "
        "this incident with no corresponding NLX-4207 spikes.\n"
        "  - Load-driven placement drift: ruled out by Jamie's "
        "controlled eastus load test at t+09h.\n"
        "  - Bad routing rule: WCoord team confirmed NL-ROUTING-07 has "
        "not changed in 60 days.\n"
        "  - Corrupt lease-manager state on one region: ruled out by "
        "uniform NLX-4207 shape across westus and northeu after the "
        "eastus revert.\n"
        "\n"
        "Runbook steps applied during the trace:\n"
        "  - Step 4 (drain a lease-manager replica while peers "
        "converge): applied twice, no effect on aggregate rate.\n"
        "  - Step 7 (roll renewal_timeout up temporarily): applied as "
        "Priya's diagnostic canary at t+04h only, never as a "
        "mitigation.\n"
        "  - Step 9 (revert last write-coordinator build in affected "
        "region): the actual mitigation, applied as 9901 across all "
        "four regions overnight at t+18d.\n"
        "\n"
        "Dashboards touched during investigation:\n"
        "  - "
        "https://dashboards.nimbus-ledger.example.com/incident/999000001\n"
        "  - "
        "https://dashboards.nimbus-ledger.example.com/lease-oscillation-detail\n"
        "  - "
        "https://dashboards.nimbus-ledger.example.net/southasia-placement-drift\n"
        "\n"
        "Handoff notes for whoever picks up 9990000029 (southasia "
        "residual):\n"
        "  1. Do not treat lease renewal timing as the primary metric "
        "there. The signal in southasia is shard placement drift, not "
        "renewal.\n"
        "  2. Look at nl_shard_placement_events grouped by "
        "tenant_hash. There is a small population of tenants whose "
        "primary shard replicates to a placement that has been "
        "marginal for months.\n"
        "  3. Southasia p99 latency does not correlate with global "
        "NLX-4207 rate. Do a separate correlation.\n"
        "  4. Do not wait on the WCoord team; they own 9901, not "
        "9990000029. Southasia is a placement-service problem, not a "
        "build regression.\n"
        "\n"
        "Recommendation:\n"
        "  - Mark this incident mitigated on the 9901 rollout.\n"
        "  - 9901 is a fix for the write-coordinator regression. It "
        "explains the westus, northeu, and (post-revert) eastus "
        "behavior. It does not explain southasia.\n"
        "  - Split the southasia residual out to 9990000029 so it "
        "gets a proper RCA against the placement service. Its "
        "cause is in placement, not in the write-coordinator diff.\n"
        "\n"
        "Bottom line: what this ticket was opened for — 'recurring "
        "lease-renewal oscillation' — is two failures wearing the "
        "same error code, and they live in different services. One "
        "of them (the primary-region one) is now fixed. The other "
        "is still open and belongs on 9990000029, where the "
        "placement-service team can diagnose it against their "
        "signals.",
        [10, 8, 4],
    ),
    # 12 — mitigation confirmation, referencing beat 11's call.
    (
        "nl-dev-23",
        "9901 shipped to all regions overnight. NLX-4207 rate on "
        "westus, eastus, northeu dropped to baseline within 20 minutes "
        "of the rollout. Southasia still elevated, as Karim called out "
        "in the summary. Marking mitigated. Keeping this incident open "
        "on the southasia residual only.",
        [11],
    ),
    # 13 — final closure. Explains why this ticket has no single cause
    # to write down: the southasia residual is a different failure.
    (
        "nl-arch-42",
        "Closing this incident. The southasia residual is real but its "
        "shape is different: bursts are ~10x smaller and don't "
        "correlate with renewal-packet timing at all. Splitting it out "
        "to work item 9990000029 so it gets a proper RCA against the "
        "placement service. This ticket closes on the 9901 rollout — "
        "the primary-region oscillation is what we were paged for and "
        "that is mitigated. The southasia diagnosis belongs on the "
        "placement-service ticket, not here.",
        [12, 11],
    ),
    # 14 — SHARED platform-triage beat. Wording matches the parallel
    # beat in B_HUMANS so that extraction yields near-identical action
    # labels across the two incidents and clustering merges them.
    (
        "nl-oncall-01",
        "First-line triage — pulled the platform-wide regional health "
        "dashboard "
        "https://dashboards.nimbus-ledger.example.com/platform/regional-health "
        "to check whether any peer team is seeing correlated signal. "
        "Nothing anomalous outside our own NLX-4207 trace.",
        [0],
    ),
    # 15 — SHARED platform-triage beat #2 (AQL). Parallels B_HUMANS.
    (
        "nl-oncall-01",
        "Ran the platform-wide incident-events cross-region query:\n"
        "```\n"
        "nl_incident_events\n"
        "| where TIMESTAMP > ago(24h)\n"
        "| summarize count() by region, err_code\n"
        "```\n"
        "only our own err_code shows up in the top-10. no cross-team "
        "correlation.",
        [14],
    ),
]


# ---------- Story B: publish-queue saturation from mis-merged config PR
B_INCIDENT = "999000002"
B_TEAM = "nl-publish-primary"
B_HUMANS: list[tuple[str, str, list[int]]] = [
    # 0 — initial symptom + telemetry
    (
        "nl-oncall-02",
        "Publish rate on northeu topic-registry dropped ~40% at 09:14 "
        "UTC. NLX-3301 (publish quota exceeded) climbed from ~1/s "
        "baseline to ~200/s. No deploys in the last 12h per the deploy "
        "log. Looking at quota-broker.",
        [],
    ),
    # 1 — cause hypothesis with evidence, @-mention
    (
        "nl-dev-21",
        "@nl-oncall-02 quota-broker is reporting zero refills for topic "
        "ledger-events-primary since 09:00 UTC. Every other topic is "
        "refilling normally. So this isn't a broker-wide outage, it's "
        "per-topic. Something specific to that topic's quota row.",
        [0],
    ),
    # 2 — direct probe
    (
        "nl-dev-21",
        "Hit the quota-broker admin API on "
        "quota-01.northeu.nimbus-ledger.example.net directly. "
        "topic=ledger-events-primary refill_rate is 0. Config-db "
        "snapshot from an hour ago has it at 5000/s. Something zeroed "
        "it in the last hour. Checking the audit log.",
        [1],
    ),
    # 3 — probe result — pinpoints the agent that wrote the zero
    (
        "nl-dev-21",
        "Audit log: the quota row for ledger-events-primary was written "
        "at 08:57:04 UTC by service account nl-config-sync-bot. That's "
        "the scheduled config sync. So the config db already had "
        "refill_rate=0 for that row when the sync ran. The bot did what "
        "it was told.",
        [2],
    ),
    # 4 — disagreement with beat 3's conclusion, by name
    (
        "nl-arch-41",
        "Hold on. Config db is supposed to be immutable at rest during "
        "ops hours. Either that assumption is wrong or the sync bot "
        "pulled the wrong file. Want to see what the sync bot actually "
        "read before we accept Sana's audit-log story.",
        [3],
    ),
    # 5 — log paste, sloppy, lowercase
    (
        "nl-oncall-04",
        "sync bot log:\n"
        "```\n"
        "[08:57:04.101] pulling s3://nl-config/topics/prod/northeu.yaml\n"
        "[08:57:04.334] parsed 2141 rows\n"
        "[08:57:05.012] applied 2141 rows OK\n"
        "```\n"
        "file size 412KB. can diff s3 against 24h ago.",
        [4],
    ),
    # 6 — diff paste (long-form for B; includes surrounding YAML,
    # PR title/body, approvals trail, CODEOWNERS drift, and the
    # nightly-promotion timing that beat the aspirational revert).
    (
        "nl-dev-21",
        "Diffed the s3 object against 24h ago. The relevant hunk in "
        "topics/prod/northeu.yaml:\n"
        "```\n"
        "topics:\n"
        "   ledger-events-primary:\n"
        "-    refill_rate: 5000\n"
        "+    refill_rate: 0\n"
        "     burst: 20000\n"
        "     window_ms: 1000\n"
        "     hot_partitions:\n"
        "       - shard-07\n"
        "       - shard-11\n"
        "       - shard-24\n"
        "     backpressure_policy: reject-newest\n"
        "     alert_owner: nl-publish-primary\n"
        "```\n"
        "PR #4429 in the nl-config/topics-prod repo. Title: "
        "'ledger-events-primary: align refill schedule with "
        "onboarding-tooling test harness'. Body (paraphrased):\n"
        "---\n"
        "Onboarding tooling test harness uses a mocked broker that "
        "returns quota-denied on refill_rate=0 for the primary topic "
        "to simulate backpressure paths. Setting refill_rate to 0 in "
        "the shared config lets the harness exercise the same code "
        "path against the real broker during CI dry runs. Will be "
        "reverted before nightly promotion.\n"
        "---\n"
        "Committed by rowan.boateng@example.com at 08:52 UTC. "
        "Approved by one reviewer (auto-approved by "
        "nl-onboarding-tooling-approver). NOT approved by "
        "nl-config-review, which is supposed to be a required "
        "reviewer on topics/prod/*.yaml — the CODEOWNERS entry that "
        "should have enforced that was pinned to a stale team ID. "
        "Filed a follow-up on the CODEOWNERS drift as work item "
        "9990000039.\n"
        "Note: the PR body's 'reverted before nightly promotion' "
        "language was aspirational, not enforced. The promotion job "
        "ran at 08:57 UTC, five minutes after merge.",
        [5],
    ),
    # 7 — one-liner conclusion, unsigned, lowercase
    (
        "nl-arch-41",
        "so this is not an infra bug. this is a mis-merged PR.",
        [6],
    ),
    # 8 — mitigation attempt with a work-item number
    (
        "nl-oncall-02",
        "Reverting PR #4429 and re-running the config sync manually "
        "with the previous YAML. Manual sync tracked as work item "
        "9990000034. Reverting first, verifying broker second, then "
        "unblocking publishers.",
        [7],
    ),
    # 9 — partial result of the mitigation
    (
        "nl-sre-11",
        "Manual sync ran at 10:22 UTC. quota-broker shows "
        "refill_rate=5000 for ledger-events-primary. NLX-3301 rate on "
        "northeu is down to ~3/s and dropping. Publishers with "
        "backpressure are draining. Not baseline yet — the retry queue "
        "is still working through its backlog.",
        [8],
    ),
    # 10 — residual case identified from re-reading the diff
    (
        "nl-arch-41",
        "@nl-oncall-02 heads up: PR #4429 touched two other rows I saw "
        "in the diff before it got closed. northeu-audit-trail went "
        "from refill_rate=800 to 100. That's most likely the source of "
        "the trickle of NLX-3301 we're still seeing on that topic.",
        [9, 6],
    ),
    # 11 — second fix landing, with work item
    (
        "nl-dev-22",
        "PR #4432 restores northeu-audit-trail to refill_rate=800 and "
        "adds a schema comment on both rows so this doesn't happen "
        "again quietly. Running the config sync a second time to pick "
        "it up. Second sync tracked as work item 9990000037.",
        [10],
    ),
    # 12 — confirmation the fix worked (temporarily)
    (
        "nl-mgr-31",
        "Second sync at 11:04 UTC. NLX-3301 rate on northeu at ~1/s "
        "baseline. Publish rate on ledger-events-primary and "
        "northeu-audit-trail recovered to normal. Marking mitigated.",
        [11],
    ),
    # 13 — the fix does NOT fully hold — reappearance reported and reasoned.
    # References the overnight quiet stretch that fires the 24h SLA.
    (
        "nl-arch-42",
        "Picking this back up. Overnight was quiet on the ticket — the "
        "page never re-fired — but NLX-3301 came back on northeu at "
        "12:11 UTC (day 2 of the incident). Low rate but real. "
        "ledger-events-primary again. Broker refill_rate is still "
        "5000, so the config side hasn't regressed. Reading the "
        "metrics: the retry queue that sits in front of the broker is "
        "still draining backpressure from yesterday's stall and "
        "periodically punches through the 20000 burst boundary. "
        "Watching, don't think we need to intervene.",
        [12],
    ),
    # 14 — root cause finalized (day 2)
    (
        "nl-arch-41",
        "12:47 UTC (day 2) — retry queue drained. NLX-3301 back to 0/s "
        "baseline on northeu. Confirmed root cause: PR #4429 "
        "(onboarding-tooling change) zeroed refill_rate on two topics "
        "in topics/prod/northeu.yaml. The scheduled config sync then "
        "propagated the zero to the quota broker. Merged without "
        "required config-review approval.",
        [13, 6],
    ),
    # 15 — resolution with follow-up work items
    (
        "nl-oncall-02",
        "Closing. Root cause recorded on this ticket. Follow-ups: "
        "(1) work item 9990000041 adds a validator that rejects "
        "refill_rate=0 in topics/prod/*.yaml without an explicit "
        "deprecation flag; (2) work item 9990000042 requires "
        "config-review approval on any PR touching topics/prod/*.yaml "
        "before it can merge.",
        [14],
    ),
    # 16 — SHARED platform-triage beat. Wording matches the parallel
    # beat in A_HUMANS so that extraction yields near-identical action
    # labels across the two incidents and clustering merges them.
    (
        "nl-oncall-02",
        "First-line triage — pulled the platform-wide regional health "
        "dashboard "
        "https://dashboards.nimbus-ledger.example.com/platform/regional-health "
        "to check whether any peer team is seeing correlated signal. "
        "Nothing anomalous outside our own NLX-3301 trace.",
        [0],
    ),
    # 17 — SHARED platform-triage beat #2 (AQL). Parallels A_HUMANS.
    (
        "nl-oncall-02",
        "Ran the platform-wide incident-events cross-region query:\n"
        "```\n"
        "nl_incident_events\n"
        "| where TIMESTAMP > ago(24h)\n"
        "| summarize count() by region, err_code\n"
        "```\n"
        "only our own err_code shows up in the top-10. no cross-team "
        "correlation.",
        [16],
    ),
]


# ----------------------------------------------------------------------
# Interleave plans
# ----------------------------------------------------------------------
# Plan grammar:
#   ("create",)                              — bot creation entry
#   ("route",)                               — bot routing entry
#   ("h", i)                                 — human beat #i
#   ("gap", n)                               — n automated entries (short gap)
#   ("wide_gap", n)                          — n automated entries with wider
#                                              per-entry hours; used to make
#                                              a stretch cross an SLA threshold
#   ("long_run", n)                          — n-entry mid-sequence auto run
#   ("tail", n)                              — n-entry post-close auto tail
A_PLAN: list[tuple] = [
    ("create",),
    ("route",),
    ("h", 0),
    # Shared platform-triage beats. Placed early so they read as
    # first-response actions, not late investigative ones.
    ("h", 14),
    ("h", 15),
    ("gap", 2),
    ("h", 1),
    ("h", 2),
    ("gap", 2),
    ("h", 3),
    ("gap", 2),
    ("h", 4),
    ("h", 5),
    ("gap", 2),
    ("h", 6),
    ("gap", 2),
    ("h", 7),
    ("h", 8),
    ("long_run", 70),
    ("h", 9),
    ("gap", 1),
    ("h", 10),
    ("gap", 1),
    ("h", 11),
    ("gap", 1),
    ("h", 12),
    ("gap", 2),
    ("h", 13),
    ("tail", 22),
]

B_PLAN: list[tuple] = [
    ("create",),
    ("route",),
    ("h", 0),
    ("gap", 1),
    ("h", 1),
    ("gap", 0),
    ("h", 2),
    ("gap", 0),
    ("h", 3),
    ("gap", 1),
    ("h", 4),
    ("gap", 0),
    ("h", 5),
    ("gap", 1),
    ("h", 6),
    ("gap", 0),
    ("h", 7),
    ("gap", 1),
    ("h", 8),
    ("gap", 2),
    ("h", 9),
    ("gap", 1),
    ("h", 10),
    ("gap", 0),
    ("h", 11),
    ("gap", 1),
    ("h", 12),
    ("wide_gap", 14),
    ("h", 13),
    ("gap", 0),
    ("h", 14),
    # Shared platform-triage beats. Placed in the late-timeline chunk so
    # they land in a chunk that would otherwise extract 0 actions, rather
    # than crowding out the mid-incident diff/mitigation actions.
    ("h", 16),
    ("h", 17),
    ("gap", 0),
    ("h", 15),
    ("tail", 4),
]


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------
@dataclass
class RenderContext:
    incident_num: str
    team: str
    primary_err: str
    primary_component: str
    routing_rule: str
    humans: list[tuple[str, str, list[int]]]
    plan: list[tuple]


def render_communications(rng: random.Random,
                          ctx: RenderContext) -> tuple[list[dict], list[int]]:
    """Return (communications list, indices of human entries in that list)."""
    st = BotState(incident_num=ctx.incident_num)
    entries: list[dict] = []
    human_positions: list[int] = []

    for step in ctx.plan:
        kind = step[0]
        if kind == "create":
            entries.append(bot_create(rng, st, ctx.team,
                                      ctx.primary_err, ctx.primary_component))
            st.advance(1)
        elif kind == "route":
            entries.append(bot_route(rng, st, ctx.team, ctx.routing_rule))
            st.advance(1)
        elif kind == "h":
            idx = step[1]
            author, text, _refs = ctx.humans[idx]
            entries.append({"ChangedBy": author, "Text": text + ss()})
            human_positions.append(len(entries) - 1)
            st.human_posted()
        elif kind == "gap":
            entries.extend(emit_auto_gap(rng, st, step[1]))
        elif kind == "wide_gap":
            # Overnight-quiet stretch: wider per-entry step so the
            # 24h SLA threshold is reliably crossed.
            entries.extend(emit_auto_gap(rng, st, step[1], step_range=(2, 3)))
        elif kind == "long_run":
            entries.extend(emit_auto_long_run(rng, st, step[1]))
        elif kind == "tail":
            entries.extend(emit_auto_tail(rng, st, step[1]))
        else:
            raise ValueError(f"unknown plan step: {step!r}")
    return entries, human_positions


def build_A(rng: random.Random) -> tuple[dict, list[int]]:
    ctx = RenderContext(
        incident_num=A_INCIDENT,
        team=A_TEAM,
        primary_err="NLX-4207",
        primary_component="lease-manager",
        routing_rule="NL-ROUTING-07",
        humans=A_HUMANS,
        plan=A_PLAN,
    )
    comms, hpos = render_communications(rng, ctx)
    inner = {
        "title": (
            "[Nimbus Ledger] Recurring lease-renewal oscillation causing "
            "periodic write-path stalls in write-coordinator across regions"
        ),
        "summary": (
            "Incident 999000001 tracks a long-running, intermittent "
            "lease-renewal oscillation in the Nimbus Ledger write path.\n"
            "The failure surfaces as bursts of NLX-4207 (lease renewal "
            "timeout) followed by NLX-4210 (stale primary) on the "
            "write-coordinator, correlated with a sharp rise in p99 write "
            "latency lasting 3-30 minutes at a time.\n"
            "\n"
            "Impact:\n"
            "  - Customer-visible writes queue for up to 30s per burst.\n"
            "  - No data loss observed.\n"
            "  - Automatic self-recovery once one of the candidate primaries "
            "wins the lease election cleanly.\n"
            "\n"
            "Why this incident stayed open so long:\n"
            "  - Root cause was not isolated until several weeks into the "
            "trace. We had working hypotheses (renewal-delay-driven "
            "oscillation) but no reproducer.\n"
            "  - Mitigations reduced blast radius but did not eliminate "
            "recurrence.\n"
            "\n"
            "Regions affected (rolling): westus, eastus, northeu, southasia.\n"
            "\n"
            "See dashboard: "
            "https://dashboards.nimbus-ledger.example.com/incident/999000001\n"
            "Runbook: "
            "https://runbooks.nimbus-ledger.example.net/lease-renewal\n"
            "\n"
            "Related work items:\n"
            "  - Work item 9990000021: revert of the 8901 renewal-ack "
            "reordering change.\n"
            "  - Work item 9990000029: separate investigation of the "
            "southasia residual pattern.\n"
        ),
        "communications": comms,
        "root_cause": [],
        "tsg": "",
    }
    doc = {
        "raw": json.dumps(inner, separators=(", ", ": "), ensure_ascii=False),
        "metadata": {
            "title": inner["title"],
            "create_date": "2024-02-03T14:22:11.500000Z",
            "resolve_date": "2024-02-22T20:14:38.720000Z",
            "incident_type": "LiveSite",
            "owning_team": A_TEAM,
            "responsible_individual": "nl-sre-11",
            "base64_strings": [],
        },
    }
    return doc, hpos


def build_B(rng: random.Random) -> tuple[dict, list[int]]:
    ctx = RenderContext(
        incident_num=B_INCIDENT,
        team=B_TEAM,
        primary_err="NLX-3301",
        primary_component="quota-broker",
        routing_rule="NL-ROUTING-14",
        humans=B_HUMANS,
        plan=B_PLAN,
    )
    comms, hpos = render_communications(rng, ctx)
    inner = {
        "title": (
            "[Nimbus Ledger] Publish-path quota exhaustion on northeu topic "
            "ledger-events-primary caused by mis-merged config PR #4429"
        ),
        "summary": (
            "Incident 999000002 tracks a publish-path outage on the Nimbus "
            "Ledger northeu region.\n"
            "\n"
            "Symptom: NLX-3301 (publish quota exceeded) climbed from ~1/s "
            "baseline to ~200/s starting 09:14 UTC. Publishers on topic "
            "ledger-events-primary experienced backpressure and, in a "
            "smaller number of cases, dropped messages after their local "
            "retry budgets were exhausted.\n"
            "\n"
            "Root cause was isolated during the same session and is "
            "recorded on this ticket.\n"
            "\n"
            "See dashboard: "
            "https://dashboards.nimbus-ledger.example.com/incident/999000002\n"
            "Runbook: "
            "https://runbooks.nimbus-ledger.example.net/quota-refill\n"
            "\n"
            "Related work items:\n"
            "  - Work item 9990000034: manual config sync recovering the "
            "primary topic refill rate.\n"
            "  - Work item 9990000037: second manual sync recovering the "
            "audit-trail topic refill rate.\n"
            "  - Work item 9990000041: schema validator rejecting "
            "refill_rate=0 without an explicit deprecation flag.\n"
            "  - Work item 9990000042: config-review approval gate on "
            "topics/prod/*.yaml PRs.\n"
        ),
        "communications": comms,
        "root_cause": [
            {
                "RootCauseId": 8842001,
                "RootCauseId1": 8842019,
                "Category": "Configuration",
                "SubCategory": "",
                "IsCausedByChange": True,
                "Description": (
                    "Mis-merged PR #4429 zeroed refill_rate on two "
                    "topics/prod/northeu.yaml rows; propagated to broker."
                ),
            }
        ],
        "tsg": "",
    }
    doc = {
        "raw": json.dumps(inner, separators=(", ", ": "), ensure_ascii=False),
        "metadata": {
            "title": inner["title"],
            "create_date": "2024-07-16T09:14:02.410000Z",
            "resolve_date": "2024-07-17T14:22:07.180000Z",
            "incident_type": "LiveSite",
            "owning_team": B_TEAM,
            "responsible_individual": "nl-oncall-02",
            "base64_strings": [],
        },
    }
    return doc, hpos


# ----------------------------------------------------------------------
# Self-check
# ----------------------------------------------------------------------
def _human_only_signal(text: str) -> str:
    """Strip the SCREENSHOTS: terminator line and any URLs before comparing
    human entries for content repetition."""
    # Drop the terminator line.
    if "\nSCREENSHOTS:" in text:
        text = text.split("\nSCREENSHOTS:", 1)[0]
    # Drop URLs.
    import re as _re
    text = _re.sub(r"https?://\S+", "", text)
    return text


def _longest_common_substring(a: str, b: str) -> str:
    """Straightforward O(n*m) longest common substring."""
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return ""
    # Roll rows to keep memory reasonable.
    prev = [0] * (m + 1)
    curr = [0] * (m + 1)
    best_end = 0
    best_len = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > best_len:
                    best_len = curr[j]
                    best_end = i
            else:
                curr[j] = 0
        prev, curr = curr, prev
        for j in range(m + 1):
            curr[j] = 0
    return a[best_end - best_len:best_end]


def _longest_repeat_across_humans(entries: list[dict],
                                  human_positions: list[int]) -> str:
    """Return the longest substring that appears in two DIFFERENT human
    entries (after stripping the SCREENSHOTS terminator and URLs)."""
    texts = [_human_only_signal(entries[p]["Text"]) for p in human_positions]
    best = ""
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            lcs = _longest_common_substring(texts[i], texts[j])
            if len(lcs) > len(best):
                best = lcs
    return best


def _monotonic_tail_ok(entries: list[dict],
                       human_positions: list[int]) -> tuple[bool, list[int]]:
    """Verify that the "hours since last human update" counter in the
    trailing automated block after the FINAL human entry is monotonically
    non-decreasing.

    We look at both `Periodic notification: ... Time since last human update: Xh`
    lines and the `Post-resolution monitoring: ... Hours since resolution: Xh`
    lines emitted by the tail helper.

    Also verify monotonicity within EVERY automated gap between two human
    posts.
    """
    import re as _re
    hours_re = _re.compile(
        r"(?:Time since last human update|Hours since resolution): (\d+)h"
    )
    # Trailing tail
    last_h = human_positions[-1]
    tail_hours: list[int] = []
    for e in entries[last_h + 1:]:
        m = hours_re.search(e["Text"])
        if m:
            tail_hours.append(int(m.group(1)))
    is_mono_tail = all(tail_hours[i] <= tail_hours[i + 1]
                       for i in range(len(tail_hours) - 1))
    # Inter-human gaps
    boundaries = [-1] + human_positions + [len(entries)]
    bad_gaps = 0
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        gap_hours = []
        for e in entries[start + 1:end]:
            m = hours_re.search(e["Text"])
            if m:
                gap_hours.append(int(m.group(1)))
        for i in range(len(gap_hours) - 1):
            if gap_hours[i] > gap_hours[i + 1]:
                bad_gaps += 1
                break
    return is_mono_tail and bad_gaps == 0, tail_hours


def selfcheck(name: str, doc: dict, human_positions: list[int],
              humans_spec: list[tuple[str, str, list[int]]]) -> None:
    print(f"\n================ Self-check: {name} ================")
    inner = json.loads(doc["raw"])
    comms = inner["communications"]
    print(f"total entries:                         {len(comms)}")
    print(f"human entries:                         {len(human_positions)}")
    auto = len(comms) - len(human_positions)
    print(f"automated entries:                     {auto}")
    print(f"automation ratio:                      "
          f"{auto / len(comms):.2%}")
    sla_fired = sum(1 for e in comms if "SLA reminder" in e["Text"])
    print(f"SLA reminders fired:                   {sla_fired}")
    unique_authors = sorted({e['ChangedBy'] for e in comms})
    print(f"distinct ChangedBy:                    {len(unique_authors)}")

    # 1. Distinct human templates count. Since each beat text is authored
    # once and used at most once, no two human entries should share their
    # signal-text after stripping the SCREENSHOTS terminator + URLs.
    human_texts = [_human_only_signal(comms[p]["Text"])
                   for p in human_positions]
    duplicates = len(human_texts) - len(set(human_texts))
    print(f"repeated human texts (target 0):       {duplicates}")

    # 2. Longest repeated substring across DIFFERENT human entries.
    lcs = _longest_repeat_across_humans(comms, human_positions)
    print(f"longest cross-human repeated substring: {len(lcs)} chars")
    if lcs:
        print(f"  (snippet: {lcs[:60]!r}{'...' if len(lcs) > 60 else ''})")

    # 3. Author aliases — real check: every ChangedBy in the rendered
    # output must be present in the ALIASES table. This is what catches
    # drift between hand-authored beat text and the alias registry.
    used_authors = {e["ChangedBy"] for e in comms}
    missing = sorted(used_authors - set(ALIASES.keys()))
    print(f"authors used but not in ALIASES:       "
          f"{missing if missing else 'none'}")

    # 4. Antecedent documentation (NOT a check). These are the refs the
    # hand-author declared per beat. This does not verify anything about
    # the rendered text — a real check would look for the referenced
    # entity (name, work item, error code) in the responding beat.
    print("antecedents (documentation only — hand-declared per beat):")
    for i, (_a, _t, refs) in enumerate(humans_spec):
        if i == 0:
            print(f"  h{i:02d} -> (initial response; no antecedent required)")
            continue
        # sanity: all refs must be strictly less than i
        assert all(0 <= r < i for r in refs), f"bad ref list on beat {i}"
        print(f"  h{i:02d} -> {refs}")

    # 5. Monotonic counters in the tail and in each inter-human gap.
    ok, tail_hours = _monotonic_tail_ok(comms, human_positions)
    print(f"monotonic counters in tail + gaps:     {ok}")
    print(f"  tail counter values:                 {tail_hours}")

    # 6. Max Text length and other shape signals.
    lens = [len(e["Text"]) for e in comms]
    print(f"Text length: min={min(lens)} median="
          f"{sorted(lens)[len(lens)//2]} max={max(lens)}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rng_a = random.Random(SEED ^ 0xA)
    doc_a, hpos_a = build_A(rng_a)
    (OUT_DIR / "test_input_A.json").write_text(
        json.dumps(doc_a, indent=2, ensure_ascii=False) + "\n"
    )
    selfcheck("test_input_A.json", doc_a, hpos_a, A_HUMANS)

    rng_b = random.Random(SEED ^ 0xB)
    doc_b, hpos_b = build_B(rng_b)
    (OUT_DIR / "test_input_B.json").write_text(
        json.dumps(doc_b, indent=2, ensure_ascii=False) + "\n"
    )
    selfcheck("test_input_B.json", doc_b, hpos_b, B_HUMANS)


if __name__ == "__main__":
    main()
