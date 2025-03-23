# StoryVoice API Documentation

This document provides a comprehensive guide to the RESTful API endpoints available for the StoryVoice mobile application. StoryVoice allows users to clone their voice and use it to narrate children's stories.

## Base URL

All API requests should be prefixed with the base URL:

```
https://api.dawnotemu.app
```

For local development:

```
http://localhost:8000
```

## Authentication

The API uses JWT (JSON Web Token) for authentication. Most endpoints require the `Authorization` header with a valid access token.

### Token Format

```
Authorization: Bearer {access_token}
```

Access tokens expire after 15 minutes. Use the refresh token endpoint to obtain a new access token.

## API Endpoints

### Authentication

#### Register a New User

```
POST /auth/register
```

Create a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "secure_password",
  "password_confirm": "secure_password"
}
```

**Response:**
```json
{
  "message": "Registration successful. Please check your email to confirm your account."
}
```

**Status Codes:**
- 201: User created successfully
- 400: Invalid request (missing fields or passwords don't match)
- 409: Email already registered

#### Log In

```
POST /auth/login
```

Authenticate a user and receive JWT tokens.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "user": {
    "id": 1,
    "email": "user@example.com",
    "email_confirmed": true,
    "created_at": "2025-03-19T14:22:35.982Z",
    "last_login": "2025-03-23T14:30:15.651Z"
  }
}
```

**Status Codes:**
- 200: Successfully authenticated
- 400: Missing required fields
- 401: Invalid credentials

#### Refresh Access Token

```
POST /auth/refresh
```

Get a new access token using a refresh token.

**Request Body:**
```json
{
  "refresh_token": "eyJhbGciOi..."
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOi..."
}
```

**Status Codes:**
- 200: New token generated successfully
- 400: Missing refresh token
- 401: Invalid or expired refresh token

#### Get Current User

```
GET /auth/me
```

Get the profile information of the currently authenticated user.

**Headers:**
- Authorization: Bearer {access_token}

**Response:**
```json
{
  "id": 1,
  "email": "user@example.com",
  "email_confirmed": true,
  "created_at": "2025-03-19T14:22:35.982Z",
  "last_login": "2025-03-23T14:30:15.651Z"
}
```

**Status Codes:**
- 200: Success
- 401: Unauthorized (invalid or missing token)

#### Confirm Email

```
GET /auth/confirm-email/{token}
```

Confirm a user's email address using the token sent via email.

**URL Parameters:**
- token: Email confirmation token

**Response:**
```json
{
  "message": "Email confirmed successfully. You can now log in."
}
```

**Status Codes:**
- 200: Email confirmed successfully
- 400: Invalid or expired token

#### Request Password Reset

```
POST /auth/reset-password-request
```

Request a password reset email.

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response:**
```json
{
  "message": "Password reset link has been sent to your email."
}
```

**Status Codes:**
- 200: Request processed (will return success even if email is not registered for security)
- 400: Missing email

#### Reset Password

```
POST /auth/reset-password/{token}
```

Reset a user's password using a token received via email.

**URL Parameters:**
- token: Password reset token

**Request Body:**
```json
{
  "new_password": "new_secure_password",
  "new_password_confirm": "new_secure_password"
}
```

**Response:**
```json
{
  "message": "Password has been reset successfully. You can now log in with your new password."
}
```

**Status Codes:**
- 200: Password reset successfully
- 400: Invalid request or token

### Stories

#### List All Stories

```
GET /stories
```

Get a list of all available stories.

**Response:**
```json
[
  {
    "id": 1,
    "title": "Hansel and Gretel",
    "author": "Brothers Grimm",
    "description": "A classic fairy tale about two children who discover a house made of candy...",
    "cover_path": "/stories/1/cover",
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z"
  },
  {
    "id": 2,
    "title": "Three Little Pigs",
    "author": "Traditional",
    "description": "The tale of three pigs who build houses of different materials...",
    "cover_path": "/stories/2/cover",
    "created_at": "2025-01-16T11:20:00Z",
    "updated_at": "2025-01-16T11:20:00Z"
  }
]
```

**Status Codes:**
- 200: Success
- 500: Server error

#### Get Story Details

```
GET /stories/{story_id}
```

Get the details of a specific story.

**URL Parameters:**
- story_id: ID of the story

**Response:**
```json
{
  "id": 1,
  "title": "Hansel and Gretel",
  "author": "Brothers Grimm",
  "description": "A classic fairy tale about two children who discover a house made of candy...",
  "content": "Once upon a time...",
  "cover_path": "/stories/1/cover",
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:30:00Z"
}
```

**Status Codes:**
- 200: Success
- 404: Story not found

#### Get Story Cover Image

```
GET /stories/{story_id}/cover
```

Get the cover image for a story. This endpoint redirects to a pre-signed URL.

**URL Parameters:**
- story_id: ID of the story

**Response:**
Redirects to the image URL or returns an error JSON if no cover exists.

**Status Codes:**
- 302: Redirected to image
- 404: Cover image not found

### Voices

#### List User's Voices

```
GET /voices
```

Get all voice clones created by the authenticated user.

**Headers:**
- Authorization: Bearer {access_token}

**Response:**
```json
[
  {
    "id": 1,
    "name": "My Voice",
    "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
    "user_id": 1,
    "created_at": "2025-03-20T15:45:22Z",
    "updated_at": "2025-03-20T15:45:22Z"
  }
]
```

