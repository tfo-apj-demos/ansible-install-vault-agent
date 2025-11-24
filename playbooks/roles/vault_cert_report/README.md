# Vault Certificate Report Role

Generates comprehensive certificate lifecycle reports from Vault KV inventory.

## Features

- **HTML Dashboard**: Visual report with summary stats, sortable table, and expiry timeline
- **JSON Export**: Machine-readable data for API integration and Grafana
- **Compliance Alerts**: Color-coded status (Healthy/Warning/Critical/Expired)
- **Interactive Table**: Client-side search, sort by any column
- **Expiry Timeline**: Shows certificates expiring in next 90 days

## Usage

```yaml
- hosts: localhost
  roles:
    - vault_cert_report
  vars:
    vault_addr: "https://vault.example.com:8200"
    report_output_dir: "/tmp/vault-cert-reports"
    cert_warning_days: 30
    cert_critical_days: 7
```

Or use the standalone playbook:

```bash
ansible-playbook playbooks/generate-certificate-report.yml \
  -e vault_server_address=https://vault.example.com:8200
```

## Outputs

- `{output_dir}/certificate-report-latest.html` - Latest HTML report (symlink)
- `{output_dir}/certificate-report-latest.json` - Latest JSON export (symlink)
- `{output_dir}/certificate-report-{timestamp}.html` - Historical snapshot
- `{output_dir}/certificate-report-{timestamp}.json` - Historical data

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `vault_addr` | `https://vault.hashicorp.local:8200` | Vault server URL |
| `report_output_dir` | `/tmp/vault-cert-reports` | Report output directory |
| `report_format` | `both` | Output format: `html`, `json`, or `both` |
| `cert_warning_days` | `30` | Warning threshold (days) |
| `cert_critical_days` | `7` | Critical threshold (days) |

## Requirements

- Vault AppRole credentials (`role_id`, `secret_id`)
- Ansible collection: `community.hashi_vault`
- Certificate inventory in Vault KV (`secrets/certificates/`)

## Report Sections

1. **Summary Stats**: Total, Healthy, Warning, Critical, Expired counts
2. **Compliance Notice**: Action items for expiring/expired certificates
3. **Certificate Table**: Full inventory with status, expiry dates, paths
4. **Expiry Timeline**: Next 90 days schedule
5. **Report Information**: Thresholds, data source, remediation steps

## Integration

### Scheduled Reports (AAP)

```yaml
# AAP Job Template
schedule: "0 8 * * *"  # Daily at 8 AM
playbook: generate-certificate-report.yml
extra_vars:
  report_output_dir: /var/www/html/reports
```

### Scheduled Reports (Cron)

```bash
0 8 * * * /usr/bin/ansible-playbook /path/to/generate-certificate-report.yml
```

### API Consumption

```bash
# Read JSON report
curl http://reports-server/vault-cert-reports/certificate-report-latest.json

# Parse with jq
jq '.summary' certificate-report-latest.json
```

## See Also

- [DASHBOARD.md](../../../DASHBOARD.md) - Comprehensive dashboard documentation
- [vault_prometheus_exporter](../vault_prometheus_exporter/) - Real-time Grafana monitoring
