# Environment Strategy

Use a two-layer model:

- versioned templates in `env/templates/*.env.example`
- real runtime env files in `/srv/devstack/state/*/config/.env`

The real `.env` files must stay out of source control and should keep `0600` permissions.