**Status Codes:**
- 200: Success
- 401: Unauthorized

#### Create Voice Clone

```
POST /voices
```

Create a new voice clone from an audio sample.

**Headers:**
- Authorization: Bearer {access_token}
- Content-Type: multipart/form-data

**Form Data:**
- file: Audio file (WAV or MP3, maximum 30 seconds)
- name: (Optional) Name for the voice

**Response:**
```json
{
  "id": 1,
  "voice_id": "pNInz6obpgDQGcFmaJgB",
  "name": "My Voice"
}
```

**Status Codes:**
- 200: Voice clone created successfully
- 400: Invalid request (missing file or invalid file type)
- 401: Unauthorized
- 500: Voice cloning failed

#### Get Voice Details

```
GET /voices/{voice_id}
```

Get details of a specific voice clone.

**Headers:**
- Authorization: Bearer {access_token}

**URL Parameters:**
- voice_id: ID of the voice

**Response:**
```json
{
  "id": 1,
  "name": "My Voice",
  "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
  "user_id": 1,
  "created_at": "2025-03-20T15:45:22Z",
  "updated_at": "2025-03-20T15:45:22Z"
}
```

**Status Codes:**
- 200: Success
- 401: Unauthorized
- 403: Forbidden (voice belongs to a different user)
- 404: Voice not found

#### Delete Voice

```
DELETE /voices/{voice_id}
```

Delete a voice clone and all associated audio files.

**Headers:**
- Authorization: Bearer {access_token}

**URL Parameters:**
- voice_id: ID of the voice

**Response:**
```json
{
  "message": "Voice and associated files deleted"
}
```

**Status Codes:**
- 200: Success
- 401: Unauthorized
- 403: Forbidden (voice belongs to a different user)
- 404: Voice not found
- 500: Deletion failed

#### Get Voice Sample

```
GET /voices/{voice_id}/sample
```

Get the original voice sample used for cloning.

**Headers:**
- Authorization: Bearer {access_token}

**URL Parameters:**
- voice_id: ID of the voice

**Query Parameters:**
- redirect: (Optional) If "true", redirects directly to the audio URL

**Response:**
```json
{
  "url": "https://s3.amazonaws.com/storyvoice/samples/..."
}
```

Or redirects to the URL if `redirect=true`.

**Status Codes:**
- 200: Success
- 401: Unauthorized
- 403: Forbidden (voice belongs to a different user)
- 404: Voice or sample not found

### Audio

#### Check Audio Existence

```
HEAD /voices/{elevenlabs_voice_id}/stories/{story_id}/audio
```

Check if audio has been generated for a specific voice and story.

**Headers:**
- Authorization: Bearer {access_token}

**URL Parameters:**
- elevenlabs_voice_id: ElevenLabs ID of the voice
- story_id: ID of the story

**Response:**
No content is returned. Status code indicates existence.

**Status Codes:**
- 200: Audio exists
- 401: Unauthorized
- 403: Forbidden (voice belongs to a different user)
- 404: Audio does not exist

#### Generate Audio

```
POST /voices/{elevenlabs_voice_id}/stories/{story_id}/audio
```

Generate audio for a story with a specific voice.

**Headers:**
- Authorization: Bearer {access_token}

**URL Parameters:**
- elevenlabs_voice_id: ElevenLabs ID of the voice
- story_id: ID of the story

**Response:**
```json
{
  "status": "success",
  "url": "https://s3.amazonaws.com/storyvoice/audio/..."
}
```

**Status Codes:**
- 200: Audio generated successfully
- 401: Unauthorized
- 403: Forbidden (voice belongs to a different user)
- 404: Voice or story not found
- 500: Generation failed

#### Get Audio File

```
GET /voices/{elevenlabs_voice_id}/stories/{story_id}/audio
```

Stream or redirect to audio for a story read in a specific voice.

**Headers:**
- Authorization: Bearer {access_token}
- Range: (Optional) For partial content requests

**URL Parameters:**
- elevenlabs_voice_id: ElevenLabs ID of the voice
- story_id: ID of the story

**Query Parameters:**
- redirect: (Optional) If "true", redirects to S3 URL instead of streaming
- expires: (Optional) Expiration time in seconds for the URL if redirecting (default: 3600)

**Response:**
If redirect=true, redirects to the audio URL.
Otherwise, streams the audio file with appropriate headers for range requests.

**Status Codes:**
- 200: Full content
- 206: Partial content (when Range header is used)
- 302: Redirect (when redirect=true)
- 401: Unauthorized
- 403: Forbidden (voice belongs to a different user)
- 404: Audio not found
- 500: Server error

## Error Handling

All error responses follow a consistent format:

```json
{
  "error": "Description of the error"
}
```

Some responses may include additional details:

```json
{
  "error": "Failed to delete voice",
  "details": "Error connecting to ElevenLabs API"
}
```

## Client Implementation Notes

1. **Token Management**: Store both access and refresh tokens securely. When an access token expires (401 response), use the refresh token to get a new one.

2. **Audio Streaming**: For a better user experience, check if audio exists before attempting to play it. If it doesn't exist, trigger generation and show a loading indicator.

3. **Offline Support**: Consider caching story text and generated audio for offline access.

4. **Error Handling**: Implement comprehensive error handling, especially for network connectivity issues common in mobile apps.

5. **Deep Linking**: The app should handle deep links for email confirmation and password reset.