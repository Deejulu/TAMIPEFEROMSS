"""One-time migration: rename every existing account to the new username pattern.

The new pattern is the same one used for brand-new signups
``<FullName><Year>TIF<RandomID>`` (e.g. ``DavidOkonkwo2026TIF4K9X``).

This command walks every ``CustomUser`` and, for each account that does not
already use the new pattern, derives the full name and the account's real
creation year (from ``date_joined``) and generates a fresh username + random
account ID using the project's shared generator
(:func:`accounts.utils.generate_unique_username_with_id`).

Only the ``username`` and ``account_id`` fields are written. The password,
email, role and every other field are left completely untouched.

Run with ``--dry-run`` first to preview (and optionally write) the full
before/after report without changing anything.
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from accounts.utils import (
    generate_unique_username_with_id,
    split_full_name,
    extract_account_id,
)

CANONICAL = None  # lazily built once we know the alphabet/length


class Command(BaseCommand):
    help = (
        "Rename every existing CustomUser to the new "
        "FullName+Year+TIF+RandomID pattern (matching new signups). "
        "Only username and account_id are changed; passwords are untouched. "
        "Use --dry-run to preview without writing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the changes and write the report without modifying "
            "the database.",
        )
        parser.add_argument(
            "--report",
            dest="report",
            default=None,
            help="Write the before/after CSV report to this path (works for "
            "both real and dry runs).",
        )
        parser.add_argument(
            "--exclude-superusers",
            action="store_true",
            help="Skip is_superuser accounts (e.g. the bootstrap admin login).",
        )
        parser.add_argument(
            "--include-already-migrated",
            action="store_true",
            help="Re-process accounts that already match the new pattern "
            "(off by default so the command is idempotent).",
        )

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _unique_username(self, first_name, last_name, year, seen):
        """Generate a username that is unique in the DB *and* within this run."""
        username, account_id = generate_unique_username_with_id(
            first_name, last_name, year
        )
        attempts = 0
        while username in seen:
            username, account_id = generate_unique_username_with_id(
                first_name, last_name, year
            )
            attempts += 1
            if attempts > 200:
                raise CommandError(
                    "Unable to allocate a unique username in this run."
                )
        seen.add(username)
        return username, account_id

    def _build_rows(self, users, exclude_superusers, include_already):
        rows = []
        skipped = []
        seen = set()
        for user in users:
            already_new = bool(extract_account_id(user.username))
            if already_new and not include_already:
                skipped.append((user, "already new format"))
                continue
            if exclude_superusers and user.is_superuser:
                skipped.append((user, "superuser excluded"))
                continue

            # Use the user's authoritative full name (not the old username) so
            # the migrated username matches how new signups are generated.
            first_name, last_name = split_full_name(user.full_name)
            year = user.date_joined.year
            new_username, account_id = self._unique_username(
                first_name, last_name, year, seen
            )
            rows.append(
                {
                    "id": user.pk,
                    "role": user.get_role_display(),
                    "old_username": user.username,
                    "new_username": new_username,
                    "account_id": account_id,
                    "email": user.email,
                    "is_superuser": user.is_superuser,
                    "date_joined": user.date_joined.strftime("%Y-%m-%d"),
                }
            )
        return rows, skipped

    def _print_preview(self, rows, skipped):
        self.stdout.write(
            self.style.WARNING(
                "DRY RUN - no changes were written to the database.\n"
            )
        )
        header = f"{'OLD USERNAME':38} -> {'NEW USERNAME':38}  ROLE"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for r in rows:
            flag = "  [SUPERUSER]" if r["is_superuser"] else ""
            self.stdout.write(
                f"{r['old_username'][:37]:38} -> "
                f"{r['new_username'][:37]:38}  {r['role']}{flag}"
            )
        self.stdout.write("")
        self.stdout.write(f"Accounts to rename : {len(rows)}")
        self.stdout.write(f"Skipped           : {len(skipped)}")
        for user, reason in skipped:
            self.stdout.write(
                f"  - {user.username} ({user.get_role_display()}): {reason}"
            )

    def _write_report(self, rows, skipped, path, dry):
        import csv

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "id",
                    "role",
                    "old_username",
                    "new_username",
                    "account_id",
                    "email",
                    "is_superuser",
                    "date_joined",
                    "action",
                ]
            )
            for r in rows:
                writer.writerow(
                    [
                        r["id"],
                        r["role"],
                        r["old_username"],
                        r["new_username"],
                        r["account_id"],
                        r["email"],
                        r["is_superuser"],
                        r["date_joined"],
                        "rename",
                    ]
                )
            for user, reason in skipped:
                writer.writerow(
                    [
                        user.pk,
                        user.get_role_display(),
                        user.username,
                        user.username,
                        user.account_id,
                        user.email,
                        user.is_superuser,
                        user.date_joined.strftime("%Y-%m-%d"),
                        f"skip:{reason}",
                    ]
                )
        self.stdout.write(self.style.SUCCESS(f"Report written to {path}"))

    # ------------------------------------------------------------------ #
    # main
    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        report_path = options.get("report")
        exclude_superusers = options["exclude_superusers"]
        include_already = options["include_already_migrated"]

        User = get_user_model()
        users = User.objects.all().order_by("id")

        rows, skipped = self._build_rows(
            users, exclude_superusers, include_already
        )

        if dry_run:
            self._print_preview(rows, skipped)
            if report_path:
                self._write_report(rows, skipped, report_path, dry=True)
            return

        updated = 0
        seen = set()
        for r in rows:
            user = User.objects.get(pk=r["id"])
            # Use the user's authoritative full name (not the old username).
            first_name, last_name = split_full_name(user.full_name)
            new_username, account_id = self._unique_username(
                first_name, last_name, user.date_joined.year, seen
            )
            user.username = new_username
            user.account_id = account_id
            # Only these two fields are written; everything else is untouched.
            user.save(update_fields=["username", "account_id"])
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nRenamed {updated} account(s) to the new username pattern."
            )
        )
        if report_path:
            self._write_report(rows, skipped, report_path, dry=False)
