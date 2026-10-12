"""Domain classification.

Keyword and topic rules rather than a model. Slower to tune but you can read
why something matched, it runs offline, and the lists are editable.
"""
from __future__ import annotations

import re

# Domains
# weight: how much a hit here argues the repo really is security work
CATEGORIES: dict[str, dict] = {
    "exploit-dev": {
        "label": "Exploit Development",
        "accent": "#ff4d6d",
        "weight": 1.35,
        "topics": ["exploit", "exploits", "cve", "poc", "0day", "privilege-escalation", "rce", "exploit-development"],
        "keywords": [
            "exploit", "proof of concept", "poc for", "0-day", "zero-day", "privilege escalation",
            "remote code execution", "rce", "lpe", "use-after-free", "heap spray", "rop chain",
            "kernel exploit", "sandbox escape", "cve-", "buffer overflow", "arbitrary write",
        ],
    },
    "offensive-security": {
        "label": "Offensive / Red Team",
        "accent": "#ff7849",
        "weight": 1.25,
        "topics": ["red-team", "redteam", "pentesting", "penetration-testing", "offensive-security",
                   "post-exploitation", "c2", "command-and-control", "lateral-movement", "adversary-emulation"],
        "keywords": [
            "red team", "redteam", "pentest", "penetration test", "post-exploitation", "c2 framework",
            "command and control", "implant", "beacon", "lateral movement", "adversary emulation",
            "payload generator", "shellcode", "loader", "edr evasion", "process injection",
        ],
    },
    "malware-analysis": {
        "label": "Malware Analysis",
        "accent": "#c77dff",
        "weight": 1.3,
        "topics": ["malware", "malware-analysis", "ransomware", "botnet", "yara", "sandbox", "unpacking"],
        "keywords": [
            "malware", "ransomware", "botnet", "trojan", "rootkit", "yara rule", "unpacker",
            "sample analysis", "packer", "obfuscated binary", "c2 extraction", "config extractor",
        ],
    },
    "reverse-engineering": {
        "label": "Reverse Engineering",
        "accent": "#9d8df1",
        "weight": 1.2,
        "topics": ["reverse-engineering", "ghidra", "ida-pro", "binary-ninja", "radare2", "decompiler", "disassembler"],
        "keywords": [
            "reverse engineering", "ghidra", "ida pro", "idapython", "binary ninja", "radare2",
            "decompiler", "disassembler", "binary analysis", "symbol recovery", "emulation of firmware",
        ],
    },
    "detection-engineering": {
        "label": "Detection Engineering",
        "accent": "#2dd4bf",
        "weight": 1.25,
        "topics": ["detection-engineering", "sigma", "siem", "edr", "detection-rules", "blue-team", "blueteam", "soc"],
        "keywords": [
            "detection rule", "detection engineering", "sigma rule", "siem", "splunk", "elastic security",
            "sentinel", "blue team", "soc", "telemetry", "edr", "hunting query", "kql", "osquery",
        ],
    },
    "threat-intel": {
        "label": "Threat Intelligence",
        "accent": "#38bdf8",
        "weight": 1.2,
        "topics": ["threat-intelligence", "threat-hunting", "ioc", "mitre-attack", "apt", "cti", "misp"],
        "keywords": [
            "threat intelligence", "threat hunting", "indicator of compromise", "ioc feed", "mitre att&ck",
            "att&ck", "apt group", "ttp", "misp", "stix", "taxii", "adversary tracking",
        ],
    },
    "dfir": {
        "label": "DFIR / Forensics",
        "accent": "#60a5fa",
        "weight": 1.25,
        "topics": ["dfir", "forensics", "incident-response", "memory-forensics", "volatility", "timeline-analysis"],
        "keywords": [
            "incident response", "digital forensics", "dfir", "memory forensics", "volatility",
            "disk image", "artifact parser", "timeline analysis", "triage collection", "evidence acquisition",
        ],
    },
    "appsec": {
        "label": "Application Security",
        "accent": "#34d399",
        "weight": 1.15,
        "topics": ["appsec", "application-security", "sast", "dast", "owasp", "sql-injection", "xss", "ssrf",
                   "web-security", "bug-bounty", "vulnerability-scanner"],
        "keywords": [
            "application security", "appsec", "sast", "dast", "owasp", "sql injection", "xss",
            "ssrf", "xxe", "deserialization", "web vulnerability", "bug bounty", "taint analysis",
            "code scanning", "security linter",
        ],
    },
    "cloud-security": {
        "label": "Cloud & Container",
        "accent": "#22d3ee",
        "weight": 1.2,
        "topics": ["cloud-security", "kubernetes-security", "container-security", "aws-security", "azure-security",
                   "gcp-security", "cspm", "iam"],
        "keywords": [
            "cloud security", "kubernetes security", "container escape", "cspm", "cnapp",
            "aws iam", "azure ad", "entra id", "gcp security", "s3 bucket", "privilege escalation in aws",
            "admission controller", "falco", "ebpf security", "runtime security",
        ],
    },
    "network-security": {
        "label": "Network Security",
        "accent": "#818cf8",
        "weight": 1.1,
        "topics": ["network-security", "ids", "ips", "firewall", "packet-analysis", "nmap", "wireshark", "mitm"],
        "keywords": [
            "network security", "intrusion detection", "packet capture", "pcap", "nmap script",
            "man in the middle", "mitm proxy", "tls interception", "protocol fuzzer", "dns tunneling",
            "wireshark dissector",
        ],
    },
    "osint": {
        "label": "OSINT & Recon",
        "accent": "#fbbf24",
        "weight": 1.1,
        "topics": ["osint", "reconnaissance", "recon", "subdomain-enumeration", "asm", "attack-surface"],
        "keywords": [
            "osint", "reconnaissance", "subdomain enumeration", "attack surface", "asset discovery",
            "footprinting", "breach data", "people search", "domain intelligence", "certificate transparency",
        ],
    },
    "cryptography": {
        "label": "Cryptography",
        "accent": "#f472b6",
        "weight": 1.1,
        "topics": ["cryptography", "crypto", "post-quantum", "tls", "zero-knowledge", "cryptanalysis", "pqc"],
        "keywords": [
            "cryptography", "cryptanalysis", "post-quantum", "kyber", "dilithium", "zero-knowledge proof",
            "homomorphic encryption", "side-channel attack", "tls library", "key exchange", "constant-time",
        ],
    },
    "ai-security": {
        "label": "AI / LLM Security",
        "accent": "#a78bfa",
        "weight": 1.35,
        "topics": ["ai-security", "llm-security", "prompt-injection", "adversarial-machine-learning",
                   "ml-security", "jailbreak", "mcp-security", "agent-security"],
        "keywords": [
            "llm security", "prompt injection", "jailbreak", "model extraction", "adversarial machine learning",
            "ai red team", "guardrails", "model poisoning", "agent security", "mcp server security",
            "ai agent sandbox", "llm firewall",
        ],
    },
    "supply-chain": {
        "label": "Supply Chain",
        "accent": "#4ade80",
        "weight": 1.25,
        "topics": ["supply-chain-security", "sbom", "sigstore", "slsa", "dependency-confusion", "provenance"],
        "keywords": [
            "supply chain security", "sbom", "software bill of materials", "sigstore", "slsa",
            "dependency confusion", "typosquatting", "package provenance", "build attestation",
            "malicious package", "npm malware", "pypi malware",
        ],
    },
    "mobile-security": {
        "label": "Mobile Security",
        "accent": "#fb7185",
        "weight": 1.15,
        "topics": ["android-security", "ios-security", "mobile-security", "frida", "apk-analysis", "jailbreak"],
        "keywords": [
            "android security", "ios security", "mobile security", "frida script", "apk analysis",
            "smali", "objection", "ssl pinning bypass", "ipa analysis", "mobile pentest",
        ],
    },
    "hardware-iot": {
        "label": "Hardware / IoT",
        "accent": "#facc15",
        "weight": 1.2,
        "topics": ["iot-security", "hardware-hacking", "firmware-analysis", "uefi", "rfid", "can-bus", "sdr"],
        "keywords": [
            "firmware analysis", "hardware hacking", "iot security", "uefi", "bios implant", "jtag",
            "can bus", "rfid", "nfc attack", "software defined radio", "baseband", "glitching",
            "fault injection", "flipper zero",
        ],
    },
    "fuzzing": {
        "label": "Fuzzing & VR",
        "accent": "#f97316",
        "weight": 1.3,
        "topics": ["fuzzing", "fuzzer", "afl", "libfuzzer", "vulnerability-research", "symbolic-execution"],
        "keywords": [
            "fuzzer", "fuzzing harness", "afl++", "libfuzzer", "coverage-guided", "symbolic execution",
            "vulnerability research", "crash triage", "sanitizer", "grammar fuzzing", "snapshot fuzzing",
        ],
    },
    "identity-access": {
        "label": "Identity & Access",
        "accent": "#2dd4bf",
        "weight": 1.1,
        "topics": ["active-directory", "kerberos", "oauth", "saml", "sso", "identity-security"],
        "keywords": [
            "active directory", "kerberos", "kerberoasting", "ntlm relay", "oauth security", "saml",
            "single sign-on", "identity provider", "adcs", "ldap enumeration", "passkey", "webauthn",
        ],
    },
    "privacy-anonymity": {
        "label": "Privacy & Anonymity",
        "accent": "#94a3b8",
        "weight": 1.0,
        "topics": ["privacy", "anonymity", "tor", "end-to-end-encryption", "censorship-circumvention"],
        "keywords": [
            "privacy preserving", "anonymity network", "tor hidden service", "end-to-end encryption",
            "censorship circumvention", "metadata scrubbing", "differential privacy", "traffic analysis resistance",
        ],
    },
    "security-tooling": {
        "label": "Security Tooling",
        "accent": "#64748b",
        "weight": 0.9,
        "topics": ["security", "security-tools", "infosec", "cybersecurity", "hacking", "vulnerability", "hardening"],
        "keywords": [
            "security tool", "security framework", "cybersecurity", "infosec", "hardening", "compliance scanning",
            "security automation", "vulnerability management", "security audit", "exposure management",
        ],
    },
}

