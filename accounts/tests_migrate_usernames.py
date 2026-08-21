"""Tests for the one-time existing-username migration command.

These exercise the command on the (rolled-back) test database only. They
confirm: passwords/other fields are untouched, logins still work with the
original password + new username, the real creation year is used, already
migrated accounts are skipped (idempotent), and superusers can be excluded.
"""
import re
from datetime import datetime

from django.test import TestCase
from django.core.management import call_command
from django.contrib.auth import get_user_model
from io import StringIO

from accounts.utils import (
    ACCOUNT_ID_ALPHABET,
    ACCOUNT_ID_LENGTH,
    extract_account_id,
)

CANONICAL = re.compile(
    rf"^.+\d{{4}}TIF[{ACCOUNT_ID_ALPHABET}]{{{ACCOUNT_ID_LENGTH},}}$"
)


class MigrateExistingUsernamesTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        # Explicit OLD-STYLE usernames so the command has something to rename.
        # (In the test DB, create_user would otherwise auto-generate the new
        #  pattern, which would make these already-migrated and skipped.)
        self.u1 = self.User.objects.create_user(
            email="mig1@example.com",
            full_name="Alpha One",
            password="Passw0rd!23",
            username="AlphaOne2023001",
            role=self.User.Role.CUSTOMER,
            date_joined=datetime(2023, 3, 4),
        )
        self.u2 = self.User.objects.create_user(
            email="mig2@example.com",
            full_name="Beta Two",
            password="Passw0rd!23",
            username="BetaTwo2024002",
            role=self.User.Role.STAFF,
            date_joined=datetime(2024, 6, 1),
        )
        self.u3 = self.User.objects.create_user(
            email="mig3@example.com",
            full_name="Admin User",
            password="Passw0rd!23",
            username="admin",
            role=self.User.Role.SUPER_ADMIN,
            is_superuser=True,
            date_joined=datetime(2022, 1, 1),
        )
        # Already in the new format -> should be skipped (idempotency).
        self.u4 = self.User.objects.create_user(
            email="mig4@example.com",
            full_name="Delta Four",
            password="Passw0rd!23",
            username="DeltaFour2025TIFQ7WK",
            account_id="Q7WK",
            role=self.User.Role.FARM_MANAGER,
            date_joined=datetime(2025, 5, 5),
        )

    # ---------------------------------------------------------------- #
    def test_dry_run_makes_no_changes(self):
        call_command("migrate_existing_usernames", "--dry-run", stdout=StringIO())
        self.u1.refresh_from_db()
        self.u2.refresh_from_db()
        self.u3.refresh_from_db()
        self.u4.refresh_from_db()
        self.assertEqual(self.u1.username, "AlphaOne2023001")
        self.assertEqual(self.u2.username, "BetaTwo2024002")
        self.assertEqual(self.u3.username, "admin")
        self.assertEqual(self.u4.username, "DeltaFour2025TIFQ7WK")

    def test_renames_to_new_pattern_with_real_creation_year(self):
        call_command("migrate_existing_usernames", stdout=StringIO())
        self.u1.refresh_from_db()
        self.u2.refresh_from_db()
        self.u3.refresh_from_db()

        self.assertRegex(self.u1.username, CANONICAL)
        self.assertIn("2023TIF", self.u1.username)
        self.assertTrue(self.u1.account_id)
        self.assertEqual(self.u1.account_id, extract_account_id(self.u1.username))

        self.assertIn("2024TIF", self.u2.username)

        # Super Admin is included by default (no exceptions).
        self.assertIn("2022TIF", self.u3.username)

    def test_already_migrated_account_is_skipped(self):
        call_command("migrate_existing_usernames", stdout=StringIO())
        self.u4.refresh_from_db()
        self.assertEqual(self.u4.username, "DeltaFour2025TIFQ7WK")
        self.assertEqual(self.u4.account_id, "Q7WK")

    def test_password_hash_is_unchanged(self):
        original_hash = self.u1.password
        email_before = self.u1.email
        call_command("migrate_existing_usernames", stdout=StringIO())
        self.u1.refresh_from_db()
        # Byte-for-byte identical password hash.
        self.assertEqual(self.u1.password, original_hash)
        # Other fields untouched.
        self.assertEqual(self.u1.email, email_before)
        self.assertTrue(self.u1.check_password("Passw0rd!23"))

    def test_login_works_with_new_username_and_original_password(self):
        call_command("migrate_existing_usernames", stdout=StringIO())
        self.u1.refresh_from_db()
        # New username + original password authenticates.
        self.assertTrue(
            self.client.login(username=self.u1.username, password="Passw0rd!23")
        )
        # The old username no longer exists.
        self.assertFalse(
            self.client.login(username="AlphaOne2023001", password="Passw0rd!23")
        )

    def test_idempotent_when_run_twice(self):
        call_command("migrate_existing_usernames", stdout=StringIO())
        self.u1.refresh_from_db()
        first_new = self.u1.username
        # Second run must skip already-migrated accounts and not re-randomize.
        call_command("migrate_existing_usernames", stdout=StringIO())
        self.u1.refresh_from_db()
        self.assertEqual(self.u1.username, first_new)

    def test_exclude_superusers_leaves_admin_login_untouched(self):
        call_command(
            "migrate_existing_usernames",
            "--exclude-superusers",
            stdout=StringIO(),
        )
        self.u1.refresh_from_db()
        self.u3.refresh_from_db()
        # Regular account still renamed.
        self.assertRegex(self.u1.username, CANONICAL)
        # Super Admin bootstrap login left alone.
        self.assertEqual(self.u3.username, "admin")

    def test_report_file_is_written(self):
        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            call_command(
                "migrate_existing_usernames",
                "--report",
                path,
                stdout=StringIO(),
            )
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("AlphaOne2023001", content)
            # New username present and marked as a rename.
            self.assertIn("rename", content)
        finally:
            os.remove(path)
