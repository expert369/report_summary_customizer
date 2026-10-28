from frappe.model.document import Document

from report_summary_customizer.svg import sanitize_svg


class ReportAppearanceCard(Document):
	"""Child table row for a styled report summary card."""

	def validate(self) -> None:
		"""Sanitize the child row's custom SVG icon."""
		self.icon_svg = sanitize_svg(self.icon_svg, "Card SVG Icon")
