# Certificate Lifecycle Dashboard

This document describes the certificate lifecycle reporting and monitoring dashboards for the Vault PKI certificate management system.

## Overview

The dashboard solution provides **two complementary approaches** for certificate lifecycle visibility:

1. **HTML Reports** - Static reports for ops teams and compliance auditing
2. **Grafana Dashboard** - Real-time monitoring with alerting for operations

## Architecture

```
┌─────────────────┐
│  Vault KV API   │  ← Single source of truth
│ (certificates/) │
└────────┬────────┘
         │
         ├──────────────────────────────┐
         │                              │
         ▼                              ▼
┌─────────────────┐           ┌────────────────────┐
│ Ansible Report  │           │ Prometheus Exporter│
│   Generator     │           │  (Python Script)   │
└────────┬────────┘           └─────────┬──────────┘
         │                              │
         ├──────────┐                   │
         ▼          ▼                   ▼
    ┌───────┐  ┌──────┐         ┌─────────────┐
    │ HTML  │  │ JSON │         │ Prometheus  │
    │Report │  │Report│         └──────┬──────┘
    └───────┘  └──────┘                │
                                       ▼
                                  ┌─────────┐
                                  │ Grafana │
                                  └─────────┘
```

## Solution 1: HTML Reports (Ops & Compliance Teams)

### Features

- **Visual Dashboard**: Summary stats with color-coded alerts
- **Certificate Table**: Sortable, searchable inventory
- **Expiry Timeline**: Next 90 days expiry schedule
- **Compliance Section**: Action items for expiring certificates
- **Export Formats**: HTML (human) + JSON (machine)

### Quick Start

```bash
# Generate certificate report
ansible-playbook playbooks/generate-certificate-report.yml \
  -e vault_server_address=https://vault.example.com:8200

# View HTML report
open ~/vault-cert-reports/certificate-report-latest.html

# Check JSON report (for API integration)
cat ~/vault-cert-reports/certificate-report-latest.json
```

### Report Outputs

| File | Purpose | Audience |
|------|---------|----------|
| `certificate-report-latest.html` | Visual dashboard | Ops teams, compliance audits |
| `certificate-report-latest.json` | Machine-readable data | Automation, APIs, Grafana |
| `certificate-report-{timestamp}.html` | Historical snapshot | Audit trail |

### HTML Report Features

- **Interactive Table**: Sort by any column, search/filter
- **Color-Coded Status**:
  - 🟢 **Healthy**: > 30 days until expiry
  - 🟡 **Warning**: 7-30 days until expiry
  - 🟠 **Critical**: 0-7 days until expiry
  - 🔴 **Expired**: Already expired
- **Summary Stats**: Total, healthy, warning, critical, expired counts
- **Print-Friendly**: Optimized CSS for PDF export

### Automation

Schedule regular report generation in AAP:

```yaml
# AAP Job Template Schedule
- name: Daily Certificate Report
  schedule: "0 8 * * *"  # 8 AM daily
  playbook: generate-certificate-report.yml
  extra_vars:
    report_output_dir: /var/www/html/reports
```

Or use cron:

```bash
0 8 * * * /usr/bin/ansible-playbook /path/to/generate-certificate-report.yml
```

### Customization

Override default thresholds:

```bash
ansible-playbook playbooks/generate-certificate-report.yml \
  -e vault_server_address=https://vault.example.com:8200 \
  -e cert_warning_days=45 \
  -e cert_critical_days=14 \
  -e report_output_dir=/custom/path
```

## Solution 2: Grafana Dashboard (Real-Time Monitoring)

### Components

1. **Prometheus Exporter** - Python service that exposes Vault KV data as Prometheus metrics
2. **Prometheus** - Scrapes metrics and stores time-series data
3. **Grafana** - Visualizes metrics with dashboards and alerts

### Deployment

#### Step 1: Deploy Prometheus Exporter

```bash
# Deploy exporter to monitoring server
ansible-playbook playbooks/deploy-prometheus-exporter.yml \
  -e vault_server_address=https://vault.example.com:8200 \
  -e target_host=monitoring-server
```

This installs:
- `/opt/vault-cert-exporter/vault_cert_exporter.py` - Exporter script
- `vault-cert-exporter.service` - Systemd service
- Exposes metrics on `http://monitoring-server:9090/metrics`

#### Step 2: Configure Prometheus

Add to your `prometheus.yml`:

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

Verify scrape target:

```bash
curl http://monitoring-server:9090/metrics
```

#### Step 3: Import Grafana Dashboard

1. Open Grafana UI
2. Navigate to **Dashboards → Import**
3. Upload `playbooks/roles/vault_prometheus_exporter/files/grafana-dashboard.json`
4. Select Prometheus data source
5. Click **Import**

