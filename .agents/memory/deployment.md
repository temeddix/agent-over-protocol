# Deployment

Production deployment is expected to run through Compose/Portainer.

- Real server environment variables should be supplied by `compose.yaml` or
  Portainer environment configuration.
- Do not commit real provider keys or production secrets.
- `tests/.env.template` is test-only and should contain dummy values.
