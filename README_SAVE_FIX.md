# Incomplete profile save hardening

The admin flow now installs a dedicated save handler at startup. It permits missing fields, rejects invalid values, derives the request number from the database-generated profile id, and isolates Telegram response failures from persistence.
