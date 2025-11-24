# Vault Prometheus Exporter Role

Deploys a Prometheus exporter for real-time certificate lifecycle monitoring via Grafana.

## Features

- **Prometheus Metrics**: Exposes certificate data as Prometheus metrics
- **Systemd Service**: Runs continuously as background service
- **Automatic Refresh**: Polls Vault KV every 60 seconds (configurable)
- **Health Endpoint**: `/health` for monitoring exporter status
- **Grafana Dashboard**: Pre-built dashboard with alerts

## Architecture

```
Vault KV API → Python Exporter → Prometheus → Grafana Dashboard
                    ↓
              :9090/metrics
```

## Usage

```yaml
- hosts: monitoring-server
  become: true
  roles:
    - vault_prometheus_exporter
  vars:
    vault_addr: "https://vault.example.com:8200"
    exporter_port: 9090
```

Or use the standalone playbook:

```bash
ansible-playbook playbooks/deploy-prometheus-exporter.yml \
  -e vault_server_address=https://vault.example.com:8200 \
  -e target_host=monitoring-server
```

## Metrics Exposed

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `vault_certificate_days_until_expiry` | Gauge | hostname, cn, serial | Days until certificate expires |
| `vault_certificate_renewal_needed` | Gauge | hostname, cn, serial | 1 if renewal needed, 0 otherwise |
| `vault_certificate_status` | Gauge | hostname, cn, status | Status code (0-3) |
| `vault_certificate_last_scanned_timestamp` | Gauge | hostname, cn, serial | Unix timestamp of last scan |
| `vault_certificates_total` | Gauge | - | Total certificate count |
| `vault_certificates_by_status` | Gauge | status | Count by status |

### Status Codes

- `0` = Healthy (> 30 days)
- `1` = Warning (7-30 days)
- `2` = Critical (0-7 days)
- `3` = Expired (< 0 days)

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `vault_addr` | `https://vault.hashicorp.local:8200` | Vault server URL |
| `exporter_port` | `9090` | Metrics HTTP port |
| `exporter_cache_duration` | `60` | Metrics cache duration (seconds) |
| `cert_warning_days` | `30` | Warning threshold |
| `cert_critical_days` | `7` | Critical threshold |

## Prometheus Configuration

Add to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'vault-certificates'
    scrape_interval: 60s
    static_configs:
      - targets:
          - 'monitoring-server:9090'
```

Reload Prometheus:

```bash
systemctl reload prometheus
```

## Grafana Dashboard

Import the pre-built dashboard:

1. Open Grafana UI
2. Navigate to **Dashboards → Import**
3. Upload `files/grafana-dashboard.json`
4. Select Prometheus data source
5. Click **Import**

### Dashboard Panels

- Certificate Overview (total count)
- Healthy/Warning/Critical/Expired stats
- Status distribution pie chart
- Days until expiry time series
- Certificate table with color coding
- Certificates expiring soon (<30 days)

## Service Management

```bash
# Start/stop
systemctl start vault-cert-exporter
systemctl stop vault-cert-exporter

# Status
systemctl status vault-cert-exporter

# Logs
journalctl -u vault-cert-exporter -f

# Test endpoints
curl http://localhost:9090/health
curl http://localhost:9090/metrics
```

## Alerting

Configure Grafana alerts for proactive monitoring:

```yaml
Alert: Certificate Expiring Soon
Condition: vault_certificate_days_until_expiry < 7
Evaluate: Every 5m, For 10m
Notification: Slack/Email/PagerDuty
Message: "Certificate {{hostname}} expiring in {{value}} days!"
```

## Security

### Credentials

Vault credentials are stored in systemd service file:

```ini
Environment="VAULT_ROLE_ID=xxx"
Environment="VAULT_SECRET_ID=xxx"
```

File permissions: `0644 root:root`

### Network

Restrict access using firewall:

```bash
firewall-cmd --permanent --add-rich-rule='
  rule family="ipv4"
  source address="10.0.0.0/8"
  port protocol="tcp" port="9090" accept'
```

## Requirements

- Python 3.6+
- `requests` library (`pip3 install requests`)
- Vault AppRole credentials
- Network access to Vault server

## Files

- `files/vault_cert_exporter.py` - Python exporter script
- `files/grafana-dashboard.json` - Pre-built Grafana dashboard
- `templates/vault-cert-exporter.service.j2` - Systemd service template

## Troubleshooting

### No metrics in Grafana

```bash
# 1. Check exporter is running
systemctl status vault-cert-exporter

# 2. Test metrics endpoint
curl http://localhost:9090/metrics

# 3. Check Prometheus targets
# Prometheus UI → Status → Targets

# 4. Verify Grafana data source
# Grafana → Configuration → Data Sources → Test
```

### Stale metrics

```bash
# Check exporter logs
journalctl -u vault-cert-exporter -n 50

# Adjust cache duration
# Edit: /etc/systemd/system/vault-cert-exporter.service
# Change: --cache-duration 30
systemctl daemon-reload
systemctl restart vault-cert-exporter
```

## See Also

- [DASHBOARD.md](../../../DASHBOARD.md) - Comprehensive dashboard documentation
- [vault_cert_report](../vault_cert_report/) - HTML/JSON report generation
