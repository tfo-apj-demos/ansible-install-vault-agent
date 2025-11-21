# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ansible playbooks and roles for deploying HashiCorp Vault Agent with TLS authentication and issuing PKI certificates to target systems. Two distinct architectural patterns are implemented:

1. **Vault Agent Pattern** - Full agent installation with automatic certificate renewal (best for Linux servers with full OS access)
2. **Direct PKI Issuance Pattern** - Simple certificate deployment without agent complexity (ideal for network devices, appliances)

## Core Architecture Concepts

### Authentication Flow
- **AAP Execution Environment**: Authenticates to Vault using AppRole (role_id + secret_id) managed as AAP credentials
- **Vault Agent**: After bootstrap, authenticates using TLS certificates (cert-based auth)
- **Target Machines**: Never authenticate directly to Vault in the direct issuance pattern

### Certificate Lifecycle
1. **Bootstrap Phase**: Initial certificate issuance via CSR signing (tls-auth role)
2. **Renewal Phase**: Automatic renewal through Vault Agent templates (server role) OR manual/scheduled runs of direct issuance playbook
3. **Discovery Phase**: Scans existing certificates, checks expiry, updates centralized inventory in Vault KV

### PKI Roles (Vault Configuration)
- **tls-auth**: Used for Vault Agent authentication certificates (bootstrap only)
- **server**: Used for application/service certificates (web servers, databases, etc.)

## Common Commands

### Install Dependencies
```bash
ansible-galaxy collection install -r playbooks/requirements.yml
# Collections: community.hashi_vault, community.postgresql, ansible.posix
```

### Run Playbooks

#### Full Vault Agent Setup (Pattern 1)
```bash
ansible-playbook playbooks/install-vault-agent-complete.yml \
  -e vault_server_address=https://vault.example.com:8200 \
  -e target_domain=example.com \
  -e vault_tpm_simplified=true
```

This executes a 3-play sequence:
1. **Play 1 (on targets)**: Generate key/CSR using vault_tpm role
2. **Play 2 (on localhost)**: Sign CSR via Vault using vault_sign role (AAP EE authenticates)
3. **Play 3 (on targets)**: Install Vault Agent and configure TLS auth using vault_agent role

#### Direct PKI Certificate Issuance (Pattern 2)
```bash
ansible-playbook playbooks/issue-pki-certificate.yml \
  -e vault_server_address=https://vault.example.com:8200 \
  -e target_domain=example.com \
  -e cert_renewal_threshold_days=5
```

This executes a 4-play sequence:
1. **Play 1 (on targets)**: Gather facts (FQDN)
2. **Play 2 (on localhost)**: Discover existing certificates using vault_cert_discovery role
3. **Play 3 (on localhost)**: Conditionally issue certificates using vault_pki_issue role (only if renewal needed)
4. **Play 4 (on localhost)**: Display summary report

### Test Vault Connectivity
```bash
# From AAP Execution Environment
ansible localhost -m uri -a "url=https://vault.example.com:8200/v1/sys/health validate_certs=true ca_path=/etc/pki/ca-trust/source/anchors/vault-ca.crt"
```

### Verify Vault Agent Status
```bash
ansible-playbook playbooks/verify-vault-agent.yml
```

## Role Dependencies and Execution Context

### vault_tpm
- **Context**: Runs on target machines (become: true)
- **Purpose**: Generates private key and CSR (simplified mode uses openssl, full TPM mode uses tpm2-tools)
- **Sets fact**: `vault_tpm_remote_csr_data_fact` (base64 encoded CSR content)

### vault_sign
- **Context**: Runs on localhost (AAP Execution Environment)
- **Purpose**: Signs CSR using Vault PKI (uses AppRole auth)
- **Requires**: CSR data from vault_tpm via hostvars
- **Delegates**: Certificate file copy back to target machine

### vault_agent
- **Context**: Runs on target machines (become: true)
- **Purpose**: Installs Vault binary, configures systemd service, sets up TLS authentication
- **Variables**:
  - `vault_agent_install_binary: true` - Install Vault binary
  - `vault_agent_setup_tls: true` - Configure TLS authentication (includes certificate renewal templates)
- **Key files**: `/etc/vault.d/vault-agent-config.hcl`, `/etc/systemd/system/vault-agent.service`

### vault_pki_issue
- **Context**: Runs on localhost (AAP Execution Environment)
- **Purpose**: Issues certificates from Vault PKI and copies to target machines
- **Authentication**: AppRole (role_id, secret_id)
- **Delegates**: File operations to target machine via `delegate_to`
- **Key feature**: No agent installation required on targets

### vault_cert_discovery
- **Context**: Runs on localhost (AAP Execution Environment)
- **Purpose**: Scans target machines for existing certificates, parses expiry dates, updates Vault KV inventory
- **Delegates**: SSH to target to check certificate files
- **Sets fact**: `cert_renewal_decisions` (dict mapping hostname → boolean for renewal needed)

