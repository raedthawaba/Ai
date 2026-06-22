# Hajeen AI Platform — Production Deployment Guide
## Phase 10: Production Infrastructure

---

## Prerequisites

| Tool | Minimum Version |
|------|----------------|
| kubectl | 1.28+ |
| Helm | 3.12+ |
| Docker | 24.0+ |
| Python | 3.11+ |
| CUDA (GPU nodes) | 12.1+ |

---

## 1. Infrastructure Setup

### 1.1 Create Kubernetes Namespace
```bash
kubectl apply -f infra/k8s/namespace.yaml
```

### 1.2 Configure Secrets
```bash
# Copy and fill in secrets template
cp infra/k8s/secrets/app-secrets.yaml infra/k8s/secrets/app-secrets.local.yaml
# Edit app-secrets.local.yaml with real credentials
kubectl apply -f infra/k8s/secrets/app-secrets.local.yaml
```

### 1.3 Apply ConfigMaps
```bash
kubectl apply -f infra/k8s/configmaps/
```

### 1.4 Create Persistent Volumes
```bash
kubectl apply -f infra/k8s/storage/persistent-volumes.yaml
```

---

## 2. Docker Image Build

### Build all images
```bash
# API Server
docker build -t ghcr.io/hajeen/hajeen-api:1.0.0 \
  -f infra/docker/Dockerfile.api .

# Worker
docker build -t ghcr.io/hajeen/hajeen-worker:1.0.0 \
  -f infra/docker/Dockerfile.worker .

# Inference (GPU)
docker build -t ghcr.io/hajeen/hajeen-inference:1.0.0 \
  -f infra/docker/Dockerfile.inference .

# Push to registry
docker push ghcr.io/hajeen/hajeen-api:1.0.0
docker push ghcr.io/hajeen/hajeen-worker:1.0.0
docker push ghcr.io/hajeen/hajeen-inference:1.0.0
```

---

## 3. Helm Deployment

### 3.1 Add Bitnami charts
```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

### 3.2 Install in staging
```bash
helm upgrade --install hajeen-staging ./helm/hajeen-platform \
  --namespace hajeen-platform \
  --values helm/hajeen-platform/values.yaml \
  --values helm/hajeen-platform/values.staging.yaml \
  --set global.imageTag=1.0.0 \
  --wait --timeout=10m
```

### 3.3 Install in production
```bash
helm upgrade --install hajeen ./helm/hajeen-platform \
  --namespace hajeen-platform \
  --values helm/hajeen-platform/values.yaml \
  --values helm/hajeen-platform/values.production.yaml \
  --set global.imageTag=1.0.0 \
  --wait --timeout=15m
```

---

## 4. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n hajeen-platform

# Verify API health
kubectl exec -n hajeen-platform deployment/hajeen-api -- \
  curl -s http://localhost:8000/api/v1/health

# Check HPA status
kubectl get hpa -n hajeen-platform

# View logs
kubectl logs -n hajeen-platform deployment/hajeen-api --tail=100 -f
```

---

## 5. Monitoring Setup

### 5.1 Deploy monitoring stack
```bash
# Prometheus + Grafana
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --values monitoring/prometheus/values.yaml

# Loki (log aggregation)
helm upgrade --install loki grafana/loki-stack \
  --namespace monitoring \
  --values monitoring/loki/loki-config.yaml

# Tempo (distributed tracing)
helm upgrade --install tempo grafana/tempo \
  --namespace monitoring \
  --values monitoring/tempo/tempo-config.yaml
```

### 5.2 Import Grafana Dashboards
```bash
kubectl create configmap grafana-dashboards \
  --from-file=monitoring/dashboards/ \
  -n monitoring
```

---

## 6. Rollback Procedure

```bash
# Rollback API to previous version
kubectl rollout undo deployment/hajeen-api -n hajeen-platform

# Rollback all components via Helm
helm rollback hajeen 0 -n hajeen-platform

# Check rollback status
kubectl rollout status deployment/hajeen-api -n hajeen-platform
```

---

## 7. Autoscaling Verification

```bash
# Apply HPA
kubectl apply -f infra/k8s/autoscaling/hpa.yaml

# Generate load to trigger scaling
kubectl run load-test --image=busybox \
  --rm -it --restart=Never \
  -n hajeen-platform \
  -- /bin/sh -c "while true; do wget -q -O- http://hajeen-api-service/api/v1/health; done"

# Watch HPA scale up
kubectl get hpa -n hajeen-platform -w
```
