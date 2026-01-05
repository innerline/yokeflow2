# Docker Deployment Architectures for YokeFlow

**Last Updated:** January 2026
**Status:** Architecture Design Document

## Executive Summary

YokeFlow faces unique challenges when deploying with Docker, particularly when generated applications require their own containerized services (PostgreSQL, Redis, etc.). This document outlines current limitations and proposed solutions for running YokeFlow in various Docker configurations.

## The Core Challenge

When YokeFlow runs in Docker and generates applications that also need Docker services, we encounter the "Docker-in-Docker-in-Docker" problem:

```
Level 1: Host Machine
  └── Level 2: YokeFlow Containers (API, PostgreSQL, Web UI)
      └── Level 3: Agent Containers (Project sandboxes)
          └── Level 4: App Service Containers (PostgreSQL, Redis, etc.)
```

This creates:
- **Port conflicts** (multiple PostgreSQL instances wanting port 5432)
- **Network complexity** (containers can't easily communicate across levels)
- **Volume mount confusion** (container paths vs host paths)
- **Performance overhead** (each layer adds latency)

## Current Solution: Port Shifting Strategy

As implemented in `prompts/initializer_prompt_docker.md`:

```yaml
# YokeFlow uses:
- PostgreSQL: 5432
- API: 8000
- Web UI: 3000

# Generated apps shift to:
- PostgreSQL: 5433, 5434, 5435...
- Redis: 6380, 6381, 6382...
- MinIO: 9002/9003, 9004/9005...
```

**Pros:**
- Simple to understand
- Works with current architecture
- No code changes required

**Cons:**
- Manual port management
- Prone to conflicts with multiple projects
- Difficult to track allocations
- Not scalable

## Deployment Architecture Options

### Option 1: Hybrid Deployment (Recommended for Production)

Run YokeFlow directly on host, containerize only agent sessions:

```
Host Machine (Direct Installation)
├── YokeFlow API (Python process - port 8000)
├── YokeFlow Web UI (Node process - port 3000)
├── PostgreSQL for YokeFlow (Container or native - port 5432)
└── Docker Engine
    ├── Agent Container 1 (Project A)
    │   ├── Workspace mount: /var/yokeflow/generations/project-a
    │   └── Can freely use ports 5433+, 6380+, etc.
    └── Agent Container 2 (Project B)
        ├── Workspace mount: /var/yokeflow/generations/project-b
        └── Different ports allocated
```

**Implementation Steps:**

1. **Install YokeFlow on Host:**
```bash
# Install Python dependencies
cd /var/yokeflow
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install Node dependencies
cd web-ui && npm install && npm run build
cd ../mcp-task-manager && npm install && npm run build
```

2. **Run PostgreSQL in Docker (for easy management):**
```bash
docker run -d \
  --name yokeflow-postgres \
  -e POSTGRES_PASSWORD=secure_password \
  -e POSTGRES_USER=agent \
  -e POSTGRES_DB=yokeflow \
  -p 127.0.0.1:5432:5432 \
  -v yokeflow-pgdata:/var/lib/postgresql/data \
  --restart unless-stopped \
  postgres:16-alpine
```

3. **Create systemd services:**
```ini
# /etc/systemd/system/yokeflow-api.service
[Unit]
Description=YokeFlow API
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=yokeflow
WorkingDirectory=/var/yokeflow
Environment="PATH=/var/yokeflow/venv/bin"
ExecStart=/var/yokeflow/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/yokeflow-web.service
[Unit]
Description=YokeFlow Web UI
After=yokeflow-api.service

[Service]
Type=simple
User=yokeflow
WorkingDirectory=/var/yokeflow/web-ui
ExecStart=/usr/bin/npm start
Environment="NODE_ENV=production"
Environment="PORT=3000"
Restart=always

[Install]
WantedBy=multi-user.target
```

4. **Start services:**
```bash
systemctl enable yokeflow-api yokeflow-web
systemctl start yokeflow-api yokeflow-web
```

**Advantages:**
- ✅ Eliminates one Docker layer
- ✅ Full Docker access for agents
- ✅ Simple port management
- ✅ Better performance
- ✅ Easier debugging

**Disadvantages:**
- ❌ More complex initial setup
- ❌ Host system dependencies
- ❌ Less portable

### Option 2: Full Docker with Service Orchestration

Keep everything in Docker but add intelligent service management:

```
Docker Host
└── YokeFlow Network (172.20.0.0/16)
    ├── YokeFlow API Container
    ├── YokeFlow PostgreSQL Container
    ├── YokeFlow Web UI Container
    └── Service Orchestrator
        ├── Port Allocator (tracks 5433-5499, 6380-6399, etc.)
        ├── Network Manager (creates isolated networks)
        └── Container Lifecycle Manager
            ├── Project A Network (172.21.0.0/24)
            │   ├── Agent Container
            │   ├── PostgreSQL (port 5433)
            │   └── Redis (port 6380)
            └── Project B Network (172.22.0.0/24)
                ├── Agent Container
                ├── PostgreSQL (port 5434)
                └── Redis (port 6381)
```

**Implementation:** See Service Orchestrator design in previous section.

**Advantages:**
- ✅ Fully containerized
- ✅ Automatic port management
- ✅ Network isolation
- ✅ Easy deployment

**Disadvantages:**
- ❌ Complex implementation
- ❌ Docker-in-Docker overhead
- ❌ Harder to debug

### Option 3: Docker with External Services

Use managed services for generated applications:

```
YokeFlow (Docker)
├── API Container
├── Web UI Container
└── PostgreSQL Container

Generated Apps use:
├── Digital Ocean Managed PostgreSQL
├── Digital Ocean Managed Redis
├── S3-compatible object storage
└── Other cloud services
```

**Configuration:**
```yaml
# .yokeflow.yaml
services:
  postgresql:
    type: managed
    provider: digitalocean
    auto_provision: true
    size: db-s-1vcpu-1gb
  redis:
    type: managed
    provider: digitalocean
    auto_provision: true
```

**Advantages:**
- ✅ No port conflicts
- ✅ High availability
- ✅ Automatic backups
- ✅ Zero maintenance

**Disadvantages:**
- ❌ Additional cost ($15+/month per service)
- ❌ Internet latency
- ❌ Vendor lock-in
- ❌ Complex provisioning logic

### Option 4: Kubernetes Deployment

Use Kubernetes for complete orchestration:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: yokeflow
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: yokeflow-api
  namespace: yokeflow
spec:
  replicas: 1
  selector:
    matchLabels:
      app: yokeflow-api
  template:
    spec:
      containers:
      - name: api
        image: yokeflow/api:latest
        ports:
        - containerPort: 8000
---
# Each project gets its own namespace
apiVersion: v1
kind: Namespace
metadata:
  name: project-abc123
---
# Services deployed in project namespace
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgresql
  namespace: project-abc123
spec:
  serviceName: postgresql
  replicas: 1
  template:
    spec:
      containers:
      - name: postgres
        image: postgres:16-alpine
        ports:
        - containerPort: 5432
```

**Advantages:**
- ✅ True container orchestration
- ✅ Automatic service discovery
- ✅ No port conflicts (internal networking)
- ✅ Highly scalable

**Disadvantages:**
- ❌ Complex setup
- ❌ Requires Kubernetes knowledge
- ❌ Overkill for small deployments
- ❌ Higher resource requirements

## Comparison Matrix

| Aspect | Hybrid | Full Docker | External Services | Kubernetes |
|--------|--------|-------------|------------------|------------|
| **Setup Complexity** | Medium | High | Low | Very High |
| **Port Management** | Simple | Automated | N/A | Automatic |
| **Performance** | Best | Good | Variable | Good |
| **Cost** | Low | Low | High | Medium-High |
| **Scalability** | Good | Good | Excellent | Excellent |
| **Debugging** | Easy | Hard | Medium | Hard |
| **Portability** | Low | High | Medium | High |
| **Production Ready** | Yes | With work | Yes | Yes |

## Recommended Implementation Path

### Phase 1: Immediate (Current State)
- Continue using port shifting strategy
- Document port allocations
- Add validation to prevent conflicts

### Phase 2: Short Term (1-2 months)
- Implement Service Orchestrator module
- Add port allocation database tables
- Create API endpoints for service management
- Automate docker-compose generation

### Phase 3: Medium Term (3-6 months)
- Add service auto-detection from spec files
- Implement health checks and monitoring
- Create Web UI for service management
- Add cleanup and resource management

### Phase 4: Long Term (6+ months)
- Evaluate Kubernetes migration
- Consider managed service integrations
- Implement multi-region support
- Add service mesh for complex applications

## Migration Guide

### From Current to Hybrid Deployment

1. **Backup everything:**
```bash
pg_dump -U agent -d yokeflow > yokeflow_backup.sql
tar -czf generations_backup.tar.gz /var/yokeflow/generations/
```

2. **Stop Docker containers:**
```bash
docker-compose down
```

3. **Install YokeFlow on host:**
```bash
# See Hybrid Deployment section above
```

4. **Update configuration:**
```yaml
# .yokeflow.yaml
sandbox:
  type: docker
  docker_socket: /var/run/docker.sock  # Direct access

project:
  default_generations_dir: /var/yokeflow/generations  # Host path
```

5. **Test with a simple project**

6. **Gradually migrate existing projects**

## Security Considerations

### Port Exposure
- Never expose database ports to internet
- Use firewall rules to restrict access
- Implement port scanning detection

### Container Isolation
- Use separate networks per project
- Implement resource limits
- Enable security scanning

### Access Control
- Implement RBAC for service management
- Audit service deployments
- Monitor resource usage

## Monitoring and Observability

### Metrics to Track
- Port allocation rate
- Container resource usage
- Network traffic between services
- Service health status

### Logging Strategy
```json
{
  "event": "service_deployed",
  "project_id": "abc123",
  "service": "postgresql",
  "port": 5433,
  "container_id": "def456",
  "timestamp": "2026-01-05T10:00:00Z"
}
```

### Alerting Rules
- Port allocation > 90% capacity
- Container memory > 80%
- Service unhealthy > 5 minutes
- Network errors > threshold

## Troubleshooting Guide

### Common Issues

#### Port Already in Use
```bash
# Find what's using the port
lsof -i :5433
netstat -tulpn | grep 5433

# Kill the process or choose different port
```

#### Container Can't Connect to Service
```bash
# Check network connectivity
docker exec agent-container ping host.docker.internal

# Verify port forwarding
docker port service-container

# Check firewall rules
iptables -L DOCKER
```

#### Volume Mount Issues
```bash
# Verify paths
docker inspect agent-container | jq '.[0].Mounts'

# Check permissions
ls -la /var/yokeflow/generations/
```

## Future Enhancements

### Planned Features
1. **Auto-scaling:** Scale services based on load
2. **Service Templates:** Pre-configured service stacks
3. **Cost Optimization:** Automatic resource right-sizing
4. **Multi-cloud Support:** Deploy across providers
5. **Service Mesh:** Advanced networking with Istio/Linkerd

### Research Areas
- Rootless Docker for better security
- Podman as Docker alternative
- WebAssembly for lightweight isolation
- Firecracker for microVM approach

## Conclusion

The Docker-in-Docker challenge is significant but solvable. The recommended approach depends on your specific needs:

- **For production:** Use Hybrid Deployment
- **For development:** Current port shifting works
- **For scale:** Consider Kubernetes
- **For simplicity:** Use managed services

The Service Orchestrator design provides a path forward that maintains Docker benefits while solving port and network challenges.

## References

- [Docker-in-Docker Best Practices](https://jpetazzo.github.io/2015/09/03/do-not-use-docker-in-docker-for-ci/)
- [Docker Network Architecture](https://docs.docker.com/network/)
- [Kubernetes Service Discovery](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Container Orchestration Patterns](https://www.oreilly.com/library/view/kubernetes-patterns/9781492050278/)