"""Curated knowledge about who publishes security code on GitHub.

Tiers drive both scoring and the UI badges. Everything here is a *default*:
the admin UI writes overrides into the `settings` table.
"""
from __future__ import annotations

TIER_BIG_TECH = "big_tech"
TIER_SECURITY_VENDOR = "security_vendor"
TIER_RESEARCH_LAB = "research_lab"
TIER_GOVERNMENT = "government"
TIER_COMMUNITY = "community_org"
TIER_KNOWN_RESEARCHER = "known_researcher"
TIER_NEWCOMER = "newcomer"
TIER_INDIE = "indie"
TIER_UNKNOWN = "unknown"

TIER_LABELS = {
    TIER_BIG_TECH: "Big Tech",
    TIER_SECURITY_VENDOR: "Security Vendor",
    TIER_RESEARCH_LAB: "Research Lab",
    TIER_GOVERNMENT: "Government / CERT",
    TIER_COMMUNITY: "Community Org",
    TIER_KNOWN_RESEARCHER: "Known Researcher",
    TIER_NEWCOMER: "New Account",
    TIER_INDIE: "Independent",
    TIER_UNKNOWN: "Unclassified",
}

TIER_ORDER = [
    TIER_BIG_TECH, TIER_SECURITY_VENDOR, TIER_RESEARCH_LAB, TIER_GOVERNMENT,
    TIER_COMMUNITY, TIER_KNOWN_RESEARCHER, TIER_NEWCOMER, TIER_INDIE, TIER_UNKNOWN,
]

BIG_TECH = {
    "facebook", "facebookincubator", "facebookresearch", "meta-llama", "pytorch",
    "google", "googlecloudplatform", "google-research", "googleprojectzero", "googlechromelabs",
    "microsoft", "azure", "dotnet", "microsoftgraph",
    "apple", "amzn", "aws", "aws-samples", "awslabs", "amazon-science",
    "netflix", "netflix-skunkworks", "uber", "uber-common", "airbnb", "lyft",
    "cloudflare", "spotify", "shopify", "stripe", "slackhq", "square", "block",
    "linkedin", "twitter", "x", "pinterest", "dropbox", "salesforce", "yahoo",
    "yelp", "adobe", "ibm", "intel", "nvidia", "arm-software", "qualcomm",
    "github", "gitlab-org", "atlassian", "vmware", "oracle", "sap", "redhat-cop",
    "openai", "anthropics", "huggingface", "deepmind", "mistralai",
}

SECURITY_VENDORS = {
    "trailofbits", "projectdiscovery", "nccgroup", "rapid7", "tenable", "crowdstrike",
    "mandiant", "fireeye", "paloaltonetworks", "unit42", "sentinelone", "sophoslabs",
    "eset", "kaspersky", "trendmicro", "fortinet", "fortra", "qualys", "snyk",
    "aquasecurity", "sysdiglabs", "falcosecurity", "chainguard-dev", "wiz-sec",
    "orcasecurity", "lacework", "datadog", "elastic", "splunk", "sumologic",
    "bishopfox", "specterops", "mdsecactivebreach", "f-secure", "withsecure",
    "ioactive", "doyensec", "zeropointsecurity", "praetorian-inc", "optiv",
    "securonix", "anvilsecure", "include-security", "cure53", "quarkslab",
    "thalium", "synacktiv", "randorisec", "sekoia-io", "harfanglab", "gatewatcher",
    "varonis", "cyberark", "beyondtrust", "hashicorp", "1password", "bitwarden",
    "jumpcloud", "okta", "duo-labs", "cisco-talos", "talos-security", "virustotal",
    "greynoise-io", "shodan-labs", "censys", "runzeroinc", "binarly-io", "eclypsium",
    "jfrog", "checkmarx", "veracode", "contrast-security", "semgrep", "github-security-lab",
    "sonatype", "socketdev", "phylum-dev", "stacklok", "endorlabs", "oligo-security",
    "protectai", "lakeraai", "robustintelligence", "hiddenlayerai",
}

