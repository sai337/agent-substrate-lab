# LinkedIn

**One line**
12 stateful AI agents on 3 pods, waking up in under 215 ms at p95: I measured CNCF Agent Substrate on my own cluster, and my first run's 4 failures were all my own design mistakes. Write-up: <article link>

**Longer variant**
Agents spend most of their time waiting, yet most platforms give each one a pod. CNCF Agent Substrate snapshots idle agents out of memory and resumes them on demand.

I tested it with my own stateful agent: 12 agents on 3 gVisor workers, no state lost, resume p50 133-184 ms and p95 145-213 ms across four nightly runs, no internet until a policy allowed exactly one host.

Three lessons from the failures: idle must mean suspended, a silent answer is not a pass, and policies take about 5 seconds to apply.

Open source, with EKS Terraform: <repo link>
#AIAgents #CNCF #Kubernetes #PlatformEngineering
