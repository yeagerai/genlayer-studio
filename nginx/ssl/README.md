# Directory for TLS Certificates and Keys

Place your TLS (Transport Layer Security) certificates and private keys for NGINX in this directory. These files are essential for enabling HTTPS, ensuring secure communication, and authenticating server identity. Make sure to use the correct certificate/private key pair for the domain you are running the studio on.

## Required Files
Ensure the following files are correctly placed in the specified directory (`/etc/nginx/ssl`):

- **Server certificate**: `genlayer.com.crt`
- **Private key**: `genlayer.com.key`
- **Client certificate**: `cloudflare.crt`

## File Permissions
Permissions should follow these guidelines:

- **Certificates** (`.crt` or `.pem`): `chmod 644`
- **Private keys** (`.key`): `chmod 600`

## Configuration Alignment
Verify that the NGINX configuration matches the expected file names and locations:

```nginx
ssl_certificate /etc/nginx/ssl/genlayer.com.crt;
ssl_certificate_key /etc/nginx/ssl/genlayer.com.key;
ssl_client_certificate /etc/nginx/ssl/cloudflare.crt;
