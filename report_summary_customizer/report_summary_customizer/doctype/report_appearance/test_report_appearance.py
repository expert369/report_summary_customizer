import json
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import frappe
from frappe.model.document import Document
from frappe.tests.utils import FrappeTestCase

from report_summary_customizer.api.report_appearance import (
	get_report_appearance,
	set_report_appearance,
)
from report_summary_customizer.uninstall import (
	APP_MODULE,
	STYLER_ROLE,
	after_uninstall,
	before_uninstall,
)


class TestReportAppearance(FrappeTestCase):
	"""Test report appearance storage, validation, and API permissions."""

	@classmethod
	def setUpClass(cls) -> None:
		"""Create the role users shared by this test class."""
		super().setUpClass()
		frappe.set_user("Administrator")
		cls._ensure_role()
		cls.styler_user = cls._ensure_user("report-appearance-styler@example.com", "Report Styler")
		cls.viewer_user = cls._ensure_user("report-appearance-viewer@example.com")

	@classmethod
	def _ensure_role(cls) -> None:
		"""Create the app role if fixtures have not been synchronized on this site."""
		if not frappe.db.exists("Role", STYLER_ROLE):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": STYLER_ROLE,
					"desk_access": 1,
					"is_custom": 1,
				}
			).insert(ignore_permissions=True)

	@classmethod
	def _ensure_user(cls, email: str, role: str | None = None) -> str:
		"""Create a test user if needed and assign its optional role."""
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Report Appearance Test",
					"enabled": 1,
					"user_type": "System User",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)

		if role and role not in frappe.get_roles(email):
			user.add_roles(role)
		return email

	def setUp(self) -> None:
		"""Create isolated Script and Query Reports for this test."""
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self._ensure_role()
		self._ensure_user(self.styler_user, STYLER_ROLE)
		self.script_report = self._create_report("Script Report")
		self.query_report = self._create_report("Query Report")

	def tearDown(self) -> None:
		"""Restore the user active before each test."""
		frappe.set_user(self.previous_user)

	def _create_report(self, report_type: str) -> Document:
		"""Insert a temporary Report record of the requested type."""
		report = frappe.get_doc(
			{
				"doctype": "Report",
				"report_name": f"_Test Report Appearance {report_type} {uuid4().hex[:8]}",
				"ref_doctype": "User",
				"report_type": report_type,
				"is_standard": "No",
				"module": "Report Summary Customizer",
				"query": "SELECT 1",
			}
		)
		report.append("roles", {"role": "System Manager"})
		return report.insert(ignore_permissions=True)

	def _set_as(self, user: str, **kwargs: Any) -> dict[str, Any]:
		"""Call the save API as a selected user and restore the current user."""
		previous_user = frappe.session.user
		try:
			frappe.set_user(user)
			return set_report_appearance(self.script_report.name, **kwargs)
		finally:
			frappe.set_user(previous_user)

	def test_get_without_saved_appearance_returns_empty_dict(self) -> None:
		"""Return an empty object when the report has no appearance row."""
		self.assertEqual(get_report_appearance(self.script_report.name), {})

	def test_guest_cannot_read_appearance(self) -> None:
		"""Reject unauthenticated appearance reads."""
		previous_user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				get_report_appearance(self.script_report.name)
		finally:
			frappe.set_user(previous_user)

	def test_logged_in_user_without_styler_role_can_read_appearance(self) -> None:
		"""Allow a logged-in viewer to read saved appearance settings."""
		set_report_appearance(self.script_report.name, icon="small-up")
		previous_user = frappe.session.user
		try:
			frappe.set_user(self.viewer_user)
			self.assertEqual(get_report_appearance(self.script_report.name)["icon"], "small-up")
		finally:
			frappe.set_user(previous_user)

	def test_user_without_styler_role_cannot_save_appearance(self) -> None:
		"""Reject updates from users without either authorized role."""
		previous_user = frappe.session.user
		try:
			frappe.set_user(self.viewer_user)
			with self.assertRaises(frappe.PermissionError):
				set_report_appearance(self.script_report.name, icon="small-up")
		finally:
			frappe.set_user(previous_user)

	def test_report_styler_can_save_appearance(self) -> None:
		"""Allow Report Styler to save despite having no DocType write permission."""
		payload = self._set_as(self.styler_user, icon="small-up", color="#ED6396")
		self.assertEqual(payload["icon"], "small-up")
		self.assertEqual(payload["color"], "#ED6396")

	def test_query_report_can_be_configured(self) -> None:
		"""Allow appearance settings for Query Reports rendered in the report view."""
		payload = set_report_appearance(self.query_report.name, icon="small-up")
		self.assertEqual(payload["icon"], "small-up")

	def test_custom_report_can_be_configured(self) -> None:
		"""Allow appearance settings for Custom Reports rendered in the report view."""
		custom_report = self._create_report("Custom Report")
		payload = set_report_appearance(custom_report.name, icon="small-up")
		self.assertEqual(payload["icon"], "small-up")

	def test_missing_and_unsupported_reports_are_rejected(self) -> None:
		"""Reject missing reports and report types outside the supported set."""
		with self.assertRaises(frappe.ValidationError):
			set_report_appearance("_Missing Report Appearance", icon="small-up")

		unsupported_report = self._create_report("Report Builder")
		with self.assertRaises(frappe.ValidationError):
			set_report_appearance(unsupported_report.name, icon="small-up")

	def test_create_and_update_keep_one_parent_record(self) -> None:
		"""Create one appearance row and update that same row on later saves."""
		set_report_appearance(self.script_report.name, icon="small-up", color="#ED6396")
		set_report_appearance(self.script_report.name, icon="both", color="#ABC")

		self.assertEqual(
			frappe.db.count("Report Appearance", {"report": self.script_report.name}),
			1,
		)
		self.assertEqual(get_report_appearance(self.script_report.name)["icon"], "both")
		self.assertEqual(get_report_appearance(self.script_report.name)["color"], "#ABC")

	def test_cards_are_replaced_on_update(self) -> None:
		"""Replace old child rows rather than appending new card styles."""
		set_report_appearance(
			self.script_report.name,
			cards=json.dumps(
				[
					{"card_label": "First", "icon": "small-up"},
					{"card_label": "Second", "border_color": "#123"},
				]
			),
		)
		payload = set_report_appearance(
			self.script_report.name,
			cards=json.dumps([{"card_label": "Replacement", "icon": "both"}]),
		)

		self.assertEqual([card["card_label"] for card in payload["cards"]], ["Replacement"])
		self.assertEqual(
			frappe.db.count(
				"Report Appearance Card",
				{
					"parent": self.script_report.name,
					"parenttype": "Report Appearance",
					"parentfield": "cards",
				},
			),
			1,
		)

	def test_unstyled_card_rows_are_dropped(self) -> None:
		"""Drop labeled rows that specify neither styling nor a description."""
		payload = set_report_appearance(
			self.script_report.name,
			cards=json.dumps(
				[
					{"card_label": "No Style"},
					{"card_label": "Styled", "border_color": "#123"},
				]
			),
		)

		self.assertEqual([card["card_label"] for card in payload["cards"]], ["Styled"])

	def test_card_input_is_trimmed_and_blank_rows_are_ignored(self) -> None:
		"""Trim meaningful card values and allow blank-only rows."""
		payload = set_report_appearance(
			self.script_report.name,
			icon="  small-up  ",
			cards=json.dumps(
				[
					{"card_label": "   "},
					{"card_label": "  Total  ", "description": "  Net total  "},
				]
			),
		)

		self.assertEqual(payload["icon"], "small-up")
		self.assertEqual(payload["cards"][0]["card_label"], "Total")
		self.assertEqual(payload["cards"][0]["description"], "Net total")

	def test_non_text_cards_input_is_rejected(self) -> None:
		"""Reject API payloads that violate the declared JSON text argument type."""
		with self.assertRaises(frappe.FrappeTypeError):
			set_report_appearance(self.script_report.name, cards=[{"card_label": "Total"}])

	def test_invalid_card_payload_shapes_are_rejected(self) -> None:
		"""Reject JSON values that do not match the expected card list schema."""
		invalid_payloads = [
			"not JSON",
			'{"card_label": "Total"}',
			"[1]",
			'[{"icon": "small-up"}]',
			'[{"card_label": "Total", "icon": 1}]',
		]
		for payload in invalid_payloads:
			with self.subTest(payload=payload), self.assertRaises(frappe.ValidationError):
				set_report_appearance(self.script_report.name, cards=payload)

	def test_clearing_all_fields_deletes_saved_row(self) -> None:
		"""Delete the parent row when all report and card styles are cleared."""
		set_report_appearance(self.script_report.name, icon="small-up")
		payload = set_report_appearance(self.script_report.name, cards="[]")

		self.assertEqual(payload, {})
		self.assertFalse(frappe.db.exists("Report Appearance", self.script_report.name))

	def test_invalid_title_color_is_rejected(self) -> None:
		"""Reject report-level colors outside the accepted hex formats."""
		with self.assertRaises(frappe.ValidationError):
			set_report_appearance(self.script_report.name, color="red")

	def test_invalid_card_border_color_is_rejected(self) -> None:
		"""Reject card border colors outside the accepted hex formats."""
		with self.assertRaises(frappe.ValidationError):
			set_report_appearance(
				self.script_report.name,
				cards=json.dumps([{"card_label": "Total Asset", "border_color": "red"}]),
			)

	def test_duplicate_card_labels_are_rejected(self) -> None:
		"""Reject repeated card labels in one report appearance."""
		with self.assertRaises(frappe.ValidationError):
			set_report_appearance(
				self.script_report.name,
				cards=json.dumps(
					[
						{"card_label": "Total Asset", "icon": "small-up"},
						{"card_label": "Total Asset", "border_color": "#123"},
					]
				),
			)

	def test_duplicate_labels_after_trimming_are_rejected(self) -> None:
		"""Treat labels with surrounding whitespace as the same card label."""
		with self.assertRaises(frappe.ValidationError):
			set_report_appearance(
				self.script_report.name,
				cards=json.dumps(
					[
						{"card_label": " Total ", "icon": "small-up"},
						{"card_label": "Total", "border_color": "#123"},
					]
				),
			)

	def test_uninstall_cleanup_respects_dry_run_and_cleans_after_module_removal(self) -> None:
		"""Keep data on dry run and remove the role after Frappe removes the module."""
		set_report_appearance(
			self.script_report.name,
			icon="small-up",
			cards=json.dumps([{"card_label": "Total", "description": "Net total"}]),
		)
		custom_field_name = f"User-custom_rsa_uninstall_{uuid4().hex[:8]}"
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "User",
				"label": "rsa Uninstall Test",
				"fieldname": custom_field_name.split("-", 1)[1],
				"fieldtype": "Data",
				"module": APP_MODULE,
			}
		).insert(ignore_permissions=True)

		self.assertTrue(frappe.db.exists("Report Appearance", self.script_report.name))
		self.assertEqual(
			frappe.db.count(
				"Report Appearance Card",
				{
					"parent": self.script_report.name,
					"parenttype": "Report Appearance",
					"parentfield": "cards",
				},
			),
			1,
		)
		self.assertTrue(frappe.db.exists("Custom Field", custom_field_name))
		self.assertTrue(frappe.db.exists("Role", STYLER_ROLE))

		before_uninstall()
		after_uninstall()

		# Module Def is present, so the callback is running in Frappe's dry-run path.
		self.assertTrue(frappe.db.exists("Report Appearance", self.script_report.name))
		self.assertTrue(frappe.db.exists("Custom Field", custom_field_name))
		self.assertTrue(frappe.db.exists("Role", STYLER_ROLE))

		# Frappe's module cleanup deletes Custom Field rows with ignore_on_trash=True.
		frappe.delete_doc("Custom Field", custom_field_name, ignore_on_trash=True, force=True)
		db_exists = frappe.db.exists

		def module_removed(doctype: str, *args: Any, **kwargs: Any) -> Any:
			if doctype == "Module Def" and args and args[0] == APP_MODULE:
				return False
			return db_exists(doctype, *args, **kwargs)

		with patch.object(frappe.db, "exists", side_effect=module_removed):
			after_uninstall()

		self.assertFalse(frappe.db.exists("Custom Field", custom_field_name))
		self.assertFalse(frappe.db.exists("Role", STYLER_ROLE))
		self.assertEqual(
			frappe.db.count("Has Role", {"role": STYLER_ROLE, "parent": self.styler_user}),
			0,
		)

	def test_app_doctypes_belong_to_app_module_for_core_uninstaller(self) -> None:
		"""Keep app DocTypes in its module so Frappe's uninstaller drops them."""
		from frappe.installer import _get_module_linked_doctype_field_map

		for doctype in ("Report Appearance", "Report Appearance Card"):
			with self.subTest(doctype=doctype):
				self.assertEqual(frappe.db.get_value("DocType", doctype, "module"), APP_MODULE)

		self.assertEqual(_get_module_linked_doctype_field_map().get("Custom Field"), "module")
