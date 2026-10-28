import re

import frappe
from frappe import _
from frappe.model.document import Document

from report_summary_customizer.svg import sanitize_svg

HEX_COLOR_PATTERN = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
SUPPORTED_REPORT_TYPES = {"Script Report", "Query Report", "Custom Report"}


class ReportAppearance(Document):
	"""Validate saved appearance settings for a report in the Query Report view."""

	def validate(self) -> None:
		"""Validate the report, colors, and summary card labels."""
		self.validate_report()
		self.validate_immutable_report()
		self.validate_colors()
		self.validate_icons()
		self.validate_unique_card_labels()

	def validate_report(self) -> None:
		"""Require a report type rendered by Frappe's Query Report page."""
		report_type = frappe.db.get_value("Report", self.report, "report_type")
		if report_type not in SUPPORTED_REPORT_TYPES:
			frappe.throw(
				_("Report Appearance requires a Script, Query, or Custom Report."),
				frappe.ValidationError,
			)

	def validate_immutable_report(self) -> None:
		"""Prevent changing the report link after the appearance is created."""
		if not self.name or not frappe.db.exists("Report Appearance", self.name):
			return

		existing_report = frappe.db.get_value("Report Appearance", self.name, "report")
		if existing_report and existing_report != self.report:
			frappe.throw(
				_("The linked report cannot be changed after creation."),
				frappe.ValidationError,
			)

	def validate_colors(self) -> None:
		"""Require report and card colors to use three- or six-digit hex values."""
		if self.color and not HEX_COLOR_PATTERN.fullmatch(self.color):
			frappe.throw(_("Title Color must be a valid hex color."), frappe.ValidationError)

		for card in self.cards or []:
			if card.border_color and not HEX_COLOR_PATTERN.fullmatch(card.border_color):
				frappe.throw(
					_("Border Color for card {0} must be a valid hex color.").format(card.card_label),
					frappe.ValidationError,
				)

	def validate_unique_card_labels(self) -> None:
		"""Reject blank or repeated card labels."""
		seen_labels: set[str] = set()
		for card in self.cards or []:
			label = (card.card_label or "").strip()
			if not label:
				frappe.throw(_("Each summary card requires a label."), frappe.ValidationError)
			if label in seen_labels:
				frappe.throw(_("Summary card label {0} is repeated.").format(label), frappe.ValidationError)
			seen_labels.add(label)

	def validate_icons(self) -> None:
		"""Sanitize report and card SVG markup before saving it."""
		self.icon_svg = sanitize_svg(self.icon_svg, _("Report SVG Icon"))
		for card in self.cards or []:
			card.icon_svg = sanitize_svg(card.icon_svg, _("Card SVG Icon"))
