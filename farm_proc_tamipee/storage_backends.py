import os
import uuid
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from urllib.request import Request, urlopen
from urllib.error import URLError
import json
import base64
import hashlib
import hmac
import time


class SupabaseStorage(FileSystemStorage):
    """
    Custom storage backend that uploads files to Supabase Storage.
    Falls back to local filesystem if Supabase is not configured.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supabase_url = getattr(settings, 'SUPABASE_URL', '')
        self.supabase_key = getattr(settings, 'SUPABASE_SERVICE_ROLE_KEY', '')
        self.default_bucket = getattr(settings, 'SUPABASE_BUCKET_NAME', 'product-images')
        self.profile_photo_bucket = getattr(settings, 'PROFILE_PHOTO_BUCKET_NAME', 'profile_photos')
        self.use_supabase = bool(self.supabase_url and self.supabase_key)

    def _get_bucket_for_name(self, name):
        """Return the appropriate Supabase bucket based on file path."""
        if name.startswith('profile_photos/') or name.startswith('profile_photos\\'):
            return self.profile_photo_bucket
        return self.default_bucket

    def _get_supabase_headers(self):
        return {
            'Authorization': f'Bearer {self.supabase_key}',
            'Content-Type': 'application/octet-stream',
            'x-upsert': 'true',
        }

    def _upload_to_supabase(self, name, content):
        """Upload file content to Supabase Storage."""
        if not self.use_supabase:
            return None

        file_content = content.read()
        content.seek(0)

        bucket = self._get_bucket_for_name(name)

        # For profile photos, preserve the provided name format
        # For other files, generate a UUID to avoid collisions
        if bucket == self.profile_photo_bucket:
            # Extract just the filename from the path for Supabase
            filename = os.path.basename(name)
        else:
            ext = os.path.splitext(name)[1]
            filename = f"{uuid.uuid4().hex}{ext}"

        upload_url = f"{self.supabase_url}/storage/v1/object/{bucket}/{filename}"

        req = Request(
            upload_url,
            data=file_content,
            headers=self._get_supabase_headers(),
            method='POST'
        )

        try:
            with urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))
                if result.get('Key') or result.get('name'):
                    # Return the public URL
                    public_url = f"{self.supabase_url}/storage/v1/object/public/{bucket}/{filename}"
                    return public_url
        except URLError as e:
            print(f"Supabase upload failed: {e}")

        return None

    def _save(self, name, content):
        if self.use_supabase:
            public_url = self._upload_to_supabase(name, content)
            if public_url:
                # Store the URL in the database instead of a local path
                return public_url

        # Fallback to local storage
        return super()._save(name, content)

    def exists(self, name):
        if self.use_supabase and name.startswith('http'):
            return True
        return super().exists(name)

    def url(self, name):
        if self.use_supabase and name.startswith('http'):
            return name
        return super().url(name)

    def open(self, name, mode='rb'):
        if self.use_supabase and name.startswith('http'):
            req = Request(name, method='GET')
            try:
                with urlopen(req, timeout=30) as response:
                    return ContentFile(response.read())
            except URLError:
                return ContentFile(b'')
        return super().open(name, mode)
