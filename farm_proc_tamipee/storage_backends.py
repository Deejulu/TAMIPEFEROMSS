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
        self.bucket_name = getattr(settings, 'SUPABASE_BUCKET_NAME', 'product-images')
        self.use_supabase = bool(self.supabase_url and self.supabase_key)

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

        # Generate a unique path to avoid collisions
        ext = os.path.splitext(name)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"

        upload_url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{unique_name}"

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
                    public_url = f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{unique_name}"
                    return public_url
        except URLError as e:
            print(f"Supabase upload failed: {e}")

        return None

    def _save(self, name, content):
        if self.use_supabase:
            public_url = self._upload_to_supabase(name, content)
            if public_url:
                # Store the URL in the database instead of a local path
                # We return the URL as the "name" so it can be retrieved later
                return public_url

        # Fallback to local storage
        return super()._save(name, content)

    def exists(self, name):
        if self.use_supabase and name.startswith('http'):
            # If name is a URL, we consider it as existing
            return True
        return super().exists(name)

    def url(self, name):
        if self.use_supabase and name.startswith('http'):
            return name
        return super().url(name)

    def open(self, name, mode='rb'):
        if self.use_supabase and name.startswith('http'):
            # For URLs, return a ContentFile with the remote content
            req = Request(name, method='GET')
            try:
                with urlopen(req, timeout=30) as response:
                    return ContentFile(response.read())
            except URLError:
                return ContentFile(b'')
        return super().open(name, mode)
