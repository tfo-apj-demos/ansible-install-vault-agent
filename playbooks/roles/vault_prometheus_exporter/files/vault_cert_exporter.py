#!/usr/bin/env python3
"""
Vault Certificate Prometheus Exporter

Queries Vault KV for certificate inventory and exposes metrics for Prometheus.
Designed to integrate with Grafana for real-time certificate lifecycle monitoring.

Usage:
    python3 vault_cert_exporter.py --vault-addr https://vault.example.com:8200 \
                                    --role-id $ROLE_ID \
                                    --secret-id $SECRET_ID \
                                    --port 9090

Metrics Exposed:
    vault_certificate_days_until_expiry{hostname,cn,serial} - Days until certificate expires
    vault_certificate_renewal_needed{hostname,cn} - 1 if renewal needed, 0 otherwise
    vault_certificate_status{hostname,cn,status} - Certificate status (0-3: healthy/warning/critical/expired)
    vault_certificate_last_scanned_timestamp{hostname,cn} - Unix timestamp of last scan
    vault_certificates_total - Total number of certificates tracked
    vault_certificates_by_status{status} - Count of certificates by status

"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Dict, List, Optional

try:
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.retry import Retry
except ImportError:
    print("ERROR: 'requests' module not found. Install with: pip3 install requests", file=sys.stderr)
    sys.exit(1)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('vault_cert_exporter')


class VaultClient:
    """Vault API client for certificate inventory queries"""

    def __init__(self, vault_addr: str, role_id: str, secret_id: str, ca_cert: Optional[str] = None):
        self.vault_addr = vault_addr.rstrip('/')
        self.role_id = role_id
        self.secret_id = secret_id
        self.ca_cert = ca_cert
        self.token = None
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic"""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def authenticate(self) -> bool:
        """Authenticate to Vault using AppRole"""
        try:
            url = f"{self.vault_addr}/v1/auth/approle/login"
            payload = {
                "role_id": self.role_id,
                "secret_id": self.secret_id
            }

            response = self.session.post(
                url,
                json=payload,
                verify=self.ca_cert if self.ca_cert else True,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            self.token = data['auth']['client_token']
            logger.info("Successfully authenticated to Vault")
            return True

        except Exception as e:
            logger.error(f"Vault authentication failed: {e}")
            return False

    def list_certificates(self) -> List[str]:
        """List all certificate inventory keys from Vault KV"""
        try:
            url = f"{self.vault_addr}/v1/secrets/metadata/certificates"
            headers = {"X-Vault-Token": self.token}

            response = self.session.request(
                "LIST",
                url,
                headers=headers,
                verify=self.ca_cert if self.ca_cert else True,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            keys = data.get('data', {}).get('keys', [])
            logger.info(f"Found {len(keys)} certificate inventories in Vault KV")
            return keys

        except Exception as e:
            logger.error(f"Failed to list certificates: {e}")
            return []

    def get_certificate(self, hostname: str) -> Optional[Dict]:
        """Retrieve certificate inventory for specific hostname"""
        try:
            url = f"{self.vault_addr}/v1/secrets/data/certificates/{hostname}"
            headers = {"X-Vault-Token": self.token}

            response = self.session.get(
                url,
                headers=headers,
                verify=self.ca_cert if self.ca_cert else True,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            return data.get('data', {}).get('data', {})

        except Exception as e:
            logger.warning(f"Failed to get certificate for {hostname}: {e}")
            return None


class CertificateMetrics:
    """Generate Prometheus metrics from certificate data"""

    def __init__(self, warning_days: int = 30, critical_days: int = 7):
        self.warning_days = warning_days
        self.critical_days = critical_days
        self.metrics = []

    def _escape_label(self, value: str) -> str:
        """Escape label values for Prometheus format"""
        return value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    def _determine_status(self, days_until_expiry: int) -> str:
        """Determine certificate status based on expiry"""
        if days_until_expiry <= 0:
            return "expired"
        elif days_until_expiry <= self.critical_days:
            return "critical"
        elif days_until_expiry <= self.warning_days:
            return "warning"
        else:
            return "healthy"

    def _status_to_value(self, status: str) -> int:
        """Convert status string to numeric value"""
        status_map = {
            "healthy": 0,
            "warning": 1,
            "critical": 2,
            "expired": 3
        }
        return status_map.get(status, 0)

    def generate(self, certificates: List[Dict]) -> str:
        """Generate Prometheus metrics from certificate data"""
        self.metrics = []

        # Counters by status
        status_counts = {
            "healthy": 0,
            "warning": 0,
            "critical": 0,
            "expired": 0
        }

        # Add metric headers with descriptions
        self.metrics.append("# HELP vault_certificate_days_until_expiry Days until certificate expires")
        self.metrics.append("# TYPE vault_certificate_days_until_expiry gauge")

        self.metrics.append("# HELP vault_certificate_renewal_needed Certificate renewal needed (1=yes, 0=no)")
        self.metrics.append("# TYPE vault_certificate_renewal_needed gauge")

        self.metrics.append("# HELP vault_certificate_status Certificate status (0=healthy, 1=warning, 2=critical, 3=expired)")
        self.metrics.append("# TYPE vault_certificate_status gauge")

        self.metrics.append("# HELP vault_certificate_last_scanned_timestamp Unix timestamp of last certificate scan")
        self.metrics.append("# TYPE vault_certificate_last_scanned_timestamp gauge")

        # Process each certificate
        for cert_data in certificates:
            hostname = cert_data.get('hostname', 'unknown')
            fqdn = cert_data.get('fqdn', 'unknown')

            cert_list = cert_data.get('certificates', [])
            if not cert_list:
                continue

            cert_info = cert_list[0]
            cn = self._escape_label(cert_info.get('common_name', 'unknown'))
            serial = self._escape_label(cert_info.get('serial_number', 'unknown')[:16])
            days_until_expiry = int(cert_info.get('days_until_expiry', 0))
            renewal_needed = 1 if cert_info.get('renewal_needed', False) else 0

            # Determine status
            status = self._determine_status(days_until_expiry)
            status_counts[status] += 1
            status_value = self._status_to_value(status)

            # Parse last scanned timestamp
            last_scanned = cert_info.get('last_scanned', cert_info.get('last_issued', ''))
            try:
                if last_scanned:
                    ts = int(datetime.fromisoformat(last_scanned.replace('Z', '+00:00')).timestamp())
                else:
                    ts = 0
            except:
                ts = 0

            # Generate metric lines
            labels = f'hostname="{hostname}",cn="{cn}",serial="{serial}"'
            status_labels = f'hostname="{hostname}",cn="{cn}",status="{status}"'

            self.metrics.append(f'vault_certificate_days_until_expiry{{{labels}}} {days_until_expiry}')
            self.metrics.append(f'vault_certificate_renewal_needed{{{labels}}} {renewal_needed}')
            self.metrics.append(f'vault_certificate_status{{{status_labels}}} {status_value}')
            self.metrics.append(f'vault_certificate_last_scanned_timestamp{{{labels}}} {ts}')

        # Add summary metrics
        self.metrics.append("# HELP vault_certificates_total Total number of certificates tracked")
        self.metrics.append("# TYPE vault_certificates_total gauge")
        self.metrics.append(f"vault_certificates_total {len(certificates)}")

        self.metrics.append("# HELP vault_certificates_by_status Count of certificates by status")
        self.metrics.append("# TYPE vault_certificates_by_status gauge")
        for status, count in status_counts.items():
            self.metrics.append(f'vault_certificates_by_status{{status="{status}"}} {count}')

        # Add exporter metadata
        self.metrics.append("# HELP vault_cert_exporter_last_scrape_timestamp Unix timestamp of last successful scrape")
        self.metrics.append("# TYPE vault_cert_exporter_last_scrape_timestamp gauge")
        self.metrics.append(f"vault_cert_exporter_last_scrape_timestamp {int(time.time())}")

        return '\n'.join(self.metrics) + '\n'


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint"""

    vault_client: VaultClient = None
    metrics_generator: CertificateMetrics = None
    cache_duration: int = 60
    cached_metrics: str = ""
    last_scrape: float = 0

    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/metrics':
            self.serve_metrics()
        elif self.path == '/health':
            self.serve_health()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def serve_metrics(self):
        """Serve Prometheus metrics"""
        try:
            # Check cache
            current_time = time.time()
            if current_time - self.last_scrape < self.cache_duration and self.cached_metrics:
                logger.debug("Serving cached metrics")
                metrics = self.cached_metrics
            else:
                # Re-authenticate if needed
                if not self.vault_client.token:
                    if not self.vault_client.authenticate():
                        raise Exception("Vault authentication failed")

                # Fetch certificates
                hostnames = self.vault_client.list_certificates()
                certificates = []

                for hostname in hostnames:
                    cert_data = self.vault_client.get_certificate(hostname)
                    if cert_data:
                        certificates.append(cert_data)

                # Generate metrics
                metrics = self.metrics_generator.generate(certificates)

                # Update cache
                self.__class__.cached_metrics = metrics
                self.__class__.last_scrape = current_time

                logger.info(f"Generated metrics for {len(certificates)} certificates")

            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()
            self.wfile.write(metrics.encode('utf-8'))

        except Exception as e:
            logger.error(f"Error generating metrics: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Error: {str(e)}".encode('utf-8'))

    def serve_health(self):
        """Serve health check endpoint"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        health = {
            "status": "healthy",
            "vault_addr": self.vault_client.vault_addr,
            "last_scrape": self.last_scrape,
            "cache_duration": self.cache_duration
        }
        self.wfile.write(json.dumps(health, indent=2).encode('utf-8'))

    def log_message(self, format, *args):
        """Override to use custom logger"""
        logger.info(f"{self.client_address[0]} - {format % args}")


def main():
    parser = argparse.ArgumentParser(description='Vault Certificate Prometheus Exporter')
    parser.add_argument('--vault-addr', required=True, help='Vault server address')
    parser.add_argument('--role-id', help='Vault AppRole role ID (or set VAULT_ROLE_ID env var)')
    parser.add_argument('--secret-id', help='Vault AppRole secret ID (or set VAULT_SECRET_ID env var)')
    parser.add_argument('--ca-cert', help='Path to Vault CA certificate')
    parser.add_argument('--port', type=int, default=9090, help='Exporter HTTP port (default: 9090)')
    parser.add_argument('--cache-duration', type=int, default=60, help='Metrics cache duration in seconds (default: 60)')
    parser.add_argument('--warning-days', type=int, default=30, help='Warning threshold in days (default: 30)')
    parser.add_argument('--critical-days', type=int, default=7, help='Critical threshold in days (default: 7)')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Log level')

    args = parser.parse_args()

    # Configure logging
    logger.setLevel(getattr(logging, args.log_level))

    # Get credentials
    role_id = args.role_id or os.getenv('VAULT_ROLE_ID')
    secret_id = args.secret_id or os.getenv('VAULT_SECRET_ID')

    if not role_id or not secret_id:
        logger.error("Vault credentials not provided. Use --role-id/--secret-id or set VAULT_ROLE_ID/VAULT_SECRET_ID env vars")
        sys.exit(1)

    # Initialize Vault client
    vault_client = VaultClient(
        vault_addr=args.vault_addr,
        role_id=role_id,
        secret_id=secret_id,
        ca_cert=args.ca_cert
    )

    # Authenticate to Vault
    if not vault_client.authenticate():
        logger.error("Failed to authenticate to Vault. Exiting.")
        sys.exit(1)

    # Initialize metrics generator
    metrics_generator = CertificateMetrics(
        warning_days=args.warning_days,
        critical_days=args.critical_days
    )

    # Set up HTTP handler
    MetricsHandler.vault_client = vault_client
    MetricsHandler.metrics_generator = metrics_generator
    MetricsHandler.cache_duration = args.cache_duration

    # Start HTTP server
    server = HTTPServer(('0.0.0.0', args.port), MetricsHandler)
    logger.info(f"Starting Vault Certificate Exporter on port {args.port}")
    logger.info(f"Metrics endpoint: http://0.0.0.0:{args.port}/metrics")
    logger.info(f"Health endpoint: http://0.0.0.0:{args.port}/health")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down exporter...")
        server.shutdown()


if __name__ == '__main__':
    main()
