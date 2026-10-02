"""Oylik balanslarni qayta hisoblash (mavjud ma'lumotlarni tuzatish).

    python manage.py sync_balances              # faqat ko'rsatadi, hech narsa yozmaydi
    python manage.py sync_balances --apply      # o'zgarishlarni saqlaydi
    python manage.py sync_balances --student 12 --group 3
    python manage.py sync_balances --reprice-past   # o'tgan oylar narxini ham hozirgi narx/chegirmaga tenglash
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from groups_app.models import Group
from payments.billing import all_pairs, sync_pair
from students.models import Student


class _DryRun(Exception):
    pass


class Command(BaseCommand):
    help = "Oylik to'lov balanslarini a'zolik sanalari, pauzalar va chegirmalar bo'yicha qayta hisoblaydi."

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help="O'zgarishlarni bazaga yozish")
        parser.add_argument('--reprice-past', action='store_true',
                            help="O'tgan oylar summasini ham hozirgi narx va chegirma bo'yicha qayta hisoblash")
        parser.add_argument('--student', type=int)
        parser.add_argument('--group', type=int)

    def handle(self, *args, **opts):
        pairs = [
            (s, g) for s, g in all_pairs()
            if (opts['student'] is None or s == opts['student']) and (opts['group'] is None or g == opts['group'])
        ]
        students = Student.objects.in_bulk({s for s, _ in pairs})
        groups = Group.objects.in_bulk({g for _, g in pairs})

        results = []
        try:
            with transaction.atomic():
                for s, g in pairs:
                    results.append(sync_pair(students[s], groups[g], reprice_past=opts['reprice_past']))
                if not opts['apply']:
                    raise _DryRun
        except _DryRun:
            pass

        changed = [r for r in results if r.changed]
        before = sum((r.debt_before for r in results), Decimal(0))
        after = sum((r.debt_after for r in results), Decimal(0))

        self.stdout.write(f"\n{'O`quvchi':<30} {'Guruh':<22} {'Qarz oldin':>14} {'Qarz keyin':>14}  yangi/o'zg/o'chir")
        for r in changed:
            self.stdout.write(
                f"{str(students[r.student_id])[:30]:<30} {groups[r.group_id].name[:22]:<22} "
                f"{r.debt_before:>14,.0f} {r.debt_after:>14,.0f}  {r.created}/{r.updated}/{r.deleted}"
                + ("  (to'lovlar qayta taqsimlandi)" if r.allocations_changed else '')
            )
        self.stdout.write(
            f"\nJami juftliklar: {len(results)}, o'zgargan: {len(changed)}\n"
            f"Umumiy qarz: {before:,.0f} -> {after:,.0f}"
        )
        if opts['apply']:
            self.stdout.write(self.style.SUCCESS("O'zgarishlar saqlandi."))
        else:
            self.stdout.write(self.style.WARNING("DRY-RUN: hech narsa saqlanmadi. Saqlash uchun --apply qo'shing."))
