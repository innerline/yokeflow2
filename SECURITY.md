# Security Policy

## Security Considerations

### Sandbox Execution

YokeFlow executes AI-generated code in sandboxed environments:

- **Docker Sandbox** (default): Isolated containers with resource limits
- **Local Execution**: Uses command blocklist for safety

**Security measures:**
- Command blocklist prevents dangerous operations (`rm -rf`, `sudo`, etc.)
- Resource limits prevent DoS attacks
- Network isolation available via Docker
- File system restrictions via Docker volumes

See [core/security.py](core/security.py) for implementation details.

### API Authentication

The API server includes JWT-based authentication:

- **Development mode**: Authentication disabled by default (for local use)
- **Production mode**: Requires `UI_PASSWORD` environment variable
- **Token expiration**: Configurable (default 24 hours)

**Production deployment checklist:**
```bash
# Set in .env file
UI_PASSWORD=your-secure-password-here
SECRET_KEY=$(openssl rand -hex 32)
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### Database Security

YokeFlow uses PostgreSQL with standard security practices:

- **Parameterized queries**: Prevents SQL injection (via asyncpg)
- **Connection pooling**: Limits database connections
- **Password protection**: Database credentials in .env file
- **SSL support**: Available for production deployments

**Production recommendations:**
- Use managed database services (Digital Ocean, AWS RDS)
- Enable SSL/TLS for database connections
- Use strong passwords (16+ characters)
- Rotate credentials regularly
- Limit database user permissions to minimum required

### Environment Variables

Sensitive data is stored in `.env` files:

```bash
# NEVER commit these to git
CLAUDE_CODE_OAUTH_TOKEN=your_token
DATABASE_URL=postgresql://user:pass@host:port/db
SECRET_KEY=your_secret_key
UI_PASSWORD=your_password
```

**Protection measures:**
- `.env` files are in `.gitignore`
- `.env.example` provides template without secrets
- Environment variables loaded securely via python-dotenv

### Generated Code Security

YokeFlow generates code via AI agents. Security considerations:

**Agent capabilities:**
- Agents can execute arbitrary code in sandboxes
- Agents have access to specified environment variables
- Agents can make network requests (if allowed)
- Agents can modify generated project files

**Your responsibilities:**
1. **Review generated code** before production deployment
2. **Validate dependencies** in package.json/requirements.txt
3. **Audit environment variables** passed to generated apps
4. **Test thoroughly** in isolated environments first
5. **Monitor for unexpected behavior**

**Built-in protections:**
- Session logs capture all agent actions
- Browser verification validates functionality
- Quality reviews check for common issues
- Git commits provide audit trail

### Known Limitations

1. **Docker required for full isolation**: Local execution uses blocklist only
2. **AI-generated code**: May contain security issues, always review
3. **Environment variables**: Passed to Docker containers as-is
4. **Network access**: Containers can make external requests by default

### Best Practices

For secure YokeFlow deployments:

#### Local Development
- Use Docker sandbox mode (default)
- Keep `.env` file secure and private
- Review generated code before running
- Don't expose API server to public internet

#### Production Deployment
- Enable authentication (`UI_PASSWORD` set)
- Use managed PostgreSQL with SSL
- Deploy behind reverse proxy (nginx, Caddy)
- Set strong `SECRET_KEY` (32+ random bytes)
- Configure CORS to restrict origins
- Use HTTPS/WSS for all connections
- Regular security updates
- Monitor logs for suspicious activity
- Backup database regularly

#### Multi-User Environments
- Implement per-user authentication (future feature)
- Isolate user projects (separate databases/containers)
- Rate limit API requests
- Audit all user actions
- Restrict file system access

## Security Features

### Command Blocklist

The security module blocks dangerous commands:

```python
# See core/security.py
BLOCKED_COMMANDS = [
    'rm', 'sudo', 'chmod', 'chown',
    'apt', 'yum', 'pip install', 'npm install -g',
    # ... and more
]
```

**How it works:**
- All bash commands validated before execution
- Blocked commands return error immediately
- Safe commands (git, npm run, curl) allowed
- Designed for autonomous operation with safety

**Customization:**
Edit `core/security.py` to add/remove blocked commands based on your needs.

### Resource Limits

Docker containers have built-in resource limits:

```yaml
# See Dockerfile.agent-sandbox
- Memory limit: 2GB default
- CPU limit: Configurable
- Network: Isolated by default
- File system: Volume-mounted only
```

### Session Isolation

Each session runs in isolated context:
- Separate working directory
- Independent environment variables
- Isolated git repository
- Dedicated Docker container (when using sandbox mode)

---

**Last Updated:** December 24, 2025
