from unittest.mock import Mock
from django.test import TestCase


class GetActiveCompanyNameTests(TestCase):
    def test_returns_company_name_from_validated_jwt(self):
        from config.auth import get_active_company_name
        request = Mock()
        request.auth = {'company_id': 'c1', 'company_name': 'Topfaith University', 'role': 'Admin'}
        self.assertEqual(get_active_company_name(request), 'Topfaith University')

    def test_returns_none_when_request_has_no_auth(self):
        from config.auth import get_active_company_name
        request = Mock()
        request.auth = None
        self.assertIsNone(get_active_company_name(request))
