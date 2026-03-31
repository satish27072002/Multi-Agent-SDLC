# DevOps K8s CI/CD Platform - Project Context

**Created:** March 18, 2026  
**For:** Continuing project in new chat session  
**Student:** Satish Somarouthu (BIT Sweden, Masters)

---

## 🎯 PROJECT OVERVIEW

### What We're Building
A **Kubernetes-native CI/CD platform** - essentially building your own mini-Vercel/Netlify that demonstrates complete DevOps expertise.

**Key Features:**
- GitOps workflow (GitHub webhook → auto-deploy to K8s)
- Local K8s cluster (k3d) for development
- Production deployment to DigitalOcean Kubernetes
- Infrastructure as Code (Terraform)
- Monitoring stack (Prometheus + Grafana)
- ArgoCD for GitOps automation

### Why This Project
**Career Goal:** Land DevOps/MLOps role with strong portfolio

**Project Value:**
- Shows ALL core DevOps skills (K8s, Docker, CI/CD, IaC, Monitoring)
- Kubernetes is #1 most in-demand DevOps skill
- Can deploy own projects on it (demonstrates practical use)
- Complements existing ML background (ViT project completed)

**Timeline:** 3 weeks (Phase 1: 1 week, Phase 2: 1 week, Phase 3: 1 week)

---

## 👤 USER PROFILE

**Name:** Satish Somarouthu  
**Education:** Masters at Blekinge Institute of Technology, Sweden  
**GitHub:** https://github.com/satish27072002  
**Location:** Karlskrona, Sweden

**Current Skill Level:**
- ✅ Strong: Python, Machine Learning, Data Science
- ✅ Completed: Vision Transformer satellite classification project (590k images, multi-label)
- 🔄 Learning: DevOps, Kubernetes, Infrastructure (this project)
- ⏭️ Next: AI Agent monitoring dashboard (AgentOps)

**Working Style:**
- Uses coding agents for implementation (gives specs, reviews code)
- Learns by building real projects
- Prefers practical over theoretical
- Values honest, realistic expectations over over-promising

---

## 💻 AVAILABLE RESOURCES

### Hardware
- **MacBook** (8GB+ RAM, macOS)
- Local development environment

### Cloud Credits
- ✅ **DigitalOcean: $200 credits** (GitHub Student Developer Pack)
  - Expires: February 2027
  - Enough for ~16 months of K8s cluster ($12/month)
  - **USE THIS - not Oracle** (easier, already have account)

### Accounts
- ✅ GitHub (has account)
- ✅ DigitalOcean (has account with $200 credits)
- ✅ Docker Hub (needs to create - free)
- ⏭️ Grafana Cloud (optional, create later)

---

## 🛠️ TECH STACK

### Core Technologies
**Kubernetes Stack:**
- k3d (local K8s clusters on Mac)
- kubectl (K8s CLI)
- Helm (K8s package manager)
- k9s (K8s terminal UI - ESSENTIAL tool)

**GitOps & CI/CD:**
- ArgoCD (GitOps engine)
- GitHub Actions (CI pipeline)
- Helm charts (app packaging)

**Infrastructure as Code:**
- Terraform (infrastructure automation)
- DigitalOcean provider

**Monitoring:**
- Prometheus (metrics collection)
- Grafana (visualization dashboards)
- kube-state-metrics
- node-exporter

**Containerization:**
- Docker Desktop
- Docker Hub (image registry)

### Tools Installed (macOS)
```bash
# Required installations (via Homebrew)
brew install kubectl          # K8s CLI
brew install k3d             # Local K8s
brew install helm            # Package manager
brew install k9s             # Terminal UI
brew install stern           # Multi-pod logs
brew install kubectx         # Context switching
brew install terraform       # IaC tool

# Also needed:
# - Docker Desktop (download separately)
# - VS Code (code editor)
```

---

## 📋 PROJECT ARCHITECTURE

### Components

**1. Local Development (Phase 1)**
```
Developer Machine (Mac)
├── k3d cluster (3 nodes)
│   ├── Master node (control plane)
│   └── 2 Worker nodes (agents)
├── ArgoCD (GitOps controller)
├── Prometheus + Grafana (monitoring)
└── Sample applications
```

