# Sentry Setup Guide

This guide explains how to set up Sentry error monitoring and performance tracking for the DawnoTemu application.

## Overview

Sentry provides real-time error tracking and performance monitoring for the Flask application. It automatically captures:

- Unhandled exceptions and errors
- Request performance data
- User context and request information
- Stack traces and debugging information

## Configuration

### 1. Environment Variable

Set the `SENTRY_DSN` environment variable with your Sentry project DSN:

```bash
# Development
export SENTRY_DSN="https://your-sentry-dsn@sentry.io/your-project-id"

# Production (Heroku)
heroku config:set SENTRY_DSN="https://your-sentry-dsn@sentry.io/your-project-id"
```

### 2. Local Development

For local development, you can create a `.env` file in the project root:

```env
SENTRY_DSN=https://your-sentry-dsn@sentry.io/your-project-id
```

The application automatically loads environment variables from `.env` files using `python-dotenv`.

## Features

### Error Tracking
- Automatic capture of unhandled exceptions
- Manual error reporting with `sentry_sdk.capture_exception()`
- Request context and user information

### Performance Monitoring
- Request traces and timing
- Database query performance
- External API call monitoring

### Data Collection
- Request headers and IP addresses (configurable)
- User context and session information
- Environment and release information

## Configuration Options

The Sentry SDK is configured with the following settings:

```python
sentry_sdk.init(
    dsn=Config.SENTRY_DSN,
    send_default_pii=True,  # Include request headers and IP
    traces_sample_rate=1.0,  # Capture 100% of transactions
    integrations=[FlaskIntegration()],
)
```

### Adjusting Settings

For production, consider adjusting these settings:

- **`traces_sample_rate`**: Reduce from 1.0 to 0.1 to capture 10% of transactions
- **`send_default_pii`**: Set to False if you don't want to collect PII data
- **`environment`**: Add environment-specific configuration

## Testing

### Test Route
A test route is available at `/test-sentry` that intentionally raises an error to verify the integration.

### Manual Testing
You can manually capture errors in your code:

```python
import sentry_sdk

try:
    # Your code here
    pass
except Exception as e:
    sentry_sdk.capture_exception(e)
```

## Monitoring

### Dashboard
Access your Sentry dashboard to view:
- Error rates and trends
- Performance metrics
- User impact analysis
- Release health

### Alerts
Configure alerts for:
- High error rates
- Performance degradation
- New error types

## Security Considerations

- The DSN is safe to include in client-side code
- PII data collection is configurable
- Environment variables keep secrets secure
- Sentry automatically filters sensitive data

## Troubleshooting

### Sentry Not Initializing
- Check that `SENTRY_DSN` environment variable is set
- Verify the DSN format is correct
- Check application logs for initialization messages

### No Data in Dashboard
- Ensure the DSN points to the correct project
- Check network connectivity to Sentry
- Verify the application is generating errors/requests

### Performance Impact
- Adjust `traces_sample_rate` to reduce overhead
- Monitor application performance metrics
- Consider disabling in development if needed

## Best Practices

1. **Environment Separation**: Use different Sentry projects for development, staging, and production
2. **Release Tracking**: Tag releases to track error rates per version
3. **User Context**: Add user information to errors for better debugging
4. **Custom Context**: Add relevant business data to error reports
5. **Regular Monitoring**: Check Sentry dashboard regularly for new issues

## Support

For Sentry-specific issues, refer to the [Sentry documentation](https://docs.sentry.io/platforms/python/flask/).

For application-specific issues, check the application logs and error handling. 