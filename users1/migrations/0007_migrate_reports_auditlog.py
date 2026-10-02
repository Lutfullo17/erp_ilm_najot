from django.db import migrations


def migrate_reports_auditlog_forward(apps, schema_editor):
    """Move existing records from reports.AuditLog to users1.AuditLog."""
    try:
        OldAuditLog = apps.get_model('reports', 'AuditLog')
        NewAuditLog = apps.get_model('users1', 'AuditLog')

        old_records = OldAuditLog.objects.all()
        new_records = []
        for old in old_records:
            new_records.append(NewAuditLog(
                user_id=old.user_id,
                role=old.role or '',
                action=old.action,
                old_data=old.old_data,
                new_data=old.new_data,
                ip_address=old.ip_address,
                created_at=old.timestamp,
            ))
        if new_records:
            NewAuditLog.objects.bulk_create(new_records)
    except Exception:
        pass


def migrate_reports_auditlog_backward(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users1', '0006_unify_auditlog_add_fields'),
        ('reports', '__first__'),
    ]

    operations = [
        migrations.RunPython(migrate_reports_auditlog_forward, migrate_reports_auditlog_backward),
    ]