**2. GitOps Pipeline**
```
GitHub Repository
├── /kubernetes/
│   ├── deployments/
│   ├── services/
│   └── configmaps/
├── /helm-charts/
└── /terraform/

↓ (Git webhook)

ArgoCD
├── Monitors Git repo
├── Detects changes
└── Auto-deploys to K8s

↓

Kubernetes Cluster
├── Pulls new images
├── Rolls out changes
└── Self-heals if failures
```

**3. Production Deployment (Phase 3)**
```
DigitalOcean Kubernetes
├── Managed K8s cluster (2 nodes)
├── ArgoCD (production config)
├── Prometheus + Grafana
├── Ingress Controller (traffic routing)
└── Deployed applications
```

---

## 📚 LEARNING RESOURCES

### Week 1: Kubernetes Fundamentals
**Primary Tutorial:**
- "Kubernetes Crash Course" by TechWorld with Nana (3.5 hours)
  - https://www.youtube.com/watch?v=X48VuDVv0do
  - Watch at 1.5x speed
  - Best beginner K8s video

**Hands-on:**
- Kubernetes official tutorial: https://kubernetes.io/docs/tutorials/
- Interactive playground: https://killercoda.com/playgrounds/scenario/kubernetes

**Documentation:**
- Kubernetes concepts: https://kubernetes.io/docs/concepts/
- kubectl cheat sheet: https://kubernetes.io/docs/reference/kubectl/cheatsheet/

### Week 2: GitOps & ArgoCD
**Primary Tutorial:**
- ArgoCD Getting Started: https://argo-cd.readthedocs.io/en/stable/
- GitOps Explained: https://www.youtube.com/watch?v=f5EpcWp0THw
- ArgoCD Tutorial: https://www.youtube.com/watch?v=MeU5_k9ssrs

**Terraform:**
- Official tutorials: https://developer.hashicorp.com/terraform/tutorials
- freeCodeCamp course: https://www.youtube.com/watch?v=SLB_c_ayRMo (2 hours)

### Week 3: Monitoring & Production
**Prometheus + Grafana:**
- Prometheus docs: https://prometheus.io/docs/prometheus/latest/getting_started/
- TechWorld with Nana: https://www.youtube.com/watch?v=QoDqxm7ybLc (1 hour)

---

## 🎯 PROJECT PHASES

### PHASE 1: Local Kubernetes Setup (Week 1) ← CURRENT PHASE

**Goal:** Get K8s running locally, deploy first app, understand basics

**Steps (Ready to Execute):**

**Step 1: Install Tools** (30 min)
```bash
brew install kubectl k3d helm k9s stern kubectx
# Download Docker Desktop from docker.com
```

**Step 2: Create Local Cluster** (10 min)
```bash
k3d cluster create dev --agents 2 --port "8080:80@loadbalancer"
kubectl get nodes  # Should show 3 nodes
```

**Step 3: Deploy First App** (15 min)
- Deploy hello-kubernetes app
- Access via port-forward
- Verify working at http://localhost:8080

**Step 4: Explore with k9s** (15 min)
- Learn to navigate pods, deployments, services
- View logs, describe resources
- Understand self-healing

**Step 5: Watch Tutorials** (Rest of week)
- Kubernetes Crash Course (3.5h over 2-3 days)
- Complete interactive tutorials
- Practice kubectl commands

**Success Criteria:**
- [ ] Can create/delete K8s clusters
- [ ] Can deploy apps using kubectl
- [ ] Understand Pods, Deployments, Services
- [ ] Comfortable using k9s
- [ ] Can read pod logs and troubleshoot

---

### PHASE 2: GitOps & Automation (Week 2)

**Goal:** Set up ArgoCD, implement GitOps workflow, write Terraform configs

**Key Tasks:**
- Install ArgoCD on local cluster
- Create GitHub repo for K8s manifests
- Configure ArgoCD to watch repo
- Deploy app via Git push (auto-deploy!)
- Write Terraform for infrastructure
- Package app as Helm chart

