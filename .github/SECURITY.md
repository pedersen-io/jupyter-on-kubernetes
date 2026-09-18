# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities privately to the maintainers.
Include:

- A clear description of the issue
- Reproduction steps
- Potential impact
- Suggested mitigation (if available)

Do not open public issues for unpatched vulnerabilities.

## Secrets and Credentials

- Never commit OAuth client secrets, service account keys, or kubeconfig files.
- Kubernetes secret values should be created and managed outside of source control.
- CI credentials must be stored in Jenkins credentials or repository secret storage.

## Container and Dependency Hygiene

- Keep base images current via Dependabot updates.
- Rebuild and redeploy images when upstream security fixes are published.
