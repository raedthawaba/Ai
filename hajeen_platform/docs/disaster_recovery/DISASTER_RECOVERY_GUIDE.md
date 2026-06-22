# Hajeen AI Platform — Disaster Recovery Guide
## Phase 10: Production Infrastructure

---

## Recovery Point Objective (RPO) & Recovery Time Objective (RTO)

| Tier | RPO | RTO | Strategy |
|------|-----|-----|----------|
| Database (PostgreSQL) | 1 hour | 30 min | PITR from S3 WAL |
| Vector Database | 24 hours | 1 hour | Daily S3 backup |
| Model Storage | 24 hours | 2 hours | S3 object storage |
| Redis Cache | 0 (ephemeral) | 5 min | Automatic restart |
| Config/Secrets | 0 | 5 min | Version controlled |

---

## Scenario 1: Full Cluster Failure

### Steps:
1. Provision new Kubernetes cluster in target region
2. Apply namespace and RBAC:
   ```bash
   kubectl apply -f infra/k8s/namespace.yaml
   kubectl apply -f infra/k8s/secrets/
   kubectl apply -f infra/k8s/configmaps/
   ```
3. Restore PostgreSQL from latest S3 backup:
   ```bash
   python -m storage.distributed.disaster_recovery \
     --strategy latest_backup \
     --db-url $DATABASE_URL
   ```
4. Deploy application via Helm:
   ```bash
   helm upgrade --install hajeen ./helm/hajeen-platform \
     --namespace hajeen-platform \
     --set global.imageTag=LAST_KNOWN_GOOD_TAG
   ```
5. Verify health:
   ```bash
   kubectl get pods -n hajeen-platform
   curl https://api.hajeen.ai/api/v1/health
   ```

---

## Scenario 2: Database Corruption

### Steps:
1. Identify last clean backup:
   ```bash
   python -m storage.distributed.backup_manager --list --type postgres
   ```
2. Stop API (prevent writes):
   ```bash
   kubectl scale deployment/hajeen-api --replicas=0 -n hajeen-platform
   ```
3. Restore from PITR:
   ```bash
   python -m storage.distributed.disaster_recovery \
     --strategy point_in_time \
     --target-time "2024-01-15T10:30:00Z"
   ```
4. Verify data integrity
5. Resume API:
   ```bash
   kubectl scale deployment/hajeen-api --replicas=3 -n hajeen-platform
   ```

---

## Scenario 3: GPU Node Failure

### Steps:
1. Verify node failure:
   ```bash
   kubectl get nodes
   kubectl describe node FAILED_NODE
   ```
2. Cordon failed node:
   ```bash
   kubectl cordon FAILED_NODE
   kubectl drain FAILED_NODE --ignore-daemonsets --delete-emptydir-data
   ```
3. GPU pods auto-reschedule to healthy nodes (HPA-managed)
4. Replace node via cloud provider console or `terraform apply`
5. Remove cordon:
   ```bash
   kubectl uncordon NEW_NODE
   ```

---

## Backup Schedule

| Component | Frequency | Retention | Destination |
|-----------|-----------|-----------|-------------|
| PostgreSQL | Every 6 hours | 30 days | S3 |
| Vector DB | Daily at 02:00 UTC | 14 days | S3 |
| Model files | Weekly | 90 days | S3 Glacier |
| K8s state | On change | 30 days | S3 |
| Audit logs | Daily | 1 year | S3 |

---

## Emergency Contacts

Refer to your organization's on-call runbook. All alerts route to PagerDuty
with severity mapping:
- `critical` → immediate page
- `warning` → Slack notification
- `info` → Dashboard only

---

## Testing DR Procedures

Run DR drills monthly:
```bash
# Run chaos testing (non-production only)
python -m tests.production.failover.test_failover

# Verify backup integrity
python -m storage.distributed.backup_manager --verify --latest

# Test PITR restore to staging
python -m storage.distributed.disaster_recovery \
  --strategy point_in_time \
  --target staging \
  --dry-run
```
