from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from groups_app.models import Group
from users1.models import User


class GroupFeeEditRenderingTests(TestCase):
	def test_edit_form_renders_fee_without_locale_decimal_separator(self):
		director = User.objects.create_user(
			username='fee-editor', password='test-password', role=User.Role.DIRECTOR
		)
		group = Group.objects.create(name='Fee format test', monthly_fee=Decimal('40000000.00'))
		self.client.force_login(director)

		response = self.client.get(reverse('groups_app:group_edit', args=[group.pk]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'value="40000000.00"', count=2)
		self.assertContains(response, 'id="appConfirmDialog"')
