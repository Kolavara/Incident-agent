# PayStream Inc — Infrastructure & Services

This is a simulated target repository for the Incident Response Agent's
remediation pipeline. It contains the configuration and source code for
PayStream's payment processing platform.

**Do not push to production** — this is a sandbox for auto-remediation demos.

## Repository Structure

```
fixes/paystream/
├── configs/           # Service configuration files
│   ├── payment-processor/
│   ├── redis/
│   ├── postgres/
│   └── notification-worker/
├── k8s/               # Kubernetes manifests
│   ├── payment-processor-v2/
│   ├── redis-cache/
│   ├── notification-worker/
│   ├── api-gateway/
│   └── auth-service/
├── src/               # Service source code
│   ├── payment-service/
│   ├── notification-worker/
│   └── auth-service/
├── tests/             # Validation & integration tests
└── ci/                # CI/CD configuration
```

## Services

| Service | Port | Description |
|---|---|---|
| payment-processor-v2 | 8080 | Payment transaction processing |
| redis-cache-03 | 6379 | Redis caching layer |
| postgres-primary | 5432 | Primary database |
| notification-worker | 9090 | Email/push notification delivery |
| api-gateway | 443 | API gateway (nginx) |
| auth-service | 4000 | Authentication & JWT management |
| fraud-detection-ml | 5005 | ML-based fraud detection |