### vault_cert_inventory_update
- **Context**: Runs on localhost (AAP Execution Environment)
- **Purpose**: Updates centralized certificate inventory in Vault KV after issuance
- **KV Path**: `secrets/certificates/{hostname}`

## Key Variables

### Global Variables
- `vault_server_address`: Vault server URL (default: `https://vault.hashicorp.local:8200`)
- `vault_pki_mount_path`: PKI engine mount path (default: `pki`)
- `target_domain`: Domain suffix for FQDNs (default: `hashicorp.local`)

### Vault Agent Pattern Variables
- `vault_tpm_simplified`: Use openssl instead of TPM (default: `true`)
- `vault_agent_install_binary`: Install Vault binary (default: `true`)
- `vault_agent_setup_tls`: Configure TLS auth (default: `false`)

### Direct PKI Issuance Variables
- `cert_ttl`: Certificate TTL (default: `168h` / 7 days)
- `cert_renewal_threshold_days`: Renew if expiring within N days (default: `5`)
- `cert_file_path`: Certificate location (default: `/etc/pki/tls/certs/{fqdn}.crt`)
- `key_file_path`: Private key location (default: `/etc/pki/tls/private/{fqdn}.key`)

### AAP Credentials (AppRole)
Required in AAP Execution Environment for Vault authentication:
- `role_id`: Vault AppRole role ID (injected by AAP credential)
- `secret_id`: Vault AppRole secret ID (injected by AAP credential)

## Multi-Play Playbook Pattern

Both main playbooks use a **context-switching pattern** where plays alternate between `hosts: all` (target machines) and `hosts: localhost` (AAP Execution Environment):

```yaml
# Play 1: Run on target machines
- hosts: all
  become: true
  roles: [vault_tpm]

# Play 2: Run on AAP EE (authenticates to Vault)
- hosts: localhost
  tasks:
    - include_role: vault_sign
      loop: "{{ groups['all'] }}"
      vars:
        target_hostname: "{{ item }}"

# Play 3: Run on target machines
- hosts: all
  become: true
  roles: [vault_agent]
```

This pattern solves the "chicken-and-egg" problem: target machines don't have Vault credentials until after bootstrap.

## Important Implementation Details

### Certificate File Permissions
- Certificates: `0644` (world-readable)
- Private keys: `0600` (owner-only)
- All files: `root:root` ownership

### Standard RHEL Certificate Locations
- `/etc/pki/tls/certs/` - Certificates
- `/etc/pki/tls/private/` - Private keys

### Vault Agent Configuration
- Config file: `/etc/vault.d/vault-agent-config.hcl`
- Service file: `/etc/systemd/system/vault-agent.service`
- TLS auth certificates: `/etc/vault.d/cert.pem`, `/etc/vault.d/key.pem`

### Conditional Certificate Renewal Logic
The `issue-pki-certificate.yml` playbook uses a fact-based decision system:
1. Discovery role checks certificate expiry and sets `cert_renewal_decisions[hostname] = true/false`
2. Issuance role uses `when: cert_renewal_decisions[item] | default(true)` to conditionally execute
3. Inventory update role runs only for renewed certificates

### Error Handling
- Vault health checks: Accept both status codes 200 (active) and 473 (standby)
- Connection retries: Most Vault API calls have `retries: 3-4` with `delay: 5`
- SSL verification: Always `validate_certs: true` with explicit `ca_path` or `ca_cert`

## Choosing Between Patterns

| Factor | Vault Agent | Direct Issuance |
|--------|-------------|-----------------|
| OS Access | Full (systemd, packages) | Limited or none |
| Rotation | Automatic (background) | Manual/scheduled |
| Complexity | Higher (agent + service) | Lower (one playbook) |
| Vault Clients | N targets = N clients | AAP = 1 client |
| Use Case | Dynamic workloads, VMs | Network devices, appliances |

## Common Troubleshooting

### Vault CA Certificate Issues
If SSL verification fails, ensure Vault CA is installed:
```bash
# On AAP Execution Environment
ls -l /etc/pki/ca-trust/source/anchors/vault-ca.crt
update-ca-trust
```

### AppRole Credentials Not Found
Ensure AAP credential is properly configured and injected:
```yaml
# Check in playbook debug
- debug:
    msg: "role_id={{ role_id | default('NOT SET') }}"
```

### Vault Agent Not Renewing Certificates
Check systemd service status and logs:
```bash
systemctl status vault-agent
journalctl -u vault-agent -f
```

### CSR Signing Fails
Verify the vault_sign role can reach Vault and has valid AppRole credentials. Check that the Vault CA certificate is trusted by the execution environment.
