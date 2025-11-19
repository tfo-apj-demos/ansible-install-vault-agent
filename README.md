# Ansible Vault Agent & PKI Certificate Management

Ansible playbooks and roles for deploying HashiCorp Vault Agent with TLS authentication and issuing PKI certificates to target systems.

## 📋 Overview

This repository contains two main workflows for certificate management with HashiCorp Vault:

1. **Vault Agent with TLS Authentication** - Full agent installation with automatic certificate renewal
2. **Direct PKI Certificate Issuance** - Simple certificate deployment without agent complexity (ideal for network devices)

## 🎯 Use Cases

### Vault Agent Pattern (`install-vault-agent-complete.yml`)
- **Best for:** Linux servers, VMs, workloads with full OS access
- **Benefits:** Automatic certificate renewal, background service, dynamic secrets
- **Architecture:** Agent runs on target, authenticates with TLS certs, manages lifecycle


### Direct PKI Issuance Pattern (`issue-pki-certificate.yml`)
- **Best for:** Network devices (routers, switches, firewalls), appliances, embedded systems
- **Benefits:** No agent installation, simple deployment, orchestrator-based
- **Architecture:** AAP authenticates to Vault, issues certs, copies to targets via SSH

## 📁 Repository Structure

```
ansible-install-vault-agent/
├── playbooks/                           # Main playbooks
│   ├── install-vault-agent-complete.yml # Full Vault Agent setup with TLS auth
│   ├── issue-pki-certificate.yml        # Simple PKI cert issuance (no agent)
│   └── requirements.yml                 # Ansible Galaxy dependencies
│
├── playbooks/roles/                     # Ansible roles
│   ├── vault_agent/                     # Vault Agent installation & config
│   ├── vault_pki_issue/                 # Direct PKI certificate issuance
│   ├── vault_sign/                      # CSR signing via Vault
│   ├── vault_tpm/                       # TPM/software key generation
│   └── vault_tls_auth/                  # TLS authentication setup
│
└── diagrams/                            # Architecture diagrams (Mermaid)
    ├── install-vault-agent-complete.md  # Agent-based flow
    └── issue-pki-certificate.md         # Direct issuance flow
```

## 🚀 Quick Start

### Prerequisites

- Ansible 2.9+
- HashiCorp Vault with PKI engine configured
- AAP/AWX with Vault AppRole credentials configured
- Target systems accessible via SSH

### Install Dependencies

```bash
ansible-galaxy collection install -r playbooks/requirements.yml
```

### Pattern 1: Vault Agent with TLS Authentication

```bash
# Full end-to-end Vault Agent setup
ansible-playbook playbooks/install-vault-agent-complete.yml \
  -e vault_server_address=https://vault.example.com:8200 \
  -e target_domain=example.com
```

**This playbook will:**
1. Generate private key and CSR on target
2. Sign CSR with Vault PKI (tls-auth role)
3. Install Vault Agent binary
4. Configure TLS authentication
5. Set up automatic certificate renewal

### Pattern 2: Direct PKI Certificate Issuance

```bash
# Simple certificate issuance without agent
ansible-playbook playbooks/issue-pki-certificate.yml \
  -e vault_server_address=https://vault.example.com:8200 \
  -e target_domain=example.com
```

**This playbook will:**
1. Authenticate to Vault from AAP Execution Environment
2. Issue certificate for target FQDN
3. Copy certificate files to target machine
4. Place in standard RHEL locations (`/etc/pki/tls/`)

## 🔐 Vault Configuration Requirements

### PKI Roles Required

1. **tls-auth** - For Vault Agent TLS authentication certificates
   - Used by: `install-vault-agent-complete.yml`
   - Purpose: Authentication to Vault

2. **server** - For application/service certificates
   - Used by: `issue-pki-certificate.yml` and Vault Agent templates
   - Purpose: TLS certificates for services (web servers, databases, etc.)

### Authentication Methods

- **AppRole** - Used by AAP Execution Environment to authenticate
- **TLS Certificate** - Used by Vault Agent (after initial setup)

## 📊 Architecture Diagrams

Visual workflows are available in the `diagrams/` directory:

- **[install-vault-agent-complete.md](diagrams/install-vault-agent-complete.md)** - Vault Agent setup flow
- **[issue-pki-certificate.md](diagrams/issue-pki-certificate.md)** - Direct PKI issuance flow

View these as sequence diagrams using Mermaid-compatible tools (GitHub, Mermaid Live Editor, etc.)

## 🔧 Configuration Variables

### Common Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `vault_server_address` | `https://vault.example.local:8200` | Vault server URL |
| `vault_pki_mount_path` | `pki` | PKI secrets engine mount path |
| `target_domain` | `hashicorp.local` | Domain suffix for FQDNs |

### Vault Agent Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `vault_tpm_simplified` | `true` | Use software keys instead of TPM |
| `vault_agent_install_binary` | `true` | Install Vault Agent binary |
| `vault_agent_setup_tls` | `true` | Configure TLS authentication |

### PKI Issuance Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `cert_ttl` | `720h` | Certificate TTL (30 days) |
| `cert_file_path` | `/etc/pki/tls/certs/{fqdn}.crt` | Certificate location |
| `key_file_path` | `/etc/pki/tls/private/{fqdn}.key` | Private key location |

## 🎓 Choosing the Right Pattern

| Factor | Vault Agent | Direct Issuance |
|--------|-------------|-----------------|
| **OS Access** | Full (systemd, packages) | Limited or none |
| **Rotation** | Automatic | Manual/scheduled |
| **Complexity** | Higher (agent setup) | Lower (one playbook) |
| **Use Case** | Dynamic workloads | Static infrastructure |
| **Examples** | App servers, VMs | Routers, switches, appliances |
| **Vault Clients** | N targets = N clients | AAP = 1 client |


## 🔗 Related Resources

- [HashiCorp Vault Documentation](https://developer.hashicorp.com/vault)
- [Vault PKI Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/pki)
- [Vault Agent](https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent)
- [Ansible Automation Platform](https://www.redhat.com/en/technologies/management/ansible)