# Security Policy

## Reporting

Do not open a public issue containing credentials, production connection strings, database dumps,
customer data, private metrics, or exploit details. Use GitHub private vulnerability reporting when
available.

Include the affected revision, impact, minimal reproduction, and sanitized evidence. Replace hosts,
tenant identifiers, and data values when their exact values are not required.

## Supported versions

This engineering lab supports the latest revision of the default branch. It is not a hosted
service and does not publish long-term support releases.

## Deployment warning

The Compose environment uses local fixture credentials, published development ports, unencrypted
container-network traffic, a non-durable Redis configuration, and process-local stale data.
Production use requires managed secrets, TLS, private networking, encryption at rest, least-
privilege database roles, durable telemetry, authenticated administration, tested recovery
objectives, capacity evidence, and independent security and reliability reviews.
