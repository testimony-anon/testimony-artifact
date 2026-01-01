"""Seed one Paperless-ngx instance with the upstream Playwright fixture data.

Run inside the application container:

    python3 manage.py shell -c "exec(open('/opt/uisemtest/seed_database.py').read())"

This is a port of ``src-ui/e2e/backend.py::seed_database()`` at upstream commit
``54e332d25943`` (paperless-ngx 3.2.0).  The only differences from upstream are
forced on us by the deployment shape, and every one of them is listed in
``deploy/paperless/README.md``:

* upstream seeds a disposable in-process instance with
  ``CELERY_TASK_ALWAYS_EAGER``; we seed a live container, so we drop the
  ``PaperlessTask`` rows the live workers record while the seed runs;
* upstream hard-codes both accounts' credentials; we read the same two accounts
  from ``UISEMTEST_PAPERLESS_ACTOR_{A,B}_{USERNAME,PASSWORD}`` so that no
  credential is written into a tracked file;
* upstream reads its sample PDF from ``src/documents/tests/samples/simple.pdf``,
  which the published image does not ship; we bind-mount a byte-identical copy
  (sha256 1093cf6e32adbd16b06969df09215d42c4a3a8938cc18b39455953f08d1ff2ab) at
  ``/opt/uisemtest/simple.pdf``.

Everything else - the 61 documents, their titles, contents, checksums,
filenames, archive serial numbers, created dates, owners, document types,
correspondents, storage paths, the inbox tag membership, the four notes, the
saved view plus its filter rule, the custom field and the UI settings - is the
upstream code path, verbatim.
"""

from __future__ import annotations

import datetime
import os
import shutil
from pathlib import Path

import documents as documents_package
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from documents.models import Correspondent
from documents.models import CustomField
from documents.models import Document
from documents.models import DocumentType
from documents.models import Note
from documents.models import PaperlessTask
from documents.models import SavedView
from documents.models import SavedViewFilterRule
from documents.models import StoragePath
from documents.models import Tag
from documents.models import UiSettings

SAMPLE_PDF = Path("/opt/uisemtest/simple.pdf")
# Upstream leaves both seeded accounts without an email address.  We set one,
# derived from the username, because it is the only field that
# `GET /api/profile/` - the one authenticated read both actors are allowed and
# that the Stage 0 recorder fully captures - exposes as a per-actor identity.
# No case in src-ui/e2e/** reads an email, so the fixture stays equivalent.
IDENTITY_EMAIL_DOMAIN = "paperless.uisemtest.local"
THUMBNAIL_SOURCE = (
    Path(documents_package.__file__).resolve().parent / "resources" / "document.webp"
)


def _account(slot: str) -> tuple[str, str]:
    """Both accounts come from .env; no credential literal lives in this file."""
    username = os.environ.get(f"UISEMTEST_PAPERLESS_ACTOR_{slot}_USERNAME")
    password = os.environ.get(f"UISEMTEST_PAPERLESS_ACTOR_{slot}_PASSWORD")
    if not username or not password:
        raise SystemExit(f"UISEMTEST_PAPERLESS_ACTOR_{slot}_{{USERNAME,PASSWORD}} are unset")
    return username, password