### Metrics Exposed

| Metric | Type | Description |
|--------|------|-------------|
| `vault_certificate_days_until_expiry` | Gauge | Days until certificate expires |
| `vault_certificate_renewal_needed` | Gauge | 1 if renewal needed, 0 otherwise |
| `vault_certificate_status` | Gauge | Status code (0=healthy, 1=warning, 2=critical, 3=expired) |
| `vault_certificate_last_scanned_timestamp` | Gauge | Unix timestamp of last scan |
| `vault_certificates_total` | Gauge | Total number of certificates |
| `vault_certificates_by_status{status}` | Gauge | Count by status (healthy/warning/critical/expired) |

### Grafana Dashboard Panels

1. **Certificate Overview** - Total certificate count
2. **Healthy Certificates** - Count of healthy certs
3. **Warning Certificates** - Count of certs expiring 7-30 days
4. **Critical/Expired Certificates** - Count of urgent renewals
5. **Status Distribution** - Pie chart of certificate health
6. **Days Until Expiry** - Time series graph with threshold lines
7. **Certificate Expiry Timeline** - Table view with color coding
8. **Certificates Expiring Soon** - Filtered table for action items

### Alerting (Grafana)

Configure alerts for proactive notifications:

```yaml
# Example alert rule (Grafana UI)
Alert Name: Certificate Expiring Soon
Condition: vault_certificate_days_until_expiry < 7
Evaluate Every: 5m
For: 10m
Notification Channel: slack-ops-channel
Message: "Certificate {{hostname}} ({{cn}}) expiring in {{value}} days!"
```

Notification channels:
- Slack
- Email
- PagerDuty
- Webhook (custom integrations)

### Service Management

```bash
# Start/stop exporter
systemctl start vault-cert-exporter
systemctl stop vault-cert-exporter

# View status
systemctl status vault-cert-exporter

# View logs
journalctl -u vault-cert-exporter -f

# Test endpoints
curl http://localhost:9090/health
curl http://localhost:9090/metrics
```

## Data Flow

### HTML Report Generation

```
1. Ansible playbook runs → vault_cert_report role
2. Role queries Vault KV API (secrets/certificates/*)
3. Retrieves certificate inventory for all hosts
4. Processes data (calculate compliance status)
5. Generates HTML report from Jinja2 template
6. Generates JSON export for API consumption
7. Creates symlinks to "latest" versions
```

### Grafana Real-Time Monitoring

```
1. Prometheus exporter service runs continuously
2. Every 60s, queries Vault KV API (secrets/certificates/*)
3. Converts certificate data to Prometheus metrics
4. Exposes metrics on :9090/metrics endpoint
5. Prometheus scrapes metrics every 60s
6. Stores time-series data in TSDB
7. Grafana queries Prometheus for dashboard/alerts
8. Alerts trigger notifications for critical certs
```

## Comparison: HTML vs. Grafana

| Feature | HTML Reports | Grafana Dashboard |
|---------|-------------|-------------------|
| **Update Frequency** | On-demand / Scheduled | Real-time (1min refresh) |
| **Data Source** | Vault KV API | Vault KV → Prometheus |
| **Audience** | Compliance, audits | Operations, SRE |
| **Alerting** | None | Yes (Slack, email, etc.) |
| **Historical Data** | Snapshot files | Time-series (retention policy) |
| **Setup Complexity** | Low (just run playbook) | Medium (exporter + Prometheus + Grafana) |
| **Infrastructure** | None (runs on AAP) | Requires monitoring stack |
| **Output Format** | HTML, JSON | Visual dashboards, graphs |
| **Best For** | Scheduled reports, compliance | 24/7 monitoring, proactive alerts |

## Recommended Approach

**Use both solutions together:**

1. **Daily HTML Reports** - For compliance, management visibility, audit trail
2. **Grafana Dashboard** - For real-time ops monitoring, proactive alerting

This provides:
- ✅ Real-time operational visibility (Grafana)
- ✅ Compliance documentation (HTML reports)
- ✅ Historical audit trail (timestamped HTML reports)
- ✅ Proactive alerting (Grafana alerts)
- ✅ Executive/management reporting (HTML dashboard)

## Integration with Certificate Issuance Playbook

The `issue-pki-certificate.yml` playbook already updates Vault KV inventory after certificate issuance. This means:

1. ✅ Every certificate issuance updates the KV inventory
2. ✅ HTML reports automatically include latest data
3. ✅ Grafana metrics reflect real-time state
4. ✅ No manual inventory updates required

**Workflow:**

