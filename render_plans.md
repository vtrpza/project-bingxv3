# Render Plans Reference (2025)

## PostgreSQL Database Plans

According to Render's current documentation, the new PostgreSQL plans are:

### Current Plans:
- `free` - Free plan with limitations (90 days expiry)
- `basic` - Basic paid plan
- `pro` - Professional plan
- `business` - Business plan

### Deprecated Plans (No longer supported):
- `starter` - Legacy plan
- `standard` - Legacy plan

## Redis Plans

### Current Plans:
- `free` - Free plan with limitations
- `starter` - Basic paid plan
- `pro` - Professional plan

## Web Service Plans

### Current Plans:
- `free` - Free plan with limitations
- `starter` - Basic paid plan ($7/month)
- `standard` - Standard plan ($25/month)
- `pro` - Professional plan ($85/month)

## Worker Plans

### Current Plans:
- `free` - Free plan with limitations
- `starter` - Basic paid plan ($7/month)
- `standard` - Standard plan ($25/month)

## Recommended Configuration for BingX Trading Bot

```yaml
services:
  # Main web service
  - type: web
    plan: starter  # $7/month - sufficient for API endpoints

  # Workers
  - type: worker
    plan: starter  # $7/month each - for background processing

  # Redis
  - type: redis
    plan: free     # Free plan should be sufficient for caching

databases:
  # PostgreSQL
  - plan: basic    # First paid plan for production use
```

## Notes

- Free plans have limitations and may not be suitable for production
- Database plans are separate from service plans
- Consider using `basic` plan for PostgreSQL in production
- Monitor usage and upgrade as needed