**Success Criteria:**
- [ ] ArgoCD running and monitoring Git repo
- [ ] Push to Git → auto-deploys to K8s
- [ ] Terraform creates infrastructure
- [ ] Helm chart for sample app

---

### PHASE 3: Production & Monitoring (Week 3)

**Goal:** Deploy to DigitalOcean, add monitoring, complete platform

**Key Tasks:**
- Create DigitalOcean K8s cluster (using credits)
- Use Terraform to provision infrastructure
- Deploy ArgoCD to production
- Set up Prometheus + Grafana
- Create monitoring dashboards
- Deploy real application (ViT model?)
- Document everything

**Success Criteria:**
- [ ] Production K8s cluster on DigitalOcean
- [ ] GitOps working in production
- [ ] Monitoring dashboards showing metrics
- [ ] Can deploy apps with Git push
- [ ] Complete documentation

---

## 📊 PROJECT STRUCTURE

```
devops-k8s-platform/
├── README.md                          # Project documentation
├── docs/
│   ├── architecture.md                # System design
│   ├── setup-guide.md                 # Installation steps
│   └── learning-notes.md              # What you learned
├── kubernetes/
│   ├── apps/
│   │   ├── hello-app/
│   │   │   ├── deployment.yaml
│   │   │   ├── service.yaml
│   │   │   └── ingress.yaml
│   │   └── vit-model/                 # Deploy ML model
│   ├── argocd/
│   │   └── applications/              # ArgoCD app definitions
│   └── monitoring/
│       ├── prometheus/
│       └── grafana/
├── helm-charts/
│   └── sample-app/                    # Custom Helm chart
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
├── terraform/
│   ├── local/                         # Local k3d setup
│   └── digitalocean/                  # DO K8s cluster
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── scripts/
│   ├── setup-local.sh                 # One-command local setup
│   ├── deploy-production.sh           # Deploy to DO
│   └── cleanup.sh                     # Tear down resources
└── .github/
    └── workflows/
        └── ci.yaml                    # GitHub Actions pipeline
```

---

## 🎓 KEY CONCEPTS TO LEARN

### Kubernetes Core
- **Pods:** Smallest unit, runs containers
- **Deployments:** Manages pods, ensures replicas
- **Services:** Network access to pods (ClusterIP, NodePort, LoadBalancer)
- **ConfigMaps:** Configuration data
- **Secrets:** Sensitive data (passwords, keys)
- **Volumes:** Persistent storage
- **Ingress:** HTTP routing (like nginx)
- **Namespaces:** Logical isolation

### GitOps Principles
- **Declarative:** Desired state in Git
- **Versioned:** All changes tracked
- **Automated:** Git push triggers deployment
- **Self-healing:** Cluster matches Git state

### Infrastructure as Code
- **Terraform:** Provision cloud resources
- **Idempotent:** Same config = same result
- **State management:** Track what's deployed
- **Modules:** Reusable infrastructure blocks

---

## 💡 CRITICAL GUIDELINES

### What TO Do
✅ **Start simple** - Master basics before advanced features
✅ **Break things** - Delete pods, see them recreate (learn self-healing)
✅ **Use k9s heavily** - Best way to understand K8s
✅ **Read error messages** - K8s errors are actually helpful
✅ **Document learnings** - Take notes as you go
✅ **Ask for help** - Kubernetes Slack is very helpful

### What NOT to Do
❌ **Don't skip Phase 1** - Local mastery before cloud deployment
❌ **Don't memorize commands** - Use k9s and kubectl explain
❌ **Don't rush** - Understanding > Speed
❌ **Don't use production best practices yet** - Learn basics first
❌ **Don't worry about security initially** - Focus on functionality

