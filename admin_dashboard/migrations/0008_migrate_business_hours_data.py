import re
from datetime import datetime, time
from django.db import migrations


def parse_time_str(time_str):
    """Parse a time string like '9:00 AM' or '5:00 PM' into a time object."""
    time_str = time_str.strip()
    if not time_str:
        return None
    try:
        return datetime.strptime(time_str, '%I:%M %p').time()
    except ValueError:
        try:
            return datetime.strptime(time_str, '%H:%M').time()
        except ValueError:
            return None


def parse_business_hours_content(content):
    """Parse HTML/text business hours content into a dict of day -> {open, close, is_closed}."""
    if not content:
        return {}

    text = re.sub(r'<[^>]+>', ' ', content)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    day_map = {
        'monday': 'monday', 'tuesday': 'tuesday', 'wednesday': 'wednesday',
        'thursday': 'thursday', 'friday': 'friday', 'saturday': 'saturday', 'sunday': 'sunday',
    }

    result = {day: {'open': None, 'close': None, 'is_closed': False} for day in day_map}

    range_pattern = re.compile(
        r'(?P<start_day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
        r'(?:\s*-\s*(?P<end_day>monday|tuesday|wednesday|thursday|friday|saturday|sunday))?'
        r'\s*:\s*'
        r'(?P<open_time>\d{1,2}:\d{2}\s*(?:AM|PM)?)'
        r'\s*-\s*'
        r'(?P<close_time>\d{1,2}:\d{2}\s*(?:AM|PM)?)',
        re.IGNORECASE,
    )

    closed_pattern = re.compile(
        r'(?P<start_day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
        r'(?:\s*-\s*(?P<end_day>monday|tuesday|wednesday|thursday|friday|saturday|sunday))?'
        r'\s*:\s*'
        r'(?P<closed_word>closed)',
        re.IGNORECASE,
    )

    for match in range_pattern.finditer(text):
        start_day = match.group('start_day').lower()
        end_day = match.group('end_day')
        if end_day:
            end_day = end_day.lower()
        else:
            end_day = start_day

        open_time = parse_time_str(match.group('open_time'))
        close_time = parse_time_str(match.group('close_time'))

        day_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        start_idx = day_order.index(start_day)
        end_idx = day_order.index(end_day)
        for i in range(start_idx, end_idx + 1):
            d = day_order[i]
            if open_time:
                result[d]['open'] = open_time
            if close_time:
                result[d]['close'] = close_time

    for match in closed_pattern.finditer(text):
        start_day = match.group('start_day').lower()
        end_day = match.group('end_day')
        if end_day:
            end_day = end_day.lower()
        else:
            end_day = start_day

        day_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        start_idx = day_order.index(start_day)
        end_idx = day_order.index(end_day)
        for i in range(start_idx, end_idx + 1):
            d = day_order[i]
            result[d]['is_closed'] = True
            if result[d]['open'] is None and result[d]['close'] is None:
                result[d]['open'] = None
                result[d]['close'] = None

    return result