RESEARCH_LABS = {
    "google-research", "googleprojectzero", "microsoft-research", "cmu-sei", "sei-cmu",
    "ucsb-seclab", "sysseclab", "seclab-ucr", "ruhr-uni-bochum", "vusec", "mpi-sp",
    "inria", "cispa", "tudelft", "eurecom-s3", "epfl-lara", "nyuad-cyber",
    "s3-eurecom", "squarelab", "iseclab", "secdev",
}

GOVERNMENT = {
    "cisagov", "nationalsecurityagency", "nsacyber", "ukncsc", "ncsc-nl",
    "anssi-fr", "ssi-gouv", "certsocietegenerale", "cert-polska", "certcc",
    "bsi-bund", "cert-eu", "europol", "defensecyber", "dod-cyber-crime-center",
    "canada-ca", "gchq", "jpcert",
}

COMMUNITY_ORGS = {
    "owasp", "ossf", "openssf", "sigstore", "cncf", "linuxfoundation",
    "mitre", "mitre-attack", "center-for-threat-informed-defense", "sigmahq",
    "yara-rules", "misp", "thehive-project", "velocidex", "volatilityfoundation",
    "radareorg", "rizinorg", "nationalvulnerabilitydatabase", "cveproject",
    "rustsec", "pyupio", "metasploit", "rapid7-metasploit", "zaproxy",
    "wazuh", "securityonion", "arkime", "suricata", "zeek", "snort3",
    "capstone-engine", "unicorn-engine", "angr", "google-ctf", "defcon",
}

# A short, deliberately conservative seed list of individual researchers whose
# output is worth seeing on day one. Extend from Admin -> Sources.
KNOWN_RESEARCHERS = {
    "swisskyrepo", "carlospolop", "hahwul", "0xdea", "danielmiessler", "s0md3v",
    "lgandx", "byt3bl33d3r", "fortra", "gentilkiwi", "skelsec", "fortynorthsecurity",
    "cocomelonc", "vxunderground", "mrd0x", "ly4k", "antoniococo", "x1337loser",
    "gtworek", "wh0amitz", "synacktiv", "zeroperil", "icyguider", "trustedsec",
}

# Seeded "starred by" radar: new 0-star repos surfacing in these users' stars is
# one of the strongest early signals there is.
RADAR_ACCOUNTS = [
    "swisskyrepo", "carlospolop", "hahwul", "0xdea", "s0md3v", "mrd0x", "cocomelonc",
]

WATCHED_ORGS = [
    # big tech security output
    "google", "googleprojectzero", "facebookincubator", "microsoft", "cloudflare",
    "netflix-skunkworks", "awslabs", "github", "openai", "anthropics",
    # vendors / labs
    "trailofbits", "projectdiscovery", "nccgroup", "bishopfox", "specterops",
    "mdsecactivebreach", "synacktiv", "quarkslab", "doyensec", "aquasecurity",
    "falcosecurity", "chainguard-dev", "snyk", "elastic", "cisco-talos",
    "sentinelone", "mandiant", "rapid7", "binarly-io", "protectai", "semgrep",
    # community / gov
    "owasp", "ossf", "sigstore", "sigmahq", "mitre-attack",
    "center-for-threat-informed-defense", "cisagov", "nsacyber", "anssi-fr",
    "velocidex", "volatilityfoundation", "wazuh", "thehive-project",
]


def tier_for_login(login: str) -> tuple[str, str]:
    """Static tier lookup. Returns (tier, label)."""
    key = (login or "").lower()
    if key in BIG_TECH:
        return TIER_BIG_TECH, TIER_LABELS[TIER_BIG_TECH]
    if key in SECURITY_VENDORS:
        return TIER_SECURITY_VENDOR, TIER_LABELS[TIER_SECURITY_VENDOR]
    if key in RESEARCH_LABS:
        return TIER_RESEARCH_LAB, TIER_LABELS[TIER_RESEARCH_LAB]
    if key in GOVERNMENT:
        return TIER_GOVERNMENT, TIER_LABELS[TIER_GOVERNMENT]
    if key in COMMUNITY_ORGS:
        return TIER_COMMUNITY, TIER_LABELS[TIER_COMMUNITY]
    if key in KNOWN_RESEARCHERS:
        return TIER_KNOWN_RESEARCHER, TIER_LABELS[TIER_KNOWN_RESEARCHER]
    return "", ""
