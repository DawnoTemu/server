# Sentry Setup Guide

This guide explains how to set up Sentry error monitoring and performance tracking for the DawnoTemu application.

## Overview

Sentry provides real-time error tracking and performance monitoring for the Flask application and Celery workers. It automatically captures:

- Unhandled exceptions and errors (both web and background tasks)
- Request performance data
- User context and request information
- Stack traces and debugging information
- Celery task failures and performance

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

### Web Application (Flask)
- Automatic capture of unhandled exceptions
- Manual error reporting with `sentry_sdk.capture_exception()`
- Request context and user information
- Performance monitoring for HTTP requests

### Background Tasks (Celery)
- Automatic capture of Celery task failures
- Task performance monitoring
- Task context and arguments
- Retry mechanism integration

### Data Collection
- Request headers and IP addresses (configurable)
- User context and session information
- Environment and release information
- Task-specific context and metadata

## Configuration Options

### Flask Application
The Sentry SDK is configured in `app.py` with the following settings:

```python
sentry_sdk.init(
    dsn=Config.SENTRY_DSN,
    send_default_pii=True,  # Include request headers and IP
    traces_sample_rate=1.0,  # Capture 100% of transactions
    integrations=[FlaskIntegration()],
)
```

### Celery Workers
The Sentry SDK is configured in `celery_worker.py` and `tasks/__init__.py`:

```python
sentry_sdk.init(
    dsn=Config.SENTRY_DSN,
    send_default_pii=True,
    traces_sample_rate=1.0,
    integrations=[CeleryIntegration()],
)
```

### Adjusting Settings

For production, consider adjusting these settings:

- **`traces_sample_rate`**: Reduce from 1.0 to 0.1 to capture 10% of transactions
- **`send_default_pii`**: Set to False if you don't want to collect PII data
- **`environment`**: Add environment-specific configuration

## Testing

### Web Application Testing
A test route is available at `/test-sentry` that intentionally raises an error to verify the integration.

### Celery Task Testing
You can test Celery integration by creating a simple test task:

```python
from celery import current_app

@current_app.task
def test_sentry_celery():
    raise ValueError("Test error for Sentry Celery integration")

# Queue the test task
result = test_sentry_celery.delay()
```

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
- Celery task failures and performance

### Alerts
Configure alerts for:
- High error rates
- Performance degradation
- New error types
- Celery task failures

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

### Celery Integration Issues
- Ensure Celery workers are started with Sentry integration
- Check that `sentry-sdk[celery]` is installed
- Verify task failures are being captured

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
6. **Task Monitoring**: Monitor Celery task performance and failure rates
7. **Error Handling**: Implement proper error handling in Celery tasks

## Support

For Sentry-specific issues, refer to the [Sentry documentation](https://docs.sentry.io/platforms/python/flask/) and [Celery integration guide](https://docs.sentry.io/platforms/python/celery/).

For application-specific issues, check the application logs and error handling. 