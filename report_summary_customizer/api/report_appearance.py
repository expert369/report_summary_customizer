"""Read and update shared appearance settings for report summary views."""

import json
from typing import Any

import frappe
from frappe import _


@frappe.whitelist(methods=["GET"])
def get_report_appearance(report: str) -> dict[str, Any]:
	"""Return saved appearance settings for a report, or an empty dict."""
	_ensure_logged_in()

	appearance = frappe.db.get_value("Report Appearance", report, ["icon", "color"], as_dict=True)
	if not appearance:
		return {}

	cards = frappe.get_all(
		"Report Appearance Card",
		filters={"parent": report, "parenttype": "Report Appearance", "parentfield": "cards"},
		fields=["card_label", "icon", "border_color", "description"],
		order_by="idx asc",
	)
	return {
		"configured": True,
		"icon": appearance.icon,
		"color": appearance.color,
		"cards": cards,
	}


@frappe.whitelist(methods=["POST"])
def set_report_appearance(
	report: str,
	icon: str | None = None,
	color: str | None = None,
	cards: str | None = None,
) -> dict[str, Any]:
	"""Create, replace, or reset settings for a report with a summary view."""
	_ensure_can_style()
	_validate_supported_report(report)

	clean_icon = _clean_optional_text(icon, "Report Icon")
	clean_color = _clean_optional_text(color, "Title Color")
	clean_cards = _parse_card_rows(cards)

	if not clean_icon and not clean_color and not clean_cards:
		if frappe.db.exists("Report Appearance", report):
			frappe.delete_doc("Report Appearance", report, ignore_permissions=True)
		return {}

	if frappe.db.exists("Report Appearance", report):
		appearance = frappe.get_doc("Report Appearance", report)
	else:
		appearance = frappe.new_doc("Report Appearance")

	appearance.report = report
	appearance.icon = clean_icon
	appearance.color = clean_color
	appearance.set("cards", [])
	for card in clean_cards:
		appearance.append("cards", card)
	appearance.save(ignore_permissions=True)

	return get_report_appearance(report)


def _ensure_logged_in() -> None:
	"""Reject unauthenticated reads of report appearance settings."""
	if frappe.session.user == "Guest":
		frappe.throw(_("You must be logged in to view report appearance settings."), frappe.PermissionError)


def _ensure_can_style() -> None:
	"""Require Report Styler or System Manager for appearance updates."""
	if not {"Report Styler", "System Manager"}.intersection(frappe.get_roles()):
		frappe.throw(_("You do not have permission to change report appearance."), frappe.PermissionError)


def _validate_supported_report(report: str) -> None:
	"""Require a Script, Query, or Custom Report opened in the Query Report view."""
	report_type = frappe.db.get_value("Report", report, "report_type")
	if report_type is None:
		frappe.throw(_("Report {0} does not exist.").format(report), frappe.ValidationError)
	if report_type not in {"Script Report", "Query Report", "Custom Report"}:
		frappe.throw(
			_("Appearance requires a Script, Query, or Custom Report."),
			frappe.ValidationError,
		)


def _clean_optional_text(value: str | None, label: str) -> str | None:
	"""Trim optional string input and normalize empty values to None."""
	if value is None:
		return None
	if not isinstance(value, str):
		frappe.throw(_("{0} must be text.").format(label), frappe.ValidationError)
	return value.strip() or None


def _parse_card_rows(cards: str | None) -> list[dict[str, str | None]]:
	"""Parse card JSON and keep only rows with a style or description."""
	if cards is None or cards == "":
		return []
	if not isinstance(cards, str):
		frappe.throw(_("Summary card settings must be JSON text."), frappe.ValidationError)

	try:
		rows = json.loads(cards)
	except json.JSONDecodeError:
		frappe.throw(_("Summary card settings must be valid JSON."), frappe.ValidationError)

	if rows is None:
		return []
	if not isinstance(rows, list):
		frappe.throw(_("Summary card settings must be a JSON list."), frappe.ValidationError)

	clean_rows: list[dict[str, str | None]] = []
	for row in rows:
		if not isinstance(row, dict):
			frappe.throw(_("Each summary card setting must be an object."), frappe.ValidationError)

		label = _clean_optional_text(row.get("card_label"), "Card Label")
		icon = _clean_optional_text(row.get("icon"), "Card Icon")
		border_color = _clean_optional_text(row.get("border_color"), "Border Color")
		description = _clean_optional_text(row.get("description"), "Card Description")
		if not icon and not border_color and not description:
			continue
		if not label:
			frappe.throw(_("A styled summary card requires a label."), frappe.ValidationError)
		clean_rows.append(
			{
				"card_label": label,
				"icon": icon,
				"border_color": border_color,
				"description": description,
			}
		)

	return clean_rows
