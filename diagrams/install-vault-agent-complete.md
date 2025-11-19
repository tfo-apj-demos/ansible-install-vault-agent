sequenceDiagram
    participant AAP as Ansible Automation<br/>Platform
    participant VM as RHEL9 VM
    participant Agent as Vault Agent
    participant Vault as HashiCorp Vault
    participant EDA as AAP Event-Driven<br/>Ansible
    participant App as Application

    rect rgb(240, 240, 255)
        Note over AAP,VM: Phase 1: Bootstrap
        AAP->>VM: Run install playbook
        VM->>VM: Generate private key & CSR
        VM->>Vault: Sign CSR (via AAP EE)
        Vault-->>VM: Return signed cert.pem
        VM->>Agent: Install & configure Vault Agent
        Agent->>Agent: Start service
    end

    rect rgb(255, 250, 240)
        Note over Agent,Vault: Phase 2: Authentication
        Agent->>Vault: TLS cert auth (cert.pem)
        Vault-->>Agent: Vault token
        Agent->>Agent: Write token to file sink
    end

    rect rgb(240, 255, 240)
        Note over Agent,App: Phase 3: Initial Provisioning
        Agent->>Vault: Request app certificate (pkiCert)
        Vault-->>Agent: app-cert.pem + key + CA
        Agent->>Agent: Write certificates to files
        App->>App: Load certificates
    end

    rect rgb(255, 245, 245)
        Note over Agent,AAP: Phase 4: Automated Renewal
        loop Every 24h
            Agent->>Vault: Renew app certificate
            Vault-->>Agent: New app-cert.pem + key + CA
            Agent->>Agent: Update certificate files
            Agent->>Vault: Write renewal metadata to KV
            Vault->>EDA: Emit kv-v2/data-write event
            EDA->>AAP: Trigger job template
            AAP->>VM: Reload service (SIGHUP/API)
            VM->>App: Reload TLS config
            App-->>AAP: Health check OK
        end
    end

    rect rgb(255, 240, 240)
        Note over AAP,VM: Phase 5: Failure Recovery
        alt Health Check Fails
            VM->>VM: Revert to previous cert
            VM->>App: Reload with backup cert
            App-->>AAP: Health OK (rolled back)
        else No Backup
            AAP->>AAP: Raise incident & skip node
        end
    end

    rect rgb(245, 245, 255)
        Note over Agent,Vault: Phase 6: Continuous Operation
        loop Background
            Agent->>Vault: Renew token
            Vault-->>Agent: Renewed token
        end
    end