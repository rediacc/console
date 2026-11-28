# breach-forensics: external research

Gathered on 2026-11-23 from web sources by read-only research agents. Legal points are research, not legal advice.

## Recent breaches and why victims could not say when or what

- No confirmed NSA breach: the mid-2026 "Mythos" claim is a rumour and the 17 November 2026 NSANet outage was officially maintenance. The confirmed US case is DOE/NNSA through SharePoint "ToolShell" (July 2025). Sources: https://www.microsoft.com/en-us/security/blog/2025/07/22/disrupting-active-exploitation-of-on-premises-sharepoint-vulnerabilities/ , https://www.bleepingcomputer.com/news/security/us-nuclear-weapons-agency-reportedly-hacked-in-sharepoint-attacks/
- The European Commission was breached three times in 2026: Ivanti phone management (January), an AWS key exposed by a poisoned Trivy scanner with about 340 GB taken (March), and internal networks from 22 October, not contained a month later. Sources: https://www.helpnetsecurity.com/2026/02/09/european-commission-ivanti-epmm-vulnerabilities/ , https://cert.europa.eu/blog/european-commission-cloud-breach-trivy-supply-chain , https://www.securityweek.com/european-commission-confirms-ai-assisted-cyberattack-disrupted-services/
- Storm-0940 used ConnectWise app credentials against more than 2,250 Microsoft 365 tenants; Microsoft says absence of evidence does not prove no access. Source: https://www.microsoft.com/en-us/security/blog/2026/10/21/storm-0940-uses-artex-agentic-ai-connectwise-supply-chain-compromise/
- The recurring gaps: dwell time longer than log retention (393 days on average for BRICKSTORM, https://cloud.google.com/blog/topics/threat-intelligence/brickstorm-espionage-campaign), logs kept on the compromised device and deleted by implants, access logging off by default or behind paid tiers, no data-access or flow logs. Where per-query logs lived off the attacker's reach (Salesforce event monitoring after Salesloft Drift), victims reconstructed the theft: https://cloud.google.com/blog/topics/threat-intelligence/data-theft-salesforce-instances-via-salesloft-drift

## Industry practice

- Unsampled flow records at one-minute granularity with bytes per direction are the forensic norm (AWS VPC Flow Logs: https://docs.aws.amazon.com/vpc/latest/userguide/flow-log-records.html).
- eBPF runtime tools (Tetragon, Falco; Apache-2.0) attribute flows and file opens to processes and containers; logging every read is impractical, so products log opens on sensitive paths (https://datadoghq.com/blog/engineering/workload-protection-ebpf-fim).
- R2 bucket locks block deletion and overwrite by age or date, but a bucket-admin token can lift them, unlike S3 compliance mode: https://developers.cloudflare.com/r2/buckets/bucket-locks/
- US OMB M-26-14 (22 May 2026) asks for logs searchable 6 months and retrievable one year, including network addresses, ports, accessed objects and the quantity of data affected: https://www.whitehouse.gov/wp-content/uploads/2026/05/M-26-14-Ensuring-Effective-and-Efficient-Agency-Logging-and-Network-Visibility-to-Defend-Against-Evolving-Cyber-Threats.pdf
- IP addresses can be personal data under GDPR (CJEU Breyer); network security is a legitimate interest that still needs proportionality and a stated retention.

## Detection models and CPU features

- Go-native streaming detectors (Half-Space Trees, ECOD, HBOS) need no runtime; the CIC-IDS datasets have documented labelling errors and suit smoke tests only (https://hal.archives-ouvertes.fr/hal-03775466).
- Granite TTM-r2 is an Apache-2.0 time-series model under one million parameters that runs on CPU: https://huggingface.co/ibm-granite/granite-timeseries-ttm-r2
- Go 1.26 added the experimental `simd/archsimd` package for AVX, AVX2 and AVX-512 on amd64: https://go.dev/blog/archsimd . AVX-512 is absent or hidden on many VPS hosts and on Zen 3 and older, so runtime dispatch with AVX2 and scalar fallbacks is required (https://docs.cloud.google.com/compute/docs/cpu-platforms).
- The OpenSSF model-signing specification defines detached signatures for model artifacts: https://raw.githubusercontent.com/ossf/model-signing-spec/main/README.md . CrowdStrike's July 2024 channel-file outage is the cautionary case for staged rollout and on-device validation: https://crowdstrike.com/wp-content/uploads/2024/08/Channel-File-291-Incident-Root-Cause-Analysis-08.06.2024.pdf

## Reporting duties

- NIS2 Art. 23 stages (24 hour early warning, 72 hour notification, one month final report): https://www.springlex.eu/en/packages/nis2/nis2-directive/article-23/ . Direct scope for Rediacc depends on size (Art. 2(1)); NIS2 customers impose supplier incident duties by contract regardless.
- The Cyber Resilience Act's reporting obligations apply from 11 September 2026 to manufacturers of products with digital elements, which covers the commercially distributed `rdc` CLI and renet: 24 hour early warning, 72 hour notification and a final report to ENISA's single reporting platform, and informing users: https://digital-strategy.ec.europa.eu/en/policies/cra-reporting
- DORA financial customers need first facts within hours (initial notice within 4 hours of classification, at most 24 hours from awareness): https://eur-lex.europa.eu/eli/reg_del/2025/301/oj
- The NIS Cooperation Group adopted common incident reporting templates on 26 May 2026: https://digital-strategy.ec.europa.eu/en/news/nis2-cooperation-group-adopts-common-templates-incident-reporting