# weak on their own, worth a nudge
GENERIC_SECURITY_TERMS = [
    "security", "cyber", "infosec", "vulnerability", "attack", "defence", "defense",
    "threat", "exploit", "hacking", "hacker", "cve", "mitre", "soc", "siem",
]

# usually a reading list rather than a project
NOISE_PATTERNS = [
    "awesome list", "awesome-", "cheat sheet", "cheatsheet", "interview question",
    "roadmap", "study notes", "course material", "my writeups", "ctf writeup",
    "collection of links", "curated list", "learning path", "book notes",
    "tryhackme", "hackthebox writeup", "100 days of",
]

# coursework and throwaway repos
LOW_EFFORT_PATTERNS = [
    "my first", "test repo", "hello world", "practice project", "school project",
    "university assignment", "tutorial follow", "clone of",
]

_WORD = re.compile(r"[a-z0-9+#.&-]+")


def _normalise(*parts: str) -> str:
    return " ".join(p.lower() for p in parts if p)


def classify(description: str, topics: list[str], name: str, readme: str = "") -> tuple[list[str], float, dict]:
    """Return (categories, relevance, per-category hits).

    The readme counts for less than the description. A readme mentions plenty
    in passing, the description says what the thing is for.
    """
    topics_l = [t.lower() for t in (topics or [])]
    head = _normalise(name.replace("-", " ").replace("_", " "), description)
    body = (readme or "").lower()[:6000]

    hits: dict[str, float] = {}
    detail: dict[str, list[str]] = {}

    for slug, meta in CATEGORIES.items():
        score = 0.0
        matched: list[str] = []
        for topic in meta["topics"]:
            if topic in topics_l:
                score += 3.0
                matched.append(f"topic:{topic}")
        for kw in meta["keywords"]:
            if kw in head:
                score += 2.0
                matched.append(f"head:{kw}")
            elif kw in body:
                score += 0.6
                matched.append(f"readme:{kw}")
        if score:
            hits[slug] = score * meta["weight"]
            detail[slug] = matched[:8]

    generic = sum(1 for term in GENERIC_SECURITY_TERMS if term in head)
    generic += sum(0.25 for term in GENERIC_SECURITY_TERMS if term in body)

    total = sum(hits.values()) + generic * 0.8
    # 14 points of evidence is treated as "unmistakably a security project".
    relevance = max(0.0, min(1.0, total / 14.0))

    ranked = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)
    categories = [slug for slug, value in ranked if value >= 2.0][:4]
    if not categories and relevance >= 0.25:
        categories = ["security-tooling"]

    return categories, relevance, detail


def noise_penalty(description: str, name: str, topics: list[str]) -> tuple[float, list[str]]:
    """0 to 1. Link farms, course material, throwaway repos."""
    text = _normalise(name.replace("-", " "), description, " ".join(topics or []))
    reasons: list[str] = []
    penalty = 0.0
    for pat in NOISE_PATTERNS:
        if pat in text:
            penalty += 0.45
            reasons.append(f"curation/list pattern: '{pat}'")
            break
    for pat in LOW_EFFORT_PATTERNS:
        if pat in text:
            penalty += 0.3
            reasons.append(f"low-effort pattern: '{pat}'")
            break
    return min(penalty, 0.8), reasons


def category_label(slug: str) -> str:
    return CATEGORIES.get(slug, {}).get("label", slug.replace("-", " ").title())


def category_accent(slug: str) -> str:
    return CATEGORIES.get(slug, {}).get("accent", "#64748b")
