# Security policy

## Supported versions

Security fixes are provided for the latest release of PDFeditorAthome.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository. Do not open a public issue containing an exploit, a sensitive document, credentials, or other confidential material.

Include the affected version, reproduction steps, security impact, and any suggested mitigation. Reports will be reviewed before public disclosure.

## Security model

PDFeditorAthome binds its local web server to `127.0.0.1`, limits imports to 50 MB, validates supported file extensions, and keeps imported previews in process memory. Release dependencies are pinned and audited, source is scanned with multiple static-analysis tools, GitHub Actions are SHA-pinned with minimal permissions, and each packaged executable receives a SHA-256 checksum.

The current executable is not Authenticode code-signed. A checksum detects accidental or malicious changes only when the checksum itself is obtained from the trusted GitHub Release page; it does not establish publisher identity.