def migrate_business_hours(apps, schema_editor):
    SiteContent = apps.get_model('admin_dashboard', 'SiteContent')
    BusinessHours = apps.get_model('admin_dashboard', 'BusinessHours')

    site_contents = SiteContent.objects.filter(section='business_hours')
    migrated = []
    unparsed = []

    for sc in site_contents:
        parsed = parse_business_hours_content(sc.content)
        if not parsed:
            unparsed.append({
                'id': sc.id,
                'title': sc.title,
                'content': sc.content,
                'reason': 'no recognizable hours format',
            })
            continue

        bh, created = BusinessHours.objects.get_or_create(
            site_content=sc,
            defaults={
                'monday_open': parsed.get('monday', {}).get('open'),
                'monday_close': parsed.get('monday', {}).get('close'),
                'monday_is_closed': parsed.get('monday', {}).get('is_closed', False),
                'tuesday_open': parsed.get('tuesday', {}).get('open'),
                'tuesday_close': parsed.get('tuesday', {}).get('close'),
                'tuesday_is_closed': parsed.get('tuesday', {}).get('is_closed', False),
                'wednesday_open': parsed.get('wednesday', {}).get('open'),
                'wednesday_close': parsed.get('wednesday', {}).get('close'),
                'wednesday_is_closed': parsed.get('wednesday', {}).get('is_closed', False),
                'thursday_open': parsed.get('thursday', {}).get('open'),
                'thursday_close': parsed.get('thursday', {}).get('close'),
                'thursday_is_closed': parsed.get('thursday', {}).get('is_closed', False),
                'friday_open': parsed.get('friday', {}).get('open'),
                'friday_close': parsed.get('friday', {}).get('close'),
                'friday_is_closed': parsed.get('friday', {}).get('is_closed', False),
                'saturday_open': parsed.get('saturday', {}).get('open'),
                'saturday_close': parsed.get('saturday', {}).get('close'),
                'saturday_is_closed': parsed.get('saturday', {}).get('is_closed', False),
                'sunday_open': parsed.get('sunday', {}).get('open'),
                'sunday_close': parsed.get('sunday', {}).get('close'),
                'sunday_is_closed': parsed.get('sunday', {}).get('is_closed', False),
                'notes': '',
            }
        )

        if not created:
            bh.monday_open = parsed.get('monday', {}).get('open')
            bh.monday_close = parsed.get('monday', {}).get('close')
            bh.monday_is_closed = parsed.get('monday', {}).get('is_closed', False)
            bh.tuesday_open = parsed.get('tuesday', {}).get('open')
            bh.tuesday_close = parsed.get('tuesday', {}).get('close')
            bh.tuesday_is_closed = parsed.get('tuesday', {}).get('is_closed', False)
            bh.wednesday_open = parsed.get('wednesday', {}).get('open')
            bh.wednesday_close = parsed.get('wednesday', {}).get('close')
            bh.wednesday_is_closed = parsed.get('wednesday', {}).get('is_closed', False)
            bh.thursday_open = parsed.get('thursday', {}).get('open')
            bh.thursday_close = parsed.get('thursday', {}).get('close')
            bh.thursday_is_closed = parsed.get('thursday', {}).get('is_closed', False)
            bh.friday_open = parsed.get('friday', {}).get('open')
            bh.friday_close = parsed.get('friday', {}).get('close')
            bh.friday_is_closed = parsed.get('friday', {}).get('is_closed', False)
            bh.saturday_open = parsed.get('saturday', {}).get('open')
            bh.saturday_close = parsed.get('saturday', {}).get('close')
            bh.saturday_is_closed = parsed.get('saturday', {}).get('is_closed', False)
            bh.sunday_open = parsed.get('sunday', {}).get('open')
            bh.sunday_close = parsed.get('sunday', {}).get('close')
            bh.sunday_is_closed = parsed.get('sunday', {}).get('is_closed', False)
            bh.save()

        all_unset = all(
            getattr(bh, f'{d}_open') is None and
            getattr(bh, f'{d}_close') is None and
            not getattr(bh, f'{d}_is_closed')
            for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        )
        if all_unset:
            bh.notes = sc.content
            bh.save()
            unparsed.append({
                'id': sc.id,
                'title': sc.title,
                'content': sc.content,
                'reason': 'could not reliably parse any days',
            })
        else:
            migrated.append({
                'id': sc.id,
                'title': sc.title,
                'days_parsed': [
                    d for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    if getattr(bh, f'{d}_open') or getattr(bh, f'{d}_close') or getattr(bh, f'{d}_is_closed')
                ],
            })

    print(f'BusinessHours migration: {len(migrated)} records fully parsed, {len(unparsed)} records preserved as notes.')
    if unparsed:
        print('Unparsed records (manual review needed):')
        for u in unparsed:
            print(f"  - ID {u['id']}: {u['title']} — {u['reason']}")
            print(f"    Raw content: {u['content'][:200]}")


class Migration(migrations.Migration):
    dependencies = [
        ('admin_dashboard', '0007_businesshours'),
    ]

    operations = [
        migrations.RunPython(migrate_business_hours, reverse_code=migrations.RunPython.noop),
    ]