### Conservative Approach
- Start with hello-world apps (not complex services)
- Use small clusters (3 nodes locally, 2 nodes in production)
- One concept at a time (don't try to learn everything at once)
- Test locally before deploying to cloud

---

## 🎯 SUCCESS METRICS

### Portfolio Impact
**After completion, you can say:**
- "Built production-grade K8s platform with GitOps automation"
- "Deployed ML models to Kubernetes with CI/CD pipeline"
- "Implemented Infrastructure as Code with Terraform"
- "Set up comprehensive monitoring with Prometheus + Grafana"

**Resume additions:**
- Kubernetes cluster administration
- GitOps with ArgoCD
- Infrastructure as Code (Terraform)
- Docker containerization
- CI/CD pipeline development
- Prometheus/Grafana monitoring

### Technical Skills Demonstrated
- Cloud-native architecture
- Container orchestration
- DevOps automation
- Infrastructure management
- Production deployment
- Monitoring & observability

---

## 🚀 CURRENT STATUS

### Completed
✅ Project planned and scoped
✅ Resources identified (DigitalOcean credits available)
✅ Tech stack decided
✅ Learning path defined
✅ Ready to execute Phase 1

### Next Immediate Actions (In Order)
1. **Install tools** (30 min)
   - kubectl, k3d, helm, k9s, stern, kubectx
   - Docker Desktop

2. **Create first cluster** (10 min)
   - `k3d cluster create dev --agents 2`

3. **Deploy hello app** (15 min)
   - Test that everything works
   - Access at localhost:8080

4. **Learn with k9s** (15 min)
   - Explore pods, deployments, services

5. **Watch tutorials** (This week)
   - Kubernetes Crash Course (3.5 hours)

### Blockers/Questions
None currently - ready to start!

---

## 📝 CONTEXT FOR NEW CHAT

**When starting new chat, provide:**

1. **This file** (PROJECT_CONTEXT.md)
2. **Current phase:** Phase 1, Steps 1-5
3. **What you need:** Step-by-step guidance through Phase 1
4. **Your style:** Prefer detailed instructions, will use coding agent for implementation

**Good opening message for new chat:**
```
I'm building a Kubernetes-native CI/CD platform to learn DevOps. 

I've attached the complete project context. I'm currently at Phase 1 
(Local Kubernetes Setup) and ready to execute Steps 1-5.

I have:
- MacBook (macOS)
- DigitalOcean account with $200 credits
- No K8s experience yet (learning as I build)

Please guide me through Phase 1, Step 1 (installing tools). I prefer 
detailed commands I can copy-paste, with explanations of what each 
tool does and why we need it.
```

---

## 🎬 EXPECTED OUTCOMES

### Week 1 (Phase 1)
- Working local K8s cluster
- Can deploy apps with kubectl
- Understand core K8s concepts
- Comfortable with k9s and kubectl

### Week 2 (Phase 2)
- GitOps workflow operational
- ArgoCD auto-deploying from Git
- Terraform provisioning infrastructure
- Helm charts for packaging

### Week 3 (Phase 3)
- Production cluster on DigitalOcean
- Full monitoring stack
- Real application deployed
- Complete documentation

### Final Portfolio Piece
A production-ready Kubernetes platform that:
- Demonstrates DevOps expertise
- Can deploy your ML models
- Has monitoring and observability
- Uses modern GitOps practices
- Is fully documented and impressive

---

## 📞 SUPPORT RESOURCES

**Official Documentation:**
- Kubernetes: https://kubernetes.io/docs
- ArgoCD: https://argo-cd.readthedocs.io
- Terraform: https://developer.hashicorp.com/terraform/docs
- Helm: https://helm.sh/docs

**Community:**
- Kubernetes Slack: https://slack.k8s.io
- r/kubernetes: https://reddit.com/r/kubernetes
- Stack Overflow: kubernetes tag

**When Stuck:**
- Use `kubectl explain <resource>` for built-in docs
- Check k9s for visual debugging
- Read pod logs with `kubectl logs <pod-name>`
- Describe resources with `kubectl describe <resource> <name>`

---

## 💰 COST TRACKING

**Total Project Cost: $0-36**

| Resource | Cost | Duration | Total |
|----------|------|----------|-------|
| Local development (k3d) | $0 | 3 weeks | $0 |
| DigitalOcean K8s cluster | $12/month | 1-3 months | $12-36 |
| Available credits | -$200 | 12 months | FREE |
| **NET COST** | | | **$0** |

**Note:** With $200 DigitalOcean credits, this project is completely free for 16+ months.

---

**END OF PROJECT CONTEXT**

Give this file to the new Claude chat along with where you are in the project and what you need help with next!
