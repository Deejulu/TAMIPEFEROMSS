from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import F, Max

from farm_management.models import Batch, FeedInventory
from notifications.models import Notification


class Command(BaseCommand):
    help = 'Checks batch conditions and creates Notification alerts for:'
    help += ' (1) no feed log in 3+ days, (2) feed inventory below reorder point,'
    help += ' (3) mortality rate jump vs rolling average.'

    def handle(self, *args, **options):
        self.stdout.write('Checking batch alerts...')
        created = 0
        created += self._check_feed_log_gaps()
        created += self._check_feed_inventory()
        created += self._check_mortality_jump()
        self.stdout.write(f'Done. Created {created} new alert(s).')

    def _check_feed_log_gaps(self):
        created = 0
        days = getattr(settings, 'FEED_DAYS_NO_LOG', 3)
        cutoff = date.today() - timedelta(days=days)
        active_batches = Batch.objects.filter(status='active')
        for batch in active_batches:
            latest = batch.feed_logs.aggregate(latest=Max('date'))['latest']
            if latest is None or latest < cutoff:
                if Notification.objects.filter(
                    notification_type='batch_alert',
                    related_object_id=batch.pk,
                    message__icontains='feed log entry',
                    is_read=False,
                ).exists():
                    continue
                Notification.objects.create(
                    notification_type='batch_alert',
                    message=f'Batch "{batch.name}" has no feed log entry in {days}+ days.',
                    related_object_id=batch.pk,
                )
                created += 1
                self.stdout.write(f'  Feed gap alert: {batch.name}')
        return created

    def _check_feed_inventory(self):
        created = 0
        low_items = FeedInventory.objects.filter(
            quantity_on_hand_kg__lte=F('reorder_point_kg'),
        )
        for item in low_items:
            if Notification.objects.filter(
                notification_type='batch_alert',
                message__icontains=item.feed_type,
                is_read=False,
            ).exists():
                continue
            Notification.objects.create(
                notification_type='batch_alert',
                message=f'Feed inventory "{item.feed_type}" is below reorder point '
                        f'({item.quantity_on_hand_kg} kg on hand, threshold {item.reorder_point_kg} kg).',
                related_object_id=item.pk,
            )
            created += 1
            self.stdout.write(f'  Low feed inventory alert: {item.feed_type}')
        return created

    def _check_mortality_jump(self):
        created = 0
        factor = getattr(settings, 'MORTALITY_JUMP_FACTOR', 2.0)
        active_batches = Batch.objects.filter(status='active')
        for batch in active_batches:
            logs = batch.mortality_logs.all().order_by('-date')
            if logs.count() < 2:
                continue
            counts = [log.count for log in logs]
            avg_count = sum(counts) / len(counts)
            latest_count = counts[0]
            if latest_count > avg_count * factor:
                if Notification.objects.filter(
                    notification_type='batch_alert',
                    related_object_id=batch.pk,
                    message__icontains='mortality',
                    is_read=False,
                ).exists():
                    continue
                Notification.objects.create(
                    notification_type='batch_alert',
                    message=f'Batch "{batch.name}" latest mortality count '
                            f'({latest_count}) exceeds {factor}x its own '
                            f'rolling average ({round(avg_count, 2)}).',
                    related_object_id=batch.pk,
                )
                created += 1
                self.stdout.write(
                    f'  Mortality jump alert: {batch.name} '
                    f'({latest_count} vs avg {round(avg_count, 2)})'
                )
        return created