def seed_database() -> None:
    admin_username, admin_password = _account("A")
    second_username, second_password = _account("B")

    admin = User.objects.create_superuser(
        username=admin_username,
        password=admin_password,
        email=f"{admin_username}@{IDENTITY_EMAIL_DOMAIN}",
    )
    User.objects.create_user(
        username=second_username,
        password=second_password,
        email=f"{second_username}@{IDENTITY_EMAIL_DOMAIN}",
    )

    inbox = Tag.objects.create(name="Inbox", is_inbox_tag=True, owner=admin)
    quick_filter = Tag.objects.create(name="Another Sample Tag", owner=admin)
    Tag.objects.create(name="TagWithPartial", owner=admin)
    invoice = DocumentType.objects.create(name="Invoice Test", owner=admin)
    correspondent_1 = Correspondent.objects.create(
        name="Test Correspondent 1",
        owner=admin,
    )
    correspondent_2 = Correspondent.objects.create(name="Correspondent 9", owner=admin)
    storage_path = StoragePath.objects.create(
        name="Testing 12",
        path="e2e/{created_year}/{title}",
        owner=admin,
    )
    CustomField.objects.create(
        name="Test Select Field",
        data_type=CustomField.FieldDataType.SELECT,
        extra_data={
            "select_options": [
                {"id": "abc123", "label": "Alpha"},
                {"id": "def456", "label": "Beta"},
            ],
        },
    )

    today = timezone.localdate()
    documents = []
    for number in range(1, 62):
        title = f"test document {number}" if number <= 9 else f"document {number}"
        content = (
            f"Playwright test content for document {number}"
            if number <= 32
            else f"Seeded content for document {number}"
        )
        created = today if number == 1 else datetime.date(2021, 1, 1)
        if number in (2, 3):
            created = datetime.date(2022, 12, 11)

        documents.append(
            Document(
                title=title,
                content=content,
                checksum=f"{number:064x}",
                mime_type="application/pdf",
                filename=f"{number:07}.pdf",
                original_filename=f"document-{number}.pdf",
                archive_serial_number=1122 + number if number <= 6 else None,
                created=created,
                owner=admin,
                document_type=invoice if number <= 3 else None,
                correspondent=(
                    correspondent_1
                    if number <= 4
                    else correspondent_2
                    if number <= 7
                    else None
                ),
                storage_path=storage_path if number <= 8 else None,
            ),
        )

    Document.objects.bulk_create(documents)
    originals = Path(settings.MEDIA_ROOT) / "documents" / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    thumbnails = Path(settings.MEDIA_ROOT) / "documents" / "thumbnails"
    thumbnails.mkdir(parents=True, exist_ok=True)
    for document in documents:
        shutil.copyfile(SAMPLE_PDF, originals / document.filename)
        shutil.copyfile(THUMBNAIL_SOURCE, thumbnails / f"{document.pk:07}.webp")

    for document in documents[:8]:
        document.tags.add(inbox)
    documents[0].tags.add(quick_filter)

    for number in range(1, 5):
        Note.objects.create(
            note=f"Playwright note {number}",
            document=documents[0],
            user=admin,
        )

    inbox_view = SavedView.objects.create(
        name="Inbox",
        owner=admin,
        sort_field="created",
        sort_reverse=True,
        page_size=10,
        display_mode=SavedView.DisplayMode.TABLE,
        display_fields=["created", "title", "tag", "documenttype"],
    )
    SavedViewFilterRule.objects.create(
        saved_view=inbox_view,
        rule_type=6,
        value=str(inbox.pk),
    )

    UiSettings.objects.create(
        user=admin,
        settings={
            "language": "",
            "bulk_edit": {"confirmation_dialogs": True, "apply_on_close": False},
            "documentListSize": 50,
            "dark_mode": {
                "use_system": True,
                "enabled": False,
                "thumb_inverted": True,
            },
            "theme": {"color": "#9fbf2f"},
            "document_details": {"native_pdf_viewer": False},
            "date_display": {"date_locale": "", "date_format": "mediumDate"},
            "comments_enabled": True,
            "slim_sidebar": False,
            "update_checking": {"enabled": False},
            "saved_views": {
                "warn_on_unsaved_change": True,
                "dashboard_views_visible_ids": [inbox_view.pk],
                "sidebar_views_visible_ids": [inbox_view.pk],
            },
            "notes_enabled": True,
            "tour_complete": True,
        },
    )

    call_command(
        "document_index",
        "reindex",
        recreate=True,
        heap_size_mb=16,
        verbosity=0,
    )


if User.objects.filter(is_superuser=True).exists():
    print("uisemtest-seed: already seeded, refusing to seed twice")
else:
    seed_database()
    # The live celery workers record a PaperlessTask row for work the in-process
    # upstream seeder never enqueues; drop them so /api/tasks/ starts empty, the
    # way the upstream fixture leaves it.
    PaperlessTask.objects.all().delete()
    print("uisemtest-seed: ok", Document.objects.count(), "documents")
