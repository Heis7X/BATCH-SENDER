# Gmail Batch Mailer

A Django web app for sending email batches through connected Gmail accounts.

## What it does

- Stores admin-editable email templates in the backend
- Lets any logged-in user load a template and overwrite the subject/body before sending
- Connects Gmail accounts via Google OAuth and sends through the Gmail API
- Accepts up to 100 recipients per batch from pasted text or CSV/TXT upload
- Queues one recipient job per email address
- Tracks sent, failed, and pending recipients per batch
- Includes a worker process for continuous sending and a manual "Process 25 Now" fallback from the UI

## Stack

- Django 5
- SQLite (easy local startup; switchable later)
- Google OAuth 2.0 + Gmail API
- Django Admin for admin-side template management and user management

## Quick start

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the env file and fill in your Google OAuth values:

   ```bash
   cp .env.example .env
   ```

4. Run migrations:

   ```bash
   python manage.py migrate
   ```

5. Create an admin user or seed a demo admin:

   ```bash
   python manage.py createsuperuser
   ```

   or

   ```bash
   python manage.py seed_demo
   ```

6. Start the web app:

   ```bash
   python manage.py runserver
   ```

7. In a second terminal, start the email worker:

   ```bash
   python manage.py run_email_worker
   ```

8. Login at `/accounts/login/`, connect a Gmail account, then create a batch.

## Google Cloud setup

1. Create a Google Cloud project.
2. Enable the Gmail API.
3. Configure the OAuth consent screen.
4. Create an OAuth client for a web application.
5. Add the redirect URI you will actually use, for example:

   ```text
   http://127.0.0.1:8000/gmail/callback/
   ```

6. Put the client id and client secret into `.env`.

Recommended Gmail scope for this app:

- `https://www.googleapis.com/auth/gmail.send`

The app also requests `openid email profile` so it can identify the connected Gmail account.

## Roles

- Staff/admin users:
  - manage templates in `/templates/`
  - manage users and raw data in `/admin/`
- Regular users:
  - connect their own Gmail accounts
  - create batches from saved templates
  - overwrite the template subject/body on the compose screen

## Template placeholders

You can use these placeholders in the subject and body:

- `{{email}}` → replaced with the recipient email
- `{{app_name}}` → replaced with the configured app name

## Recipient formats

The app accepts recipients from:

- pasted text separated by commas, spaces, tabs, semicolons, or new lines
- CSV files
- TXT files

Duplicates are removed automatically. Invalid emails are skipped.

## Running with Docker Compose

```bash
docker compose up --build
```

This starts:

- `web` on port 8000
- `worker` for continuous queued sending

## Notes for production

- Replace SQLite with PostgreSQL for higher concurrency
- Run the app behind HTTPS
- Keep `TOKEN_ENCRYPTION_KEY` secret and stable
- Restrict access with proper user accounts and strong passwords
- Consider a pause between emails if you want gentler delivery patterns:

  ```bash
  python manage.py run_email_worker --pause-between-emails 0.5
  ```
