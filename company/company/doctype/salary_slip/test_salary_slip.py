# Copyright (c) 2025, deepak and Contributors
# See license.txt

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from company.company.doctype.salary_slip.salary_slip import calculate_salary_slip_tds
from company.company.tds import (
	DEFAULT_TDS_NEW_SLABS_JSON,
	DEFAULT_TDS_OLD_SLABS_JSON,
	calculate_monthly_tds,
	compute_annual_income_tax,
	compute_slab_tax,
	parse_tds_slabs,
	resolve_tds_policy,
)

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


def _new_regime_settings(**overrides):
	base = {
		"enable_tds": 1,
		"tds_default_regime": "New Tax Regime u/s 115BAC",
		"tds_active_financial_year": "2026-2027",
		"tds_deduction_component": "TDS",
		"tds_standard_deduction_new": 75000,
		"tds_standard_deduction_old": 50000,
		"tds_rebate_limit_87a_new": 1200000,
		"tds_rebate_limit_87a_old": 500000,
		"tds_enable_marginal_relief": 1,
		"tds_cess_rate": 4.0,
		"tds_new_regime_slabs": DEFAULT_TDS_NEW_SLABS_JSON,
		"tds_old_regime_slabs": DEFAULT_TDS_OLD_SLABS_JSON,
		"tds_applicable_categories": '["Staff - CTC", "Workers"]',
	}
	base.update(overrides)
	return base


class IntegrationTestSalarySlip(IntegrationTestCase):
	"""Unit and integration tests for SalarySlip TDS calculations."""

	def test_zero_tds_up_to_1275000_annual_gross(self):
		policy = resolve_tds_policy(_new_regime_settings())
		res = compute_annual_income_tax(1275000.0, policy)
		self.assertEqual(res["standard_deduction"], 75000.0)
		self.assertEqual(res["taxable_income"], 1200000.0)
		self.assertEqual(res["raw_slab_tax"], 60000.0)
		self.assertEqual(res["rebate_87a"], 60000.0)
		self.assertEqual(res["cess_amount"], 0.0)
		self.assertEqual(res["total_annual_tax"], 0.0)

	def test_marginal_relief_just_above_1275000(self):
		# Gross 12,85,000 => Taxable 12,10,000 (10,000 above 12L).
		# Raw slab tax = 61,500; with 87A marginal relief, base tax is capped at 10,000 (+4% cess = 10,400).
		policy_relief = resolve_tds_policy(_new_regime_settings(tds_enable_marginal_relief=1))
		res_relief = compute_annual_income_tax(1285000.0, policy_relief)
		self.assertEqual(res_relief["raw_slab_tax"], 61500.0)
		self.assertEqual(res_relief["marginal_relief"], 51500.0)
		self.assertEqual(res_relief["tax_after_relief"], 10000.0)
		self.assertEqual(res_relief["cess_amount"], 400.0)
		self.assertEqual(res_relief["total_annual_tax"], 10400.0)

		# Without marginal relief toggle, full slab breakup applies immediately above 12.75L.
		policy_no_relief = resolve_tds_policy(_new_regime_settings(tds_enable_marginal_relief=0))
		res_no_relief = compute_annual_income_tax(1285000.0, policy_no_relief)
		self.assertEqual(res_no_relief["tax_after_relief"], 61500.0)
		self.assertEqual(res_no_relief["total_annual_tax"], 63960.0)

	def test_progressive_slab_breakup_across_all_tiers_above_24l(self):
		# Gross 26,75,000 => Taxable 26,00,000
		# Slabs: 0-4L(0) + 4-8L(20k) + 8-12L(40k) + 12-16L(60k) + 16-20L(80k) + 20-24L(100k) + 24-26L(60k) = 3,60,000
		# + 4% cess (14,400) = 3,74,400
		slabs = parse_tds_slabs(DEFAULT_TDS_NEW_SLABS_JSON)
		self.assertEqual(compute_slab_tax(2600000.0, slabs), 360000.0)

		policy = resolve_tds_policy(_new_regime_settings())
		res = compute_annual_income_tax(2675000.0, policy)
		self.assertEqual(res["taxable_income"], 2600000.0)
		self.assertEqual(res["raw_slab_tax"], 360000.0)
		self.assertEqual(res["cess_amount"], 14400.0)
		self.assertEqual(res["total_annual_tax"], 374400.0)

	def test_monthly_tds_projection_and_category_exclusion(self):
		settings = _new_regime_settings()
		emp_below = frappe._dict(
			name="EMP-TEST-001",
			employee_type="Staff - CTC",
			date_of_joining=date(2025, 1, 1),
			total_earnings=106250.0,  # 12,75,000 / 12
		)
		with patch("company.company.tds.frappe.get_all", return_value=[]):
			out_zero = calculate_monthly_tds(106250.0, date(2026, 4, 1), settings, emp_doc=emp_below)
		self.assertEqual(out_zero["tds_amount"], 0.0)
		self.assertTrue(out_zero["applicable"])

		emp_excluded = frappe._dict(
			name="EMP-TEST-002",
			employee_type="Drivers",
			date_of_joining=date(2025, 1, 1),
			total_earnings=250000.0,
		)
		out_excluded = calculate_monthly_tds(250000.0, date(2026, 4, 1), settings, emp_doc=emp_excluded)
		self.assertEqual(out_excluded["tds_amount"], 0.0)
		self.assertFalse(out_excluded["applicable"])

	def test_monthly_tds_ytd_subtraction_mid_year(self):
		settings = _new_regime_settings(tds_cess_rate=0.0)
		# October 2026 (6 months left: Oct..Mar). Monthly 1,50,000 => 18,00,000/yr => taxable 17,25,000
		# Slab tax on 17.25L: 20k + 40k + 60k + (1.25L * 20% = 25k) = 1,45,000
		# Suppose Apr..Sep slips had 9,00,000 gross total and 60,000 TDS already deducted.
		# Remaining 85,000 over 6 months (Oct..Mar) => round(85000/6) = 14167
		emp_mid = frappe._dict(
			name="EMP-TEST-003",
			employee_type="Staff - CTC",
			date_of_joining=date(2025, 1, 1),
			total_earnings=150000.0,
		)
		fake_past = [
			frappe._dict(name=f"SS-PAST-{m}", grand_gross_pay=150000.0, pay_period_start=date(2026, m, 1), tds_amount=10000.0)
			for m in range(4, 10)
		]
		with patch("company.company.tds.frappe.get_all", return_value=fake_past), patch(
			"company.company.tds.frappe.db.has_column", return_value=True
		):
			out_mid = calculate_monthly_tds(150000.0, date(2026, 10, 1), settings, emp_doc=emp_mid)

		self.assertEqual(out_mid["breakdown"]["projected_annual_gross"], 1800000.0)
		self.assertEqual(out_mid["breakdown"]["total_annual_tax"], 145000.0)
		self.assertEqual(out_mid["breakdown"]["ytd_tds_deducted"], 60000.0)
		self.assertEqual(out_mid["breakdown"]["remaining_months"], 6)
		self.assertEqual(out_mid["tds_amount"], 14167.0)

	def test_calculate_salary_slip_tds_requires_permission(self):
		prev_user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				calculate_salary_slip_tds(
					employee="EMP-0001",
					grand_gross_pay=200000.0,
					pay_period_start="2026-04-01",
				)
		finally:
			frappe.set_user(prev_user)
