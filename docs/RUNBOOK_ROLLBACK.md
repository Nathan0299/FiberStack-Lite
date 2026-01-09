# Rollback Runbook

**Document Status:** Frozen (v1.0.0-mvp)  
**Last Updated:** 2026-01-09

---

## Purpose

This runbook provides step-by-step procedures for rolling back FiberStack-Lite in case of production issues or failed deployments.

---

## Scenario 1: Hotfix Breaks Frozen Branch

### Symptoms
- CI/CD gates failing after merge
- Application crashes or behaves unexpectedly after deployment

### Procedure

1. **Identify the bad commit**
   ```bash
   git log --oneline -10
   # Find the commit that broke the build
   ```

2. **Revert the commit**
   ```bash
   git revert <bad_commit_hash>
   git push origin release/mvp
   ```

3. **Isolate the fix**
   ```bash
   # Create hotfix branch from last known good tag
   git checkout v1.0.0-mvp
   git checkout -b hotfix/fix-description
   ```

4. **Apply fix and test**
   ```bash
   # Make fixes
   # Run local tests
   docker-compose -f fiber-deploy/docker-compose.dev.yml up -d
   curl http://localhost:8000/api/status
   ```

5. **Cherry-pick to release branch**
   ```bash
   git checkout release/mvp
   git cherry-pick <fixed_commit_hash>
   git push origin release/mvp
   ```

6. **Re-tag if necessary**
   ```bash
   git tag -s v1.0.1-mvp -m "Hotfix: <description>"
   git push origin v1.0.1-mvp
   ```

---

## Scenario 2: Production Regression

### Symptoms
- Dashboard not loading
- API returning 500 errors
- Probes not reporting data

### Immediate Actions

1. **Stop current deployment**
   ```bash
   docker-compose -f fiber-deploy/docker-compose.dev.yml down
   ```

2. **Rollback to last known good version**
   ```bash
   git checkout v1.0.0-mvp
   docker-compose -f fiber-deploy/docker-compose.dev.yml up -d
   ```

3. **Restore database (if corrupted)**
   ```bash
   # List available backups
   ls -la backups/
   
   # Restore from backup
   pg_restore --clean -h localhost -U postgres -d fiberstack backups/v1.0.0-mvp.dump
   ```

4. **Verify recovery**
   ```bash
   # Check API
   curl http://localhost:8000/api/status
   
   # Check probe count
   curl http://localhost:8000/api/metrics | jq 'length'
   
   # Check dashboard
   open http://localhost:4000
   ```

5. **Notify stakeholders**
   - Post to `#fiberstack-ops` Slack channel
   - Create incident report

---

## Scenario 3: Database Migration Failure

### Symptoms
- Alembic migration fails
- Tables missing or corrupted

### Procedure

1. **Check migration status**
   ```bash
   docker exec fiber-api alembic current
   docker exec fiber-api alembic history
   ```

2. **Downgrade to previous migration**
   ```bash
   docker exec fiber-api alembic downgrade -1
   ```

3. **Fix migration script and retry**
   ```bash
   # Edit migration in fiber-db/migrations/
   docker exec fiber-api alembic upgrade head
   ```

---

## Post-Incident Checklist

- [ ] Root cause identified
- [ ] Fix applied and tested
- [ ] Incident report created
- [ ] Runbook updated if needed
- [ ] Stakeholders notified of resolution

---

## Emergency Contacts

| Role | Contact |
|------|---------|
| Project Lead | nathaniellamptey17@gmail.com |
| Ops On-Call | TBD |
