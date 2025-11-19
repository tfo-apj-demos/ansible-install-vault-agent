sequenceDiagram
    autonumber
    actor User
    participant AAP as AAP Execution Environment<br/>(Trusted Orchestrator)
    participant Vault as HashiCorp Vault<br/>(PKI Engine)
    participant Target as Target Machine<br/>(web-server-01)

    User->>AAP: Trigger playbook:<br/>issue-pki-certificate.yml
    
    Note over AAP: Play 1: Gather Facts
    AAP->>Target: SSH: Gather system facts
    Target-->>AAP: Return ansible_fqdn, hostname
    AAP->>AAP: Construct FQDN:<br/>web-server-01.hashicorp.local
    
    Note over AAP,Vault: Play 2: Issue Certificate (localhost)
    AAP->>Vault: Authenticate using AppRole<br/>(role_id + secret_id)
    Vault-->>AAP: Return authentication token
       
    AAP->>Vault: Issue certificate:<br/>POST /v1/pki/issue/server<br/>{common_name: "web-server-01.hashicorp.local",<br/>ttl: "720h"}
    
    Note over Vault: PKI engine validates CN<br/>against role constraints
    
    Vault-->>AAP: Return certificate bundle:<br/>- Certificate (PEM)<br/>- Private Key (PEM)<br/>- CA Certificate<br/>- Certificate Chain<br/>- Serial Number<br/>- Expiration
    
    Note over AAP: Certificate stored in memory<br/>on Execution Environment
    
    AAP->>Target: SSH: Create directories<br/>/etc/pki/tls/certs<br/>/etc/pki/tls/private
    Target-->>AAP: Directories created
    
    AAP->>Target: SCP: Copy certificate<br/>/etc/pki/tls/certs/{fqdn}.crt<br/>(mode: 0644)
    Target-->>AAP: File written
    
    AAP->>Target: SCP: Copy private key<br/>/etc/pki/tls/private/{fqdn}.key<br/>(mode: 0600, owner: root)
    Target-->>AAP: File written (secure)
    
    AAP->>Target: SCP: Copy CA bundle<br/>/etc/pki/tls/certs/{fqdn}-ca.crt<br/>(mode: 0644)
    Target-->>AAP: File written
    
    AAP->>Target: SCP: Copy full chain<br/>/etc/pki/tls/certs/{fqdn}-chain.crt<br/>(mode: 0644)
    Target-->>AAP: File written
    
    AAP->>User: Display summary:<br/>✓ Certificate issued<br/>✓ Files deployed to target<br/>✓ No agent required!
    
    Note over AAP,Target: Key Benefits:<br/>- Perfect for network devices<br/>- No agent installation possible/needed<br/>- Ideal for appliances with limited OS access<br/>- Simple certificate rotation via automation
