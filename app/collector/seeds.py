"""Default discovery sources, inserted once on first boot."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Source
from .known import RADAR_ACCOUNTS, WATCHED_ORGS

# `{since}` is substituted with an ISO date by the pipeline.
SEARCH_QUERIES: list[tuple[str, str, float]] = [
    ("topic:security created:>{since}", "New repos tagged `security`", 1.0),
    ("topic:cybersecurity created:>{since}", "New repos tagged `cybersecurity`", 1.0),
    ("topic:pentesting created:>{since}", "New pentesting tools", 1.1),
    ("topic:red-team created:>{since}", "New red-team tooling", 1.2),
    ("topic:blue-team created:>{since}", "New blue-team tooling", 1.1),
    ("topic:exploit created:>{since}", "New exploit repos", 1.3),
    ("topic:cve created:>{since}", "New CVE-tagged repos", 1.3),
    ("topic:malware-analysis created:>{since}", "New malware analysis tooling", 1.2),
    ("topic:threat-intelligence created:>{since}", "New threat-intel projects", 1.1),
    ("topic:dfir created:>{since}", "New DFIR tooling", 1.1),
    ("topic:detection-engineering created:>{since}", "New detection engineering", 1.2),
    ("topic:reverse-engineering created:>{since}", "New RE tooling", 1.1),
    ("topic:fuzzing created:>{since}", "New fuzzers and harnesses", 1.2),
    ("topic:osint created:>{since}", "New OSINT tooling", 1.0),
    ("topic:appsec created:>{since}", "New AppSec tooling", 1.0),
    ("topic:cloud-security created:>{since}", "New cloud security tooling", 1.1),
    ("topic:kubernetes-security created:>{since}", "New Kubernetes security", 1.1),
    ("topic:supply-chain-security created:>{since}", "New supply-chain security", 1.2),
    ("topic:llm-security created:>{since}", "New LLM security projects", 1.3),
    ("topic:prompt-injection created:>{since}", "Prompt-injection research", 1.3),
    ("topic:ai-security created:>{since}", "New AI security projects", 1.3),
    ("topic:hardware-hacking created:>{since}", "New hardware hacking", 1.1),
    ("topic:iot-security created:>{since}", "New IoT security", 1.1),
    ("topic:android-security created:>{since}", "New Android security", 1.0),
    ("topic:active-directory topic:security created:>{since}", "New AD security tooling", 1.1),
    # Intent-based queries catch everything that never gets tagged - which is
    # exactly where the 0-star gems live.
    ('"proof of concept" exploit in:name,description created:>{since}', "Fresh PoC exploits", 1.3),
    ("CVE in:name,description created:>{since}", "Repos named after a CVE", 1.25),
    ("rce OR lpe OR sandbox-escape in:name,description created:>{since}", "RCE / LPE / escape research", 1.3),
    ("edr OR evasion OR bypass in:name,description created:>{since} stars:<50", "Evasion research, low visibility", 1.2),
    ("c2 OR implant OR beacon in:name,description created:>{since} stars:<100", "C2 / implant work", 1.2),
    ("detection rules in:name,description created:>{since}", "Detection rule sets", 1.0),
    ("security scanner in:name,description created:>{since} stars:<30", "Scanners nobody has starred yet", 1.1),
    ("forensics OR incident-response in:name,description created:>{since}", "Forensics / IR", 1.0),
    ("ebpf security in:name,description created:>{since}", "eBPF security tooling", 1.1),
    ("mcp server security in:name,description created:>{since}", "MCP / agent security", 1.2),
]


def seed_sources(db: Session) -> int:
    """Insert the default sources if the table is empty. Returns rows added."""
    existing = db.scalar(select(Source.id).limit(1))
    if existing:
        return 0

    rows: list[Source] = []
    for query, label, weight in SEARCH_QUERIES:
        rows.append(Source(kind="search", value=query, label=label, weight=weight, max_pages=1))
    for org in WATCHED_ORGS:
        rows.append(Source(kind="org", value=org, label=f"Org: {org}", weight=1.0, max_pages=1))
    for login in RADAR_ACCOUNTS:
        rows.append(Source(kind="starred", value=login, label=f"Starred by @{login}", weight=1.0, max_pages=1))

    db.add_all(rows)
    db.commit()
    return len(rows)