```
issue-pki-certificate.yml → Updates Vault KV
                              ↓
                        Prometheus Exporter
                              ↓
                          Grafana Dashboard (auto-refresh)
```

## Customization

### Adjust Thresholds

Both solutions support custom thresholds:

```bash
# HTML Report
ansible-playbook playbooks/generate-certificate-report.yml \
  -e cert_warning_days=45 \
  -e cert_critical_days=14

# Prometheus Exporter
# Edit /etc/systemd/system/vault-cert-exporter.service
# Change --warning-days and --critical-days flags
systemctl daemon-reload
systemctl restart vault-cert-exporter
```

### Add Custom Panels (Grafana)

Edit the dashboard JSON or use Grafana UI to add:
- Certificate issuance rate over time
- Average certificate lifetime
- Certificate renewals per day/week
- Compliance score percentage

### HTML Report Branding

Modify `playbooks/roles/vault_cert_report/templates/certificate_report.html.j2`:
- Add company logo
- Customize colors/fonts
- Add additional sections

## Troubleshooting

### HTML Reports

**Issue**: No certificates found in Vault KV

```bash
# Verify KV path
vault kv list secrets/certificates/

# Check AppRole permissions
vault read auth/approle/role/aap-automation/policies
```

**Issue**: Report generation fails

```bash
# Check Ansible logs
ansible-playbook generate-certificate-report.yml -vvv

# Verify Vault connectivity
curl -k https://vault.example.com:8200/v1/sys/health
```

### Grafana Dashboard

**Issue**: No metrics in Grafana

```bash
# 1. Check exporter is running
systemctl status vault-cert-exporter

# 2. Test exporter endpoint
curl http://localhost:9090/metrics

# 3. Check Prometheus scrape targets
# Open Prometheus UI → Status → Targets
# Verify vault-certificates job is UP

# 4. Check Grafana data source
# Grafana UI → Configuration → Data Sources → Prometheus
# Click "Test" button
```

**Issue**: Stale metrics

```bash
# Check exporter cache duration
journalctl -u vault-cert-exporter -n 50

# Adjust cache duration in service file
# --cache-duration 30  # Reduce to 30 seconds
```

## Security Considerations

### Vault Credentials

Both solutions use Vault AppRole authentication:

```bash
# Credentials are passed via environment variables
VAULT_ROLE_ID=xxx
VAULT_SECRET_ID=xxx

# For systemd service, credentials are in service file
# Ensure file permissions: 0644 (root:root)

# For AAP, credentials are stored as AAP credential type
# AAP injects role_id/secret_id at runtime
```

### Network Security

```bash
# Prometheus exporter listens on 0.0.0.0:9090
# Restrict access using firewall rules:

firewall-cmd --permanent --add-rich-rule='
  rule family="ipv4"
  source address="10.0.0.0/8"
  port protocol="tcp" port="9090" accept'
firewall-cmd --reload
```

### TLS/SSL

The Prometheus exporter currently uses HTTP. For production:

1. Use reverse proxy (nginx/HAProxy) with TLS
2. Configure Prometheus to use HTTPS
3. Or restrict to localhost and tunnel via SSH

## Next Steps

1. **Schedule HTML reports** - Configure AAP job template with cron schedule
2. **Deploy Prometheus exporter** - Run `deploy-prometheus-exporter.yml`
3. **Configure Grafana alerts** - Set up Slack/email notifications
4. **Test alert workflow** - Create test certificate expiring in 5 days
5. **Document runbooks** - Create SOPs for certificate renewal

## Support

For issues or questions:
- Review playbook logs with `-vvv` flag
- Check Vault audit logs for API errors
- Review exporter logs: `journalctl -u vault-cert-exporter -f`
- Verify Vault KV inventory: `vault kv get secrets/certificates/{hostname}`

## Files Reference

### Playbooks
- `playbooks/generate-certificate-report.yml` - Generate HTML/JSON reports
- `playbooks/deploy-prometheus-exporter.yml` - Deploy Prometheus exporter

### Roles
- `playbooks/roles/vault_cert_report/` - Report generation role
- `playbooks/roles/vault_prometheus_exporter/` - Exporter deployment role

### Templates
- `playbooks/roles/vault_cert_report/templates/certificate_report.html.j2` - HTML report template
- `playbooks/roles/vault_prometheus_exporter/templates/vault-cert-exporter.service.j2` - Systemd service

### Scripts
- `playbooks/roles/vault_prometheus_exporter/files/vault_cert_exporter.py` - Prometheus exporter
- `playbooks/roles/vault_prometheus_exporter/files/grafana-dashboard.json` - Grafana dashboard
