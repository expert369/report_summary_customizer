"""Clean up app-owned records that Frappe does not associate with its module."""

import frappe

APP_MODULE = "Report Summary Customizer"
STYLER_ROLE = "Report Styler"
CUSTOM_FIELDS_FLAG = "report_summary_customizer_custom_fields"


def before_uninstall() -> None:
	"""Remember custom field identities so their ancillary metadata can be removed later."""
	frappe.flags[CUSTOM_FIELDS_FLAG] = frappe.get_all(
		"Custom Field",
		filters={"module": APP_MODULE},
		fields=["dt", "fieldname"],
	)


def after_uninstall() -> None:
	"""Clean side metadata and the role only after Frappe removed the app module."""
	# Frappe runs hooks during --dry-run too. Its module still exists then.
	if frappe.db.exists("Module Def", APP_MODULE):
		return

	previous_user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		for custom_field in frappe.flags.pop(CUSTOM_FIELDS_FLAG, []):
			frappe.db.delete(
				"Property Setter",
				{"doc_type": custom_field.dt, "field_name": custom_field.fieldname},
			)
			if frappe.db.exists("DocType", "DocType Layout"):
				layouts = frappe.get_all(
					"DocType Layout",
					filters={"document_type": custom_field.dt},
					pluck="name",
				)
				for name in layouts:
					if not frappe.db.exists("DocType", custom_field.dt):
						frappe.delete_doc(
							"DocType Layout",
							name,
							ignore_permissions=True,
							force=True,
						)
						continue
					layout = frappe.get_doc("DocType Layout", name)
					for field in layout.fields:
						if field.fieldname == custom_field.fieldname:
							layout.remove(field)
							layout.save(ignore_permissions=True)
							break
			frappe.clear_cache(doctype=custom_field.dt)

		if frappe.db.exists("Role", STYLER_ROLE):
			role = frappe.get_doc("Role", STYLER_ROLE)
			role.remove_roles()
			frappe.delete_doc(
				"Role",
				STYLER_ROLE,
				ignore_permissions=True,
				force=True,
			)
	finally:
		frappe.set_user(previous_user